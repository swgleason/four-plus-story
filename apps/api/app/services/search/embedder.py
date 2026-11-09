"""Approved-story embedding generation with content-hash-based refresh."""

from __future__ import annotations

import hashlib
import logging
import math
from typing import Any

from app.core.config import get_settings
from app.services.search.embeddings import EmbeddingProvider, create_embedding_provider

logger = logging.getLogger(__name__)


class StoryEmbedder:
    """Generate and upsert configured vector embeddings for approved stories."""

    embedding_type = "story_composite"

    def __init__(
        self,
        supabase: Any,
        provider: EmbeddingProvider | None = None,
    ) -> None:
        self.supabase = supabase
        self.provider = provider or create_embedding_provider()
        settings = get_settings()
        self.model_name = settings.embedding_model
        self.model_version = settings.embedding_model_version or settings.embedding_model
        self.dimension = settings.embedding_dimension
        if self.dimension != 1536:
            raise ValueError(
                "The installed story_embeddings HNSW index requires embedding_dimension=1536."
            )

    async def embed_approved_stories(self, batch_size: int = 100) -> dict[str, int]:
        """Generate missing or stale embeddings for every approved story."""
        if batch_size < 1 or batch_size > 500:
            raise ValueError("batch_size must be between 1 and 500.")

        await self.provider.initialize()
        processed = 0
        skipped = 0
        try:
            offset = 0
            while True:
                result = await (
                    self.supabase.table("stories")
                    .select("*")
                    .eq("status", "approved")
                    .order("created_at")
                    .range(offset, offset + batch_size - 1)
                    .execute()
                )
                stories = getattr(result, "data", None) or []
                if not stories:
                    break
                for story in stories:
                    if await self._embed_story(story):
                        processed += 1
                    else:
                        skipped += 1
                offset += len(stories)
                if len(stories) < batch_size:
                    break
        finally:
            await self.provider.close()
        return {"processed": processed, "skipped": skipped}

    async def embed_story(self, story: dict[str, Any]) -> bool:
        """Generate/update one embedding if story is approved and its content changed."""
        if story.get("status") != "approved":
            raise ValueError("Only approved stories may receive search embeddings.")
        await self.provider.initialize()
        try:
            return await self._embed_story(story)
        finally:
            await self.provider.close()

    async def _embed_story(self, story: dict[str, Any]) -> bool:
        if story.get("status") != "approved":
            raise ValueError("Only approved stories may receive search embeddings.")
        composite = await self._composite_content(story)
        content_hash = hashlib.sha256(composite.encode("utf-8")).hexdigest()
        existing_result = await (
            self.supabase.table("story_embeddings")
            .select("content_hash,model_version")
            .eq("story_id", str(story["id"]))
            .eq("embedding_type", self.embedding_type)
            .eq("embedding_model", self.model_name)
            .maybe_single()
            .execute()
        )
        existing = self._first_row(existing_result)
        if (
            existing
            and existing.get("content_hash") == content_hash
            and existing.get("model_version") == self.model_version
        ):
            return False

        response = await self.provider.embed(composite, self.model_name, self.dimension)
        if len(response.vector) != self.dimension:
            raise ValueError(
                f"Embedding provider returned {len(response.vector)} dimensions; "
                f"the database index requires {self.dimension}."
            )
        if not all(map(self._is_finite, response.vector)):
            raise ValueError("Embedding provider returned a non-finite vector component.")

        payload = {
            "story_id": str(story["id"]),
            "embedding_type": self.embedding_type,
            "embedding_model": self.model_name,
            "model_version": self.model_version or response.model_version,
            "content_hash": content_hash,
            "embedding": "[" + ",".join(format(value, ".9g") for value in response.vector) + "]",
        }
        await (
            self.supabase.table("story_embeddings")
            .upsert(
                payload,
                on_conflict="story_id,embedding_type,embedding_model",
            )
            .execute()
        )
        logger.info(
            "Generated search embedding for approved story %s.",
            story["id"],
            extra={"model": response.model_name, "content_hash": content_hash},
        )
        return True

    async def _composite_content(self, story: dict[str, Any]) -> str:
        variants = await self._related_values(
            "story_variant_assignments", story["id"], "variant"
        )
        emotions_result = await (
            self.supabase.table("story_emotions")
            .select("emotion,energy_level,sensations_identified")
            .eq("story_id", str(story["id"]))
            .execute()
        )
        emotions = getattr(emotions_result, "data", None) or []
        step_result = await (
            self.supabase.table("story_step_analyses")
            .select("setting,trigger,emotion_and_body_sensations,point")
            .eq("story_id", str(story["id"]))
            .maybe_single()
            .execute()
        )
        step = self._first_row(step_result) or {}
        curated_result = await (
            self.supabase.table("story_curated_versions")
            .select("curated_text")
            .eq("story_id", str(story["id"]))
            .eq("is_approved", True)
            .order("created_at", desc=True)
            .limit(1)
            .maybe_single()
            .execute()
        )
        curated = self._first_row(curated_result) or {}
        emotion_text = "; ".join(
            f"{item.get('emotion', '')} ({item.get('energy_level', '')}): "
            f"{', '.join(item.get('sensations_identified') or [])}"
            for item in emotions
        )
        return "\n".join(
            [
                f"Title: {story.get('title', '')}",
                f"Variants: {', '.join(variants)}",
                f"Emotions & Somatics: {emotion_text}",
                f"STEP Setting: {step.get('setting', '')}",
                f"STEP Trigger: {step.get('trigger', '')}",
                f"STEP Emotion & Sensations: {step.get('emotion_and_body_sensations', '')}",
                f"STEP Point: {step.get('point', '')}",
                f"Story Excerpt: {str(story.get('original_text', ''))[:1200]}",
                f"Curated Text: {str(curated.get('curated_text', ''))[:600]}",
            ]
        )

    async def _related_values(self, table_name: str, story_id: Any, column: str) -> list[str]:
        result = await (
            self.supabase.table(table_name)
            .select(column)
            .eq("story_id", str(story_id))
            .execute()
        )
        return [str(row[column]) for row in (getattr(result, "data", None) or [])]

    @staticmethod
    def _is_finite(value: float) -> bool:
        return math.isfinite(value)

    @staticmethod
    def _first_row(result: Any) -> dict[str, Any] | None:
        data = getattr(result, "data", None)
        if isinstance(data, list):
            return data[0] if data else None
        return data if isinstance(data, dict) else None
