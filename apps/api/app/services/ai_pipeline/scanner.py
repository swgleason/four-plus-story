"""Asynchronous document chunk scanning and pending-review story persistence."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from app.schemas.ai import (
    CandidateStoryBoundary,
    StoryBoundaryCandidateInDB,
    StoryBoundaryExtractionResponse,
)
from app.schemas.document import DocumentChunkInDB, DocumentPageInDB
from app.schemas.enums import JobStatus, NarratorGender, StoryStatus, StoryVisibility
from app.schemas.story import StoryInDB
from app.services.ai.base import AIProviderError, AIRequestConfig, AIResponse
from app.services.ai.manager import AIServiceManager
from app.services.ai_pipeline.prompts import BOUNDARY_SYSTEM_PROMPT
from app.services.ai_pipeline.reconciler import BoundaryReconciler, VerifiedStoryBoundary

logger = logging.getLogger(__name__)

MAX_DISCOVERED_STORY_WORDS = 800


class StoryBoundaryScanResult(BaseModel):
    """Counts from a completed story boundary scan."""

    model_config = ConfigDict(from_attributes=True)

    document_id: str
    job_id: str
    chunks_scanned: int
    candidates_proposed: int
    candidates_created: int
    candidates_rejected: int


class StoryBoundaryScanner:
    """Scan stored chunks through the provider-independent AI manager."""

    def __init__(
        self,
        supabase: Any,
        ai_manager: AIServiceManager,
        reconciler: BoundaryReconciler | None = None,
        request_config: AIRequestConfig | None = None,
    ) -> None:
        self.supabase = supabase
        self.ai_manager = ai_manager
        self.reconciler = reconciler or BoundaryReconciler()
        self.request_config = request_config

    async def scan_document(self, document_id: str, job_id: str) -> StoryBoundaryScanResult:
        """Scan all stored chunks, persisting only exact-source verified proposals."""
        try:
            await self._update_job(job_id, status=JobStatus.PROCESSING.value)
            await self._log_event(job_id, "scan", "Story boundary scanning started.")
            pages = await self._fetch_pages(document_id)
            chunks = await self._fetch_chunks(document_id)
            if not pages or not chunks:
                raise ValueError("The document has no ingested pages or chunks to scan.")

            document_text = "\n".join(page.extracted_text for page in pages)
            self._validate_chunk_sources(chunks, document_text)
            await self.ai_manager.initialize()

            existing = await self._existing_boundaries(document_id)
            candidates_proposed = 0
            candidates_created = 0
            candidates_rejected = 0

            for chunk in chunks:
                def log_retry(
                    retry_number: int,
                    error: AIProviderError,
                    chunk_index: int = chunk.chunk_index,
                ) -> None:
                    logger.warning(
                        "Transient AI provider error scanning chunk %d; retry %d/%d "
                        "(provider=%s, status=%s).",
                        chunk_index,
                        retry_number,
                        self.ai_manager.max_retries,
                        error.provider,
                        error.status_code,
                    )

                response = await self.ai_manager.complete_structured(
                    system_prompt=BOUNDARY_SYSTEM_PROMPT,
                    user_prompt=chunk.text,
                    response_schema=StoryBoundaryExtractionResponse,
                    config=self.request_config,
                    retry_callback=log_retry,
                )
                extraction = StoryBoundaryExtractionResponse.model_validate_json(
                    self._response_content(response)
                )
                if not extraction.has_candidates:
                    continue
                candidates_proposed += len(extraction.candidates)

                for candidate in extraction.candidates:
                    verified = self.reconciler.reconcile(candidate, chunk, pages, chunks)
                    if verified is None or not self._is_complete_candidate(
                        verified.text,
                        document_text,
                        verified.document_char_start,
                    ):
                        candidates_rejected += 1
                        continue
                    boundary_key = (
                        verified.document_char_start,
                        verified.document_char_end,
                    )
                    if boundary_key in existing:
                        continue
                    await self._persist_candidate(
                        document_id=document_id,
                        chunk=chunk,
                        candidate=candidate,
                        verified=verified,
                    )
                    existing.add(boundary_key)
                    candidates_created += 1

            result = StoryBoundaryScanResult(
                document_id=document_id,
                job_id=job_id,
                chunks_scanned=len(chunks),
                candidates_proposed=candidates_proposed,
                candidates_created=candidates_created,
                candidates_rejected=candidates_rejected,
            )
            await self._update_job(job_id, status=JobStatus.COMPLETED.value, error_message=None)
            await self._log_event(
                job_id,
                "complete",
                "Story boundary scanning completed.",
                {
                    "chunks_scanned": result.chunks_scanned,
                    "candidates_proposed": result.candidates_proposed,
                    "candidates_created": result.candidates_created,
                    "candidates_rejected": result.candidates_rejected,
                },
            )
            return result
        except Exception as exc:
            logger.error(
                "Story boundary scan failed for document %s (job %s).",
                document_id,
                job_id,
                extra={"error_type": type(exc).__name__},
            )
            try:
                await self._update_job(
                    job_id,
                    status=JobStatus.FAILED.value,
                    error_message=f"Story discovery failed: {type(exc).__name__}: {exc}",
                )
                await self._log_event(
                    job_id,
                    "failed",
                    "Story boundary scanning failed.",
                    {"error_type": type(exc).__name__},
                    level="error",
                )
            except Exception as status_exc:
                logger.error(
                    "Could not record failed story discovery job %s.",
                    job_id,
                    extra={"error_type": type(status_exc).__name__},
                )
                raise status_exc from exc
            raise
        finally:
            await self.ai_manager.close()

    @staticmethod
    def _is_complete_candidate(text: str, source_text: str, start_offset: int) -> bool:
        words = text.split()
        preceding_source = source_text[:start_offset]
        preceding_text = preceding_source.rstrip()
        starts_at_boundary = (
            not preceding_text
            or preceding_source.endswith("\n\n")
            or re.search(r"""[.!?…]["'”’)\]]*$""", preceding_text) is not None
        )
        return bool(
            words
            and len(words) <= MAX_DISCOVERED_STORY_WORDS
            and re.search(r"""[.!?…]["'”’)\]]*\s*$""", text)
            and starts_at_boundary
        )

    async def _fetch_pages(self, document_id: str) -> list[DocumentPageInDB]:
        rows = await self._fetch_all_rows("document_pages", document_id, "page_number")
        return [DocumentPageInDB.model_validate(row) for row in rows]

    async def _fetch_chunks(self, document_id: str) -> list[DocumentChunkInDB]:
        rows = await self._fetch_all_rows("document_chunks", document_id, "chunk_index")
        return [DocumentChunkInDB.model_validate(row) for row in rows]

    async def _fetch_all_rows(
        self, table_name: str, document_id: str, order_column: str
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        page_size = 1000
        offset = 0
        while True:
            result = await (
                self.supabase.table(table_name)
                .select("*")
                .eq("document_id", document_id)
                .order(order_column)
                .range(offset, offset + page_size - 1)
                .execute()
            )
            batch = getattr(result, "data", None) or []
            rows.extend(batch)
            if len(batch) < page_size:
                return rows
            offset += page_size

    @staticmethod
    def _validate_chunk_sources(chunks: Sequence[DocumentChunkInDB], document_text: str) -> None:
        for chunk in chunks:
            if (
                chunk.char_end <= chunk.char_start
                or document_text[chunk.char_start : chunk.char_end] != chunk.text
            ):
                raise ValueError(f"Chunk {chunk.chunk_index} does not match stored page text.")

    async def _existing_boundaries(self, document_id: str) -> set[tuple[int, int]]:
        result = await (
            self.supabase.table("story_boundary_candidates")
            .select("document_char_start,document_char_end")
            .eq("document_id", document_id)
            .execute()
        )
        return {
            (int(row["document_char_start"]), int(row["document_char_end"]))
            for row in (getattr(result, "data", None) or [])
        }

    async def _persist_candidate(
        self,
        document_id: str,
        chunk: DocumentChunkInDB,
        candidate: CandidateStoryBoundary,
        verified: VerifiedStoryBoundary,
    ) -> tuple[StoryInDB, StoryBoundaryCandidateInDB]:
        word_count = len(verified.text.split())
        story_payload = {
            "id": str(uuid4()),
            "document_id": document_id,
            "title": candidate.tentative_title.strip() or "Untitled discovered story",
            "original_text": verified.text,
            "original_word_count": word_count,
            "estimated_spoken_duration_seconds": round(word_count * 60 / 140),
            "is_autobiographical": None,
            "narrator_gender": NarratorGender.UNKNOWN.value,
            "status": StoryStatus.DISCOVERED_PENDING_REVIEW.value,
            "visibility": StoryVisibility.INTERNAL_ONLY.value,
        }
        story_id = story_payload["id"]
        try:
            story_result = await (
                self.supabase.table("stories").insert(story_payload).select("*").single().execute()
            )
            story_row = self._required_row(story_result, "Story insert returned no row.")

            span_rows = [
                {"story_id": story_id, **span.model_dump(mode="json")}
                for span in verified.source_spans
            ]
            await self.supabase.table("story_source_spans").insert(span_rows).execute()

            candidate_payload = {
                "document_id": document_id,
                "story_id": story_id,
                "chunk_id": str(chunk.id),
                "tentative_title": candidate.tentative_title.strip() or "Untitled discovered story",
                "first_sentence": candidate.first_sentence,
                "last_sentence": candidate.last_sentence,
                "evidence_quote": candidate.evidence_quote,
                "approx_char_start": candidate.approx_char_start,
                "approx_char_end": candidate.approx_char_end,
                "document_char_start": verified.document_char_start,
                "document_char_end": verified.document_char_end,
            }
            candidate_result = await (
                self.supabase.table("story_boundary_candidates")
                .insert(candidate_payload)
                .select("*")
                .single()
                .execute()
            )
            candidate_row = self._required_row(
                candidate_result,
                "Boundary candidate insert returned no row.",
            )
            return StoryInDB.model_validate(story_row), StoryBoundaryCandidateInDB.model_validate(
                candidate_row
            )
        except Exception:
            await self.supabase.table("stories").delete().eq("id", story_id).execute()
            raise

    async def _update_job(self, job_id: str, **values: Any) -> None:
        await self.supabase.table("processing_jobs").update(values).eq("id", job_id).execute()

    async def _log_event(
        self,
        job_id: str,
        stage: str,
        message: str,
        details: dict[str, Any] | None = None,
        level: str = "info",
    ) -> None:
        await (
            self.supabase.table("processing_job_events")
            .insert(
                {
                    "job_id": job_id,
                    "stage": stage,
                    "level": level,
                    "message": message,
                    "details": details or {},
                }
            )
            .execute()
        )

    @staticmethod
    def _response_content(response: AIResponse) -> str:
        if not isinstance(response.content, str):
            raise TypeError("AI provider returned non-text structured content.")
        return response.content

    @staticmethod
    def _required_row(result: Any, message: str) -> dict[str, Any]:
        data = getattr(result, "data", None)
        if isinstance(data, list):
            data = data[0] if data else None
        if not isinstance(data, dict):
            raise TypeError(message)
        return data
