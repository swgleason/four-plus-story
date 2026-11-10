"""Upload deduplication, persistence, and asynchronous ingestion job processing."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from pathlib import PurePath
from typing import Any
from uuid import uuid4

from app.core.config import get_settings
from app.schemas.enums import DocumentRightsStatus, DocumentType, JobStatus
from app.services.ingest.chunker import SemanticChunker
from app.services.ingest.parser import DocumentParser

logger = logging.getLogger(__name__)


class DuplicateDocumentError(Exception):
    """Raised when a source file hash is already registered."""

    def __init__(self, document: dict[str, Any]) -> None:
        super().__init__("A document with this source file has already been ingested.")
        self.document = document


class IngestionStorageError(RuntimeError):
    """Raised when required Supabase storage or database configuration is unavailable."""


class MissingStorageBucketError(IngestionStorageError):
    """Raised when the configured Supabase Storage bucket does not exist."""


class IngestionManager:
    """Coordinate original-file storage, metadata persistence, and parsing jobs."""

    def __init__(
        self,
        supabase: Any,
        parser: DocumentParser | None = None,
        chunker: SemanticChunker | None = None,
        bucket_name: str | None = None,
    ) -> None:
        settings = get_settings()
        self.supabase = supabase
        self.parser = parser or DocumentParser()
        self.chunker = chunker or SemanticChunker(
            max_tokens=settings.document_chunk_max_tokens,
            overlap_tokens=settings.document_chunk_overlap_tokens,
        )
        self.bucket_name = bucket_name or settings.raw_documents_bucket

    @staticmethod
    def sha256(content: bytes) -> str:
        """Return the lowercase SHA-256 digest of uploaded bytes."""
        return hashlib.sha256(content).hexdigest()

    async def create_upload(
        self,
        content: bytes,
        filename: str,
        title: str,
        document_type: DocumentType,
        author: str | None = None,
        rights_status: DocumentRightsStatus = DocumentRightsStatus.RESTRICTED_INTERNAL,
        metadata: dict[str, Any] | None = None,
        created_by: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not content:
            raise ValueError("The uploaded file is empty.")
        if not title.strip():
            raise ValueError("Document title must not be blank.")
        if not filename:
            raise ValueError("The uploaded file must have a filename.")

        file_hash = self.sha256(content)
        existing_result = await (
            self.supabase.table("documents")
            .select("*")
            .eq("file_hash_sha256", file_hash)
            .maybe_single()
            .execute()
        )
        existing = self._first_row(existing_result)
        if existing:
            raise DuplicateDocumentError(existing)

        document_id = str(uuid4())
        job_id = str(uuid4())
        safe_name = self._safe_filename(filename)
        storage_path = f"{document_id}/{safe_name}"
        content_type = "application/pdf" if safe_name.lower().endswith(".pdf") else "text/plain"

        try:
            await self.supabase.storage.from_(self.bucket_name).upload(
                storage_path,
                content,
                {"content-type": content_type, "upsert": False},
            )
        except Exception as exc:
            if self._is_missing_bucket_error(exc):
                raise MissingStorageBucketError(
                    f"Supabase Storage bucket '{self.bucket_name}' does not exist. "
                    "Create it as a private bucket or restart the API with valid "
                    "Supabase service-role credentials so startup can provision it."
                ) from exc
            raise

        document_payload = {
            "id": document_id,
            "title": title,
            "author": author,
            "document_type": document_type.value,
            "source_file_path": storage_path,
            "file_hash_sha256": file_hash,
            "page_count": None,
            "rights_status": rights_status.value,
            "publication_restrictions": None,
            "metadata": metadata or {},
            "created_by": created_by,
        }

        try:
            document_result = await (
                self.supabase.table("documents")
                .insert(document_payload)
                .select("*")
                .single()
                .execute()
            )
            document = self._required_row(document_result, "Document insert returned no row.")
        except Exception as exc:
            await self._remove_storage_object(storage_path)
            existing_result = await (
                self.supabase.table("documents")
                .select("*")
                .eq("file_hash_sha256", file_hash)
                .maybe_single()
                .execute()
            )
            existing = self._first_row(existing_result)
            if existing:
                raise DuplicateDocumentError(existing) from exc
            raise

        job_payload = {
            "id": job_id,
            "document_id": document_id,
            "job_type": "document_ingestion",
            "status": JobStatus.PENDING.value,
            "config": {"source_file_name": safe_name},
        }
        try:
            job_result = await (
                self.supabase.table("processing_jobs")
                .insert(job_payload)
                .select("*")
                .single()
                .execute()
            )
            job = self._required_row(job_result, "Processing job insert returned no row.")
            await self._log_event(
                job_id,
                "queued",
                "Document ingestion job queued.",
                {"document_id": document_id, "file_size_bytes": len(content)},
            )
        except Exception:
            await self.supabase.table("processing_jobs").delete().eq("id", job_id).execute()
            await self.supabase.table("documents").delete().eq("id", document_id).execute()
            await self._remove_storage_object(storage_path)
            raise

        return document, job

    async def process_document(
        self,
        document_id: str,
        job_id: str,
        content: bytes,
        filename: str,
        document_type: DocumentType,
    ) -> None:
        """Parse and persist extracted pages and token-bounded chunks for a job."""
        try:
            await self._update_job(job_id, status=JobStatus.PROCESSING.value)
            await self._log_event(job_id, "extract", "Text extraction started.")
            pages = await asyncio.to_thread(self.parser.parse, content, filename, document_type)
            page_rows = [
                {"document_id": document_id, **page.model_dump(mode="json")} for page in pages
            ]
            await self._insert_batches("document_pages", page_rows)
            await self._log_event(
                job_id,
                "extract",
                "Text extraction completed.",
                {"page_count": len(pages), "character_count": sum(p.char_count for p in pages)},
            )

            chunks = await asyncio.to_thread(self.chunker.chunk, pages)
            chunk_rows = [
                {"document_id": document_id, **chunk.model_dump(mode="json")} for chunk in chunks
            ]
            await self._insert_batches("document_chunks", chunk_rows)
            await self._update_document(document_id, page_count=len(pages))
            await self._update_job(job_id, status=JobStatus.COMPLETED.value, error_message=None)
            await self._log_event(
                job_id,
                "complete",
                "Document ingestion completed.",
                {"page_count": len(pages), "chunk_count": len(chunks)},
            )
        except Exception as exc:
            logger.error(
                "Document ingestion failed for document %s (job %s).",
                document_id,
                job_id,
                extra={"error_type": type(exc).__name__},
            )
            try:
                await (
                    self.supabase.table("document_chunks")
                    .delete()
                    .eq("document_id", document_id)
                    .execute()
                )
                await (
                    self.supabase.table("document_pages")
                    .delete()
                    .eq("document_id", document_id)
                    .execute()
                )
            except Exception as cleanup_exc:  # noqa: BLE001 — preserve the original job failure.
                logger.error(
                    "Could not clean partial ingestion rows for document %s.",
                    document_id,
                    extra={"error_type": type(cleanup_exc).__name__},
                )
            try:
                await self._update_job(
                    job_id,
                    status=JobStatus.FAILED.value,
                    error_message=f"Ingestion failed: {type(exc).__name__}",
                )
                await self._log_event(
                    job_id,
                    "failed",
                    "Document ingestion failed.",
                    {"error_type": type(exc).__name__},
                    level="error",
                )
            except Exception as status_exc:
                logger.error(
                    "Could not record failed ingestion state for job %s.",
                    job_id,
                    extra={"error_type": type(status_exc).__name__},
                )
                raise status_exc from exc
            raise

    async def get_job(self, job_id: str) -> dict[str, Any] | None:
        result = await (
            self.supabase.table("processing_jobs")
            .select("*")
            .eq("id", job_id)
            .maybe_single()
            .execute()
        )
        job = self._first_row(result)
        if job is None:
            return None
        events_result = await (
            self.supabase.table("processing_job_events")
            .select("*")
            .eq("job_id", job_id)
            .order("created_at")
            .execute()
        )
        job["events"] = getattr(events_result, "data", None) or []
        return job

    async def get_document(self, document_id: str) -> dict[str, Any] | None:
        result = await (
            self.supabase.table("documents")
            .select("id")
            .eq("id", document_id)
            .maybe_single()
            .execute()
        )
        return self._first_row(result)

    async def get_document_rows(
        self,
        table_name: str,
        document_id: str,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        if table_name not in {"document_pages", "document_chunks"}:
            raise ValueError("Unsupported document resource.")
        result = await (
            self.supabase.table(table_name)
            .select("*")
            .eq("document_id", document_id)
            .order("page_number" if table_name == "document_pages" else "chunk_index")
            .range(offset, offset + limit - 1)
            .execute()
        )
        return getattr(result, "data", None) or []

    async def _insert_batches(self, table_name: str, rows: list[dict[str, Any]]) -> None:
        for index in range(0, len(rows), 100):
            await self.supabase.table(table_name).insert(rows[index : index + 100]).execute()

    async def _update_job(self, job_id: str, **values: Any) -> None:
        await self.supabase.table("processing_jobs").update(values).eq("id", job_id).execute()

    async def _update_document(self, document_id: str, **values: Any) -> None:
        await self.supabase.table("documents").update(values).eq("id", document_id).execute()

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

    async def _remove_storage_object(self, storage_path: str) -> None:
        await self.supabase.storage.from_(self.bucket_name).remove([storage_path])

    @staticmethod
    def _safe_filename(filename: str) -> str:
        basename = PurePath(filename.replace("\\", "/")).name
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", basename).strip("._")
        return safe or "document"

    @staticmethod
    def _first_row(result: Any) -> dict[str, Any] | None:
        data = getattr(result, "data", None)
        if isinstance(data, list):
            return data[0] if data else None
        return data if isinstance(data, dict) else None

    @classmethod
    def _required_row(cls, result: Any, message: str) -> dict[str, Any]:
        row = cls._first_row(result)
        if row is None:
            raise IngestionStorageError(message)
        return row

    @staticmethod
    def _is_missing_bucket_error(exc: Exception) -> bool:
        status_code = getattr(exc, "status", getattr(exc, "status_code", None))
        message = getattr(exc, "message", str(exc))
        return str(status_code) == "404" and "bucket not found" in str(message).lower()
