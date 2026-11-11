"""RRF hybrid search orchestration and access-control validation."""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.schemas.enums import DocumentRightsStatus, UserRole
from app.schemas.search import (
    HybridSearchRequest,
    HybridSearchResponse,
    HybridSearchResultItem,
)
from app.services.search.embeddings import EmbeddingProvider

_REGISTERED_ROLES = {
    UserRole.CHURCH_MEMBER,
    UserRole.CURATOR,
    UserRole.REVIEWER,
    UserRole.SUPER_ADMIN,
}
_CLEARED_RIGHTS = {
    DocumentRightsStatus.PUBLIC_DOMAIN,
    DocumentRightsStatus.LICENSED,
    DocumentRightsStatus.FAIR_USE_EDUCATIONAL,
}


def reciprocal_rank_fusion(
    sparse_rank: int | None,
    dense_rank: int | None,
    k: int = 60,
) -> float:
    """Calculate RRF with one-based ranks, omitting absent retrieval lanes."""
    if k < 1:
        raise ValueError("RRF smoothing constant must be at least one.")
    if any(rank is not None and rank < 1 for rank in (sparse_rank, dense_rank)):
        raise ValueError("Search ranks must be one-based positive integers.")
    return sum(1 / (k + rank) for rank in (sparse_rank, dense_rank) if rank is not None)


def can_access_story(
    status: str,
    visibility: str,
    rights_status: str,
    publication_restrictions: str | None,
    user_role: UserRole,
) -> bool:
    """Mirror the SQL search access gate for policy-level tests and diagnostics."""
    if status != "approved" or publication_restrictions:
        return False
    try:
        rights = DocumentRightsStatus(rights_status)
    except ValueError:
        return False
    if rights not in _CLEARED_RIGHTS:
        return False
    if visibility == "public":
        return True
    return visibility == "registered_users" and user_role in _REGISTERED_ROLES


class HybridSearchEngine:
    """Embed a query and invoke the database's indexed, rights-filtered RRF RPC."""

    def __init__(self, supabase: Any, embedding_provider: EmbeddingProvider) -> None:
        self.supabase = supabase
        self.embedding_provider = embedding_provider
        settings = get_settings()
        self.model_name = settings.embedding_model
        self.dimension = settings.embedding_dimension
        if self.dimension != 1536:
            raise ValueError(
                "The installed story_embeddings HNSW index requires embedding_dimension=1536."
            )

    async def search(
        self,
        request: HybridSearchRequest,
        user_role: UserRole = UserRole.PUBLIC_GUEST,
    ) -> HybridSearchResponse:
        if not request.query.strip():
            raise ValueError("Search query must not be blank.")
        await self.embedding_provider.initialize()
        try:
            embedded = await self.embedding_provider.embed(
                request.query.strip(),
                self.model_name,
                self.dimension,
            )
            if len(embedded.vector) != self.dimension:
                raise ValueError(
                    f"Query embedding has {len(embedded.vector)} dimensions; "
                    f"the database index requires {self.dimension}."
                )
            arguments = {
                "query_text": request.query.strip(),
                "requested_embedding_model": self.model_name,
                "query_embedding": "["
                + ",".join(format(value, ".9g") for value in embedded.vector)
                + "]",
                "include_registered": user_role in _REGISTERED_ROLES,
                "match_count": request.limit,
                "result_offset": request.offset,
                "filter_variant": request.filter_variant.value if request.filter_variant else None,
                "filter_emotion": request.filter_emotion.value if request.filter_emotion else None,
                "rrf_k": 60,
            }
            result = await self.supabase.rpc("hybrid_story_search", arguments).execute()
            rows = getattr(result, "data", None) or []
            if not rows and request.offset:
                total_result = await self.supabase.rpc(
                    "hybrid_story_search",
                    {**arguments, "match_count": 1, "result_offset": 0},
                ).execute()
                total_rows = getattr(total_result, "data", None) or []
                total_matched = int(total_rows[0].get("total_matched", 0)) if total_rows else 0
            else:
                total_matched = int(rows[0].get("total_matched", 0)) if rows else 0
            results = [
                HybridSearchResultItem(
                    story_id=row["story_id"],
                    title=row["title"],
                    original_text_preview=self._preview(str(row.get("original_text") or "")),
                    original_word_count=row["original_word_count"],
                    estimated_spoken_duration_seconds=row[
                        "estimated_spoken_duration_seconds"
                    ],
                    length_advisory_exceeds_800_words=row[
                        "length_advisory_exceeds_800_words"
                    ],
                    rrf_score=row["rrf_score"],
                )
                for row in rows
            ]
            return HybridSearchResponse(
                query=request.query,
                total_matched=total_matched,
                results=results,
            )
        finally:
            await self.embedding_provider.close()

    @staticmethod
    def _preview(text: str, maximum_length: int = 400) -> str:
        normalized = " ".join(text.split())
        if len(normalized) <= maximum_length:
            return normalized
        return normalized[:maximum_length].rsplit(" ", 1)[0] + "..."
