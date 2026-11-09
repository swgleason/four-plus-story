from __future__ import annotations

from itertools import pairwise
from types import SimpleNamespace
from typing import Any

import pymupdf
import pytest
import tiktoken
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.supabase import require_curator
from app.routers.documents import get_ingestion_manager, router
from app.schemas.document import DocumentPageBase
from app.schemas.enums import DocumentType
from app.services.ingest.chunker import SemanticChunker
from app.services.ingest.manager import DuplicateDocumentError, IngestionManager
from app.services.ingest.parser import DocumentParseError, DocumentParser


def make_pdf_bytes(page_texts: list[str]) -> bytes:
    document = pymupdf.open()
    for text in page_texts:
        page = document.new_page()
        page.insert_text((72, 72), text)
    content = document.tobytes()
    document.close()
    return content


def test_parser_extracts_pdf_pages_and_layout() -> None:
    parser = DocumentParser()
    pages = parser.parse(
        make_pdf_bytes(["First page text.", "Second page text."]),
        "sample.pdf",
        DocumentType.PDF_BOOK,
    )

    assert len(pages) == 2
    assert pages[0].page_number == 1
    assert pages[0].extracted_text.strip() == "First page text."
    assert pages[0].char_count == len(pages[0].extracted_text)
    assert pages[0].metadata["width"] > 0
    assert pages[0].metadata["text_block_count"] == 1
    assert pages[1].page_number == 2
    assert pages[1].extracted_text.strip() == "Second page text."


def test_parser_splits_text_on_form_feed_and_preserves_characters() -> None:
    parser = DocumentParser()
    pages = parser.parse_text(b"First page.\fSecond page.\n")

    assert [page.page_number for page in pages] == [1, 2]
    assert pages[1].extracted_text == "Second page.\n"
    assert pages[1].char_count == len("Second page.\n")


def test_parser_rejects_non_utf8_text() -> None:
    with pytest.raises(DocumentParseError, match="UTF-8"):
        DocumentParser().parse_text(b"\xff\xfe")


def test_parser_requires_matching_file_extension() -> None:
    with pytest.raises(DocumentParseError, match=r"\.pdf"):
        DocumentParser().parse(b"not a pdf", "source.txt", DocumentType.PDF_ARTICLE)


def test_chunker_tracks_exact_text_offsets_and_page_bounds() -> None:
    pages = [
        DocumentPageBase(
            page_number=1,
            extracted_text="First page. " + "A useful sentence. " * 18,
            char_count=0,
        ),
        DocumentPageBase(
            page_number=2,
            extracted_text="Second page. " + "Another useful sentence. " * 18,
            char_count=0,
        ),
    ]
    document_text = "\n".join(page.extracted_text for page in pages)
    chunker = SemanticChunker(max_tokens=24, overlap_tokens=5)

    chunks = chunker.chunk(pages)

    assert len(chunks) > 2
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert any(chunk.page_start == 1 and chunk.page_end == 2 for chunk in chunks)
    for chunk in chunks:
        assert document_text[chunk.char_start : chunk.char_end] == chunk.text
        assert chunk.char_end > chunk.char_start
        assert chunk.token_count == len(
            tiktoken.get_encoding("cl100k_base").encode(chunk.text, disallowed_special=())
        )
        assert 1 <= chunk.token_count <= 24
    assert any(left.char_end > right.char_start for left, right in pairwise(chunks))


def test_chunker_handles_unicode_without_invalid_offsets() -> None:
    page = DocumentPageBase(
        page_number=1,
        extracted_text="Stories matter—especially when people share 🧡. " * 12,
        char_count=0,
    )
    chunks = SemanticChunker(max_tokens=12, overlap_tokens=2).chunk([page])

    assert chunks
    for chunk in chunks:
        assert page.extracted_text[chunk.char_start : chunk.char_end] == chunk.text
        assert "�" not in chunk.text


class DuplicateLookupQuery:
    def __init__(self, existing: dict[str, Any]) -> None:
        self.existing = existing

    def select(self, _columns: str) -> DuplicateLookupQuery:
        return self

    def eq(self, _column: str, _value: str) -> DuplicateLookupQuery:
        return self

    def maybe_single(self) -> DuplicateLookupQuery:
        return self

    async def execute(self) -> SimpleNamespace:
        return SimpleNamespace(data=self.existing)


class DuplicateLookupClient:
    def __init__(self, existing: dict[str, Any]) -> None:
        self.existing = existing
        self.storage_uploads: list[bytes] = []

    def table(self, table_name: str) -> DuplicateLookupQuery:
        assert table_name == "documents"
        return DuplicateLookupQuery(self.existing)


class FakeSupabaseQuery:
    def __init__(self, client: FakeSupabaseClient, table_name: str) -> None:
        self.client = client
        self.table_name = table_name
        self.action = "select"
        self.payload: Any = None
        self.filters: dict[str, Any] = {}
        self.single_row = False
        self.offset = 0
        self.limit: int | None = None
        self.order_by: str | None = None

    def select(self, _columns: str) -> FakeSupabaseQuery:
        return self

    def insert(self, payload: Any) -> FakeSupabaseQuery:
        self.action = "insert"
        self.payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> FakeSupabaseQuery:
        self.action = "update"
        self.payload = payload
        return self

    def delete(self) -> FakeSupabaseQuery:
        self.action = "delete"
        return self

    def eq(self, column: str, value: Any) -> FakeSupabaseQuery:
        self.filters[column] = value
        return self

    def maybe_single(self) -> FakeSupabaseQuery:
        self.single_row = True
        return self

    def single(self) -> FakeSupabaseQuery:
        self.single_row = True
        return self

    def order(self, column: str) -> FakeSupabaseQuery:
        self.order_by = column
        return self

    def range(self, start: int, end: int) -> FakeSupabaseQuery:
        self.offset = start
        self.limit = end - start + 1
        return self

    async def execute(self) -> SimpleNamespace:
        rows = self.client.tables.setdefault(self.table_name, [])
        if self.action == "insert":
            inserted = self.payload if isinstance(self.payload, list) else [self.payload]
            rows.extend(inserted)
            return SimpleNamespace(data=inserted[0] if self.single_row else inserted)
        matching = [
            row
            for row in rows
            if all(row.get(column) == value for column, value in self.filters.items())
        ]
        if self.action == "update":
            for row in matching:
                row.update(self.payload)
            return SimpleNamespace(data=matching)
        if self.action == "delete":
            self.client.tables[self.table_name] = [row for row in rows if row not in matching]
            return SimpleNamespace(data=matching)
        if self.order_by:
            matching.sort(key=lambda row: row.get(self.order_by, ""))
        if self.limit is not None:
            matching = matching[self.offset : self.offset + self.limit]
        if self.single_row:
            return SimpleNamespace(data=matching[0] if matching else None)
        return SimpleNamespace(data=matching)


class FakeStorageBucket:
    def __init__(self, storage: FakeSupabaseStorage) -> None:
        self.storage = storage

    async def upload(self, path: str, content: bytes, _options: dict[str, Any]) -> None:
        self.storage.files[path] = content

    async def remove(self, paths: list[str]) -> None:
        for path in paths:
            self.storage.files.pop(path, None)


class FakeSupabaseStorage:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    def from_(self, _bucket_name: str) -> FakeStorageBucket:
        return FakeStorageBucket(self)


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {}
        self.storage = FakeSupabaseStorage()

    def table(self, table_name: str) -> FakeSupabaseQuery:
        return FakeSupabaseQuery(self, table_name)


@pytest.mark.asyncio
async def test_ingestion_manager_rejects_duplicate_sha256_before_storage() -> None:
    content = b"same source bytes"
    existing = {
        "id": "existing-document",
        "file_hash_sha256": IngestionManager.sha256(content),
    }
    client = DuplicateLookupClient(existing)
    manager = IngestionManager(client)

    with pytest.raises(DuplicateDocumentError) as error:
        await manager.create_upload(
            content=content,
            filename="duplicate.txt",
            title="Duplicate",
            document_type=DocumentType.TXT_TRANSCRIPT,
        )

    assert error.value.document["id"] == "existing-document"
    assert client.storage_uploads == []


@pytest.mark.asyncio
async def test_ingestion_manager_uploads_and_processes_document() -> None:
    client = FakeSupabaseClient()
    manager = IngestionManager(
        client,
        chunker=SemanticChunker(max_tokens=12, overlap_tokens=2),
    )
    source = ("A story begins here. " * 20).encode()
    document, job = await manager.create_upload(
        content=source,
        filename="story.txt",
        title="A story",
        document_type=DocumentType.TXT_TRANSCRIPT,
    )

    await manager.process_document(
        document_id=document["id"],
        job_id=job["id"],
        content=source,
        filename="story.txt",
        document_type=DocumentType.TXT_TRANSCRIPT,
    )

    assert client.tables["documents"][0]["page_count"] == 1
    assert client.tables["processing_jobs"][0]["status"] == "completed"
    assert len(client.tables["document_pages"]) == 1
    assert client.tables["document_chunks"]
    assert {event["stage"] for event in client.tables["processing_job_events"]} == {
        "queued",
        "extract",
        "complete",
    }
    assert client.storage.files[document["source_file_path"]] == source


def test_upload_endpoint_queues_background_processing() -> None:
    class FakeManager:
        processed: tuple[str, str, bytes, str, DocumentType] | None = None

        def __init__(self) -> None:
            self.parser = DocumentParser()

        async def create_upload(self, **kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
            return (
                {"id": "document-1", "title": kwargs["title"]},
                {"id": "job-1", "status": "pending"},
            )

        async def process_document(
            self,
            document_id: str,
            job_id: str,
            content: bytes,
            filename: str,
            document_type: DocumentType,
        ) -> None:
            self.processed = (document_id, job_id, content, filename, document_type)

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    manager = FakeManager()
    app.dependency_overrides[get_ingestion_manager] = lambda: manager
    app.dependency_overrides[require_curator] = lambda: "curator-1"

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/documents/upload",
            data={"title": "Transcript", "document_type": "txt_transcript"},
            files={"file": ("story.txt", b"An autobiographical story.", "text/plain")},
        )

    assert response.status_code == 202
    assert response.json()["job"]["id"] == "job-1"
    assert manager.processed == (
        "document-1",
        "job-1",
        b"An autobiographical story.",
        "story.txt",
        DocumentType.TXT_TRANSCRIPT,
    )


def test_sha256_matches_standard_digest() -> None:
    assert IngestionManager.sha256(b"abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
