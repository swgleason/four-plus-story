from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.supabase import get_supabase_client, require_curator
from app.routers.discovery import get_story_boundary_scanner, router
from app.schemas.ai import (
    CandidateStoryBoundary,
    CandidateStorySegment,
    StoryBoundaryExtractionResponse,
    StoryEvaluationResponse,
)
from app.schemas.document import DocumentChunkInDB, DocumentPageBase, DocumentPageInDB
from app.services.ai.base import AIProviderError, AIRequestConfig, AIResponse, AIUsageStats
from app.services.ai.manager import AIServiceManager
from app.services.ai.mock import MockAIProvider
from app.services.ingest.chunker import SemanticChunker
from app.services.ai_pipeline.reconciler import BoundaryReconciler
from app.services.ai_pipeline.scanner import StoryBoundaryScanner

FIRST_SENTENCE = "I remember standing in that sterile waiting room when the nurse called my name."
LAST_SENTENCE = (
    "And somehow, impossibly, I found peace in that moment — not because the news was "
    "good, but because I was not alone."
)
CREATED_AT = datetime.now(UTC).isoformat()


class FakeSupabaseQuery:
    def __init__(self, client: FakeSupabase, table_name: str) -> None:
        self.client = client
        self.table_name = table_name
        self.action = "select"
        self.payload: Any = None
        self.filters: dict[str, Any] = {}
        self.membership_filters: dict[str, list[Any]] = {}
        self.single_row = False
        self.order_by: str | None = None
        self.offset = 0
        self.limit_count: int | None = None

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

    def in_(self, column: str, values: list[Any]) -> FakeSupabaseQuery:
        self.membership_filters[column] = values
        return self

    def order(self, column: str, **_kwargs: Any) -> FakeSupabaseQuery:
        self.order_by = column
        return self

    def range(self, start: int, end: int) -> FakeSupabaseQuery:
        self.offset = start
        self.limit_count = end - start + 1
        return self

    def limit(self, count: int) -> FakeSupabaseQuery:
        self.limit_count = count
        return self

    def single(self) -> FakeSupabaseQuery:
        self.single_row = True
        return self

    def maybe_single(self) -> FakeSupabaseQuery:
        self.single_row = True
        return self

    async def execute(self) -> SimpleNamespace:
        rows = self.client.tables.setdefault(self.table_name, [])
        if self.action == "insert":
            inserted = self.payload if isinstance(self.payload, list) else [self.payload]
            saved = []
            for item in inserted:
                row = dict(item)
                now = datetime.now(UTC).isoformat()
                row.setdefault("id", str(uuid4()))
                row.setdefault("created_at", now)
                if self.table_name in {"stories", "processing_jobs"}:
                    row.setdefault("updated_at", now)
                if self.table_name == "stories":
                    row.setdefault("length_advisory_exceeds_600_words", False)
                rows.append(row)
                saved.append(row)
            data: Any = saved[0] if self.single_row else saved
            return SimpleNamespace(data=data)

        matching = [
            row
            for row in rows
            if all(row.get(column) == value for column, value in self.filters.items())
            and all(row.get(column) in values for column, values in self.membership_filters.items())
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
        if self.limit_count is not None:
            matching = matching[self.offset : self.offset + self.limit_count]
        if self.single_row:
            return SimpleNamespace(data=matching[0] if matching else None)
        return SimpleNamespace(data=matching)


class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {}

    def table(self, table_name: str) -> FakeSupabaseQuery:
        return FakeSupabaseQuery(self, table_name)


def source_fixture(source: str) -> tuple[FakeSupabase, str, str]:
    client = FakeSupabase()
    document_id = str(uuid4())
    page_id = str(uuid4())
    chunk_id = str(uuid4())
    job_id = str(uuid4())
    client.tables["documents"] = [{"id": document_id}]
    client.tables["document_pages"] = [
        {
            "id": page_id,
            "document_id": document_id,
            "page_number": 1,
            "extracted_text": source,
            "char_count": len(source),
            "metadata": {},
            "created_at": CREATED_AT,
        }
    ]
    client.tables["document_chunks"] = [
        {
            "id": chunk_id,
            "document_id": document_id,
            "chunk_index": 0,
            "token_count": 1,
            "text": source,
            "page_start": 1,
            "page_end": 1,
            "char_start": 0,
            "char_end": len(source),
            "created_at": CREATED_AT,
        }
    ]
    client.tables["processing_jobs"] = [
        {
            "id": job_id,
            "document_id": document_id,
            "job_type": "story_discovery",
            "status": "pending",
            "error_message": None,
            "config": {},
            "created_at": CREATED_AT,
            "updated_at": CREATED_AT,
        }
    ]
    return client, document_id, job_id


def mock_manager() -> AIServiceManager:
    return AIServiceManager(
        primary_provider="mock",
        fallback_providers=[],
        providers={"mock": MockAIProvider()},
    )


def make_scan_source() -> str:
    return (
        "Chapter introduction. "
        + FIRST_SENTENCE
        + " My hands trembled through the long afternoon. "
        + LAST_SENTENCE
        + " A separate paragraph follows."
    )


@pytest.mark.asyncio
async def test_scanner_persists_only_verified_pending_review_story() -> None:
    source = make_scan_source()
    client, document_id, job_id = source_fixture(source)
    scanner = StoryBoundaryScanner(
        client,
        mock_manager(),
        request_config=AIRequestConfig(extra={"scenario": "success"}),
    )

    result = await scanner.scan_document(document_id, job_id)

    assert result.candidates_created == 1
    story = client.tables["stories"][0]
    start = source.index(FIRST_SENTENCE)
    end = source.index(LAST_SENTENCE) + len(LAST_SENTENCE)
    assert story["original_text"] == source[start:end]
    assert story["status"] == "discovered_pending_review"
    assert story["visibility"] == "internal_only"
    assert story["narrator_gender"] == "unknown"
    assert len(client.tables["story_source_spans"]) == 1
    assert client.tables["story_source_spans"][0]["verbatim_text"] == story["original_text"]
    assert client.tables["story_boundary_candidates"][0]["document_char_start"] == start
    assert client.tables["processing_jobs"][0]["status"] == "completed"
    assert all("text" not in event["details"] for event in client.tables["processing_job_events"])

    repeated_job_id = str(uuid4())
    client.tables["processing_jobs"].append(
        {
            "id": repeated_job_id,
            "document_id": document_id,
            "job_type": "story_discovery",
            "status": "pending",
            "config": {},
            "created_at": CREATED_AT,
            "updated_at": CREATED_AT,
        }
    )
    repeated = await StoryBoundaryScanner(
        client,
        mock_manager(),
        request_config=AIRequestConfig(extra={"scenario": "success"}),
    ).scan_document(document_id, repeated_job_id)
    assert repeated.candidates_created == 0
    assert len(client.tables["stories"]) == 1


@pytest.mark.asyncio
async def test_scanner_completes_when_mock_finds_no_candidates() -> None:
    client, document_id, job_id = source_fixture("No autobiographical story appears here.")
    scanner = StoryBoundaryScanner(
        client,
        mock_manager(),
        request_config=AIRequestConfig(extra={"scenario": "no_candidates"}),
    )

    result = await scanner.scan_document(document_id, job_id)

    assert result.candidates_proposed == 0
    assert result.candidates_created == 0
    assert client.tables.get("stories", []) == []
    assert client.tables["processing_jobs"][0]["status"] == "completed"


@pytest.mark.asyncio
async def test_scanner_logs_chunk_retry_and_succeeds(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    client, document_id, job_id = source_fixture(make_scan_source())
    provider = MockAIProvider()
    original_complete_structured = provider.complete_structured
    attempts = 0

    async def flaky_complete_structured(*args: Any, **kwargs: Any) -> Any:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise AIProviderError(
                "Gemini service unavailable",
                provider="gemini",
                status_code=503,
                retryable=True,
            )
        return await original_complete_structured(*args, **kwargs)

    monkeypatch.setattr(provider, "complete_structured", flaky_complete_structured)
    manager = AIServiceManager(
        primary_provider="mock",
        fallback_providers=[],
        providers={"mock": provider},
    )
    monkeypatch.setattr(manager, "_sleep_for_backoff", lambda _attempt: asyncio.sleep(0))

    result = await StoryBoundaryScanner(
        client,
        manager,
        request_config=AIRequestConfig(extra={"scenario": "success"}),
    ).scan_document(document_id, job_id)

    assert result.chunks_scanned == 1
    assert attempts == 3
    assert "chunk 0; retry 1/" in caplog.text
    assert "chunk 0; retry 2/" in caplog.text
    assert client.tables["processing_jobs"][0]["status"] == "completed"


@pytest.mark.asyncio
async def test_scanner_persists_descriptive_error_after_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, document_id, job_id = source_fixture(make_scan_source())
    provider = MockAIProvider()
    attempts = 0

    async def always_unavailable(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal attempts
        attempts += 1
        raise AIProviderError(
            "Gemini returned 503 Service Unavailable",
            provider="gemini",
            status_code=503,
            retryable=True,
        )

    monkeypatch.setattr(provider, "complete_structured", always_unavailable)
    manager = AIServiceManager(
        primary_provider="mock",
        fallback_providers=[],
        providers={"mock": provider},
    )
    monkeypatch.setattr(manager, "_sleep_for_backoff", lambda _attempt: asyncio.sleep(0))
    scanner = StoryBoundaryScanner(client, manager)

    with pytest.raises(AIProviderError, match="503 Service Unavailable"):
        await scanner.scan_document(document_id, job_id)

    assert attempts == manager.max_retries + 1
    job = client.tables["processing_jobs"][0]
    assert job["status"] == "failed"
    assert "503 Service Unavailable" in job["error_message"]


@pytest.mark.asyncio
async def test_mock_uncertain_evaluation_is_structurally_validated() -> None:
    manager = mock_manager()
    response = await manager.complete_structured(
        system_prompt="Evaluate the story.",
        user_prompt="When the rejection letter arrived, I set it down quietly.",
        response_schema=StoryEvaluationResponse,
        config=AIRequestConfig(extra={"scenario": "uncertain"}),
    )

    evaluation = StoryEvaluationResponse.model_validate_json(response.content)
    assert evaluation.overall_classification.value == "uncertain_needs_review"
    assert evaluation.narrator_gender.value == "unknown"


def make_page(text: str, page_number: int = 1, document_id: str | None = None) -> DocumentPageInDB:
    return DocumentPageInDB(
        id=uuid4(),
        document_id=document_id or str(uuid4()),
        page_number=page_number,
        extracted_text=text,
        char_count=len(text),
        metadata={},
        created_at=datetime.now(UTC),
    )


def make_chunk(text: str, start: int = 0) -> DocumentChunkInDB:
    return DocumentChunkInDB(
        id=uuid4(),
        document_id=uuid4(),
        chunk_index=0,
        token_count=1,
        text=text,
        page_start=1,
        page_end=1,
        char_start=start,
        char_end=start + len(text),
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_scanner_preserves_story_spanning_chunk_edge() -> None:
    first_sentence = "I remember the moment my sister reached for my hand."
    last_sentence = "Together, we found the courage to walk back inside."
    story = (
        f"{first_sentence}\n\n"
        + "My hands trembled as my sister sat with me and listened. " * 16
        + f"\n\n{last_sentence}"
    )
    source = "preamble " * 700 + story + " conclusion " * 800
    chunk_bases = SemanticChunker(max_tokens=800).chunk(
        [DocumentPageBase(page_number=1, extracted_text=source, char_count=len(source))]
    )
    story_start = source.index(story)
    story_end = story_start + len(story)
    assert any(
        chunk.char_start < story_start < chunk.char_end < story_end
        for chunk in chunk_bases
    )
    assert any(
        chunk.char_start <= story_start and chunk.char_end >= story_end
        for chunk in chunk_bases
    )

    client, document_id, job_id = source_fixture(source)
    client.tables["document_chunks"] = [
        {
            "id": str(uuid4()),
            "document_id": document_id,
            "chunk_index": chunk.chunk_index,
            "token_count": chunk.token_count,
            "text": chunk.text,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
            "char_start": chunk.char_start,
            "char_end": chunk.char_end,
            "created_at": CREATED_AT,
        }
        for chunk in chunk_bases
    ]

    class BoundaryProvider(MockAIProvider):
        async def complete_structured(
            self,
            system_prompt: str,
            user_prompt: str,
            response_schema: type[BaseModel],
            config: AIRequestConfig | None = None,
        ) -> AIResponse:
            candidates = []
            if first_sentence in user_prompt and last_sentence in user_prompt:
                candidates.append(
                    CandidateStoryBoundary(
                        tentative_title="A story across a chunk edge",
                        first_sentence=first_sentence,
                        last_sentence=last_sentence,
                        approx_char_start=user_prompt.index(first_sentence),
                        approx_char_end=(
                            user_prompt.index(last_sentence) + len(last_sentence)
                        ),
                        evidence_quote=first_sentence,
                    )
                )
            extraction = StoryBoundaryExtractionResponse(
                has_candidates=bool(candidates),
                candidates=candidates,
            )
            return AIResponse(
                content=extraction.model_dump_json(),
                usage=AIUsageStats(provider_name=self.provider_name),
            )

    scanner = StoryBoundaryScanner(
        client,
        AIServiceManager(
            primary_provider="mock",
            fallback_providers=[],
            providers={"mock": BoundaryProvider()},
        ),
    )

    result = await scanner.scan_document(document_id, job_id)

    assert result.candidates_created == 1
    assert client.tables["stories"][0]["original_text"] == story


def test_reconciler_reconstructs_non_contiguous_story_without_sidebar() -> None:
    page = make_page(
        "I felt afraid. I called my sister. SIDEBAR: unrelated news. "
        "Later, I asked for help. We found a way forward."
    )
    chunk = make_chunk(page.extracted_text)
    candidate = CandidateStoryBoundary(
        tentative_title="A story through interruption",
        first_sentence="I felt afraid.",
        last_sentence="We found a way forward.",
        approx_char_start=0,
        approx_char_end=40,
        evidence_quote="I felt afraid.",
        source_segments=[
            CandidateStorySegment(
                first_sentence="I felt afraid.",
                last_sentence="I called my sister.",
                approx_char_start=0,
                approx_char_end=40,
            ),
            CandidateStorySegment(
                first_sentence="Later, I asked for help.",
                last_sentence="We found a way forward.",
                approx_char_start=65,
                approx_char_end=len(page.extracted_text),
            ),
        ],
    )

    verified = BoundaryReconciler().reconcile(candidate, chunk, [page], [chunk])

    assert verified is not None
    assert verified.text == (
        "I felt afraid. I called my sister.\nLater, I asked for help. We found a way forward."
    )
    assert "SIDEBAR" not in verified.text
    assert [span.span_order for span in verified.source_spans] == [1, 2]
    assert all(span.document_page_id == page.id for span in verified.source_spans)


def test_reconciler_splits_verified_story_across_page_break() -> None:
    document_id = str(uuid4())
    pages = [
        make_page("The chapter began. I felt afraid.", 1, document_id),
        make_page("I asked for help, and we found peace. The story ends.", 2, document_id),
    ]
    text = "\n".join(page.extracted_text for page in pages)
    chunk = make_chunk(text)
    candidate = CandidateStoryBoundary(
        tentative_title="Across pages",
        first_sentence="I felt afraid.",
        last_sentence="I asked for help, and we found peace.",
        approx_char_start=0,
        approx_char_end=len(text),
        evidence_quote="I felt afraid.",
    )

    verified = BoundaryReconciler().reconcile(candidate, chunk, pages, [chunk])

    assert verified is not None
    assert verified.text == "I felt afraid.\nI asked for help, and we found peace."
    assert [span.page_number for span in verified.source_spans] == [1, 2]
    assert [span.verbatim_text for span in verified.source_spans] == [
        "I felt afraid.",
        "I asked for help, and we found peace.",
    ]


def test_reconciler_accepts_single_sentence_story_boundaries() -> None:
    page = make_page("A complete story in one sentence.")
    chunk = make_chunk(page.extracted_text)
    candidate = CandidateStoryBoundary(
        tentative_title="One sentence",
        first_sentence=page.extracted_text,
        last_sentence=page.extracted_text,
        approx_char_start=0,
        approx_char_end=len(page.extracted_text),
        evidence_quote=page.extracted_text,
    )

    verified = BoundaryReconciler().reconcile(candidate, chunk, [page], [chunk])

    assert verified is not None
    assert verified.text == page.extracted_text
    assert len(verified.source_spans) == 1


def test_reconciler_rejects_unverifiable_ai_anchors() -> None:
    page = make_page("The source does not contain these boundary sentences.")
    chunk = make_chunk(page.extracted_text)
    candidate = CandidateStoryBoundary(
        tentative_title="Unsupported",
        first_sentence="I remember a different event.",
        last_sentence="The invented story ended happily.",
        approx_char_start=0,
        approx_char_end=20,
        evidence_quote="I remember",
    )

    assert BoundaryReconciler().reconcile(candidate, chunk, [page], [chunk]) is None


def test_discovery_endpoints_queue_scan_and_return_review_candidates() -> None:
    source = make_scan_source()
    client, document_id, _job_id = source_fixture(source)
    scanner = StoryBoundaryScanner(
        client,
        mock_manager(),
        request_config=AIRequestConfig(extra={"scenario": "success"}),
    )
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_supabase_client] = lambda: client
    app.dependency_overrides[require_curator] = lambda: "curator-1"
    app.dependency_overrides[get_story_boundary_scanner] = lambda: scanner

    with TestClient(app) as test_client:
        queued = test_client.post(f"/api/v1/documents/{document_id}/scan")
        candidates = test_client.get(f"/api/v1/documents/{document_id}/candidates")

    assert queued.status_code == 202
    assert queued.json()["job"]["job_type"] == "story_discovery"
    assert candidates.status_code == 200
    assert len(candidates.json()) == 1
    assert candidates.json()[0]["story"]["status"] == "discovered_pending_review"
    assert candidates.json()[0]["story"]["visibility"] == "internal_only"
