from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.supabase import get_supabase_client, require_curator
from app.routers.stories import get_story_evaluator, router
from app.schemas.enums import StoryStatus, StoryVisibility
from app.schemas.story import StoryInDB
from app.services.ai.base import AIRequestConfig, AIResponse
from app.services.ai.manager import AIServiceManager
from app.services.ai.mock import MockAIProvider
from app.services.ai_pipeline.evaluator import StoryEvaluator

NOW = datetime.now(UTC).isoformat()
SOURCE_TEXT = """I remember standing in that sterile waiting room when the nurse called my name.
My hands were trembling but I was still present, still able to hear.
My hands were trembling, tears blurring my vision, a knot tightening in my stomach.
I whispered 'I can't do this alone' and felt a presence, steady and warm, hold me.
And somehow, impossibly, I found peace — not because the news was good, but because I was not alone.
And somehow, impossibly, I found peace in that moment — not because the news was good, but because I was not alone.
I found peace in that moment — not because the news was good, but because I was not alone.
My hands were trembling, tears blurring my vision.
I found peace in that moment."""


class FakeSupabaseQuery:
    def __init__(self, client: FakeSupabase, table_name: str) -> None:
        self.client = client
        self.table_name = table_name
        self.action = "select"
        self.payload: Any = None
        self.filters: dict[str, Any] = {}
        self.single_row = False
        self.order_by: str | None = None
        self.descending = False
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

    def order(self, column: str, desc: bool = False, **_kwargs: Any) -> FakeSupabaseQuery:
        self.order_by = column
        self.descending = desc
        return self

    def limit(self, count: int) -> FakeSupabaseQuery:
        self.limit_count = count
        return self

    def range(self, start: int, end: int) -> FakeSupabaseQuery:
        self.offset = start
        self.limit_count = end - start + 1
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
            payloads = self.payload if isinstance(self.payload, list) else [self.payload]
            inserted = []
            for payload in payloads:
                row = dict(payload)
                now = datetime.now(UTC).isoformat()
                row.setdefault("id", str(uuid4()))
                row.setdefault("created_at", now)
                if self.table_name in {
                    "stories",
                    "processing_jobs",
                    "story_step_analyses",
                }:
                    row.setdefault("updated_at", now)
                if self.table_name == "stories":
                    row.setdefault("length_advisory_exceeds_600_words", False)
                rows.append(row)
                inserted.append(row)
            return SimpleNamespace(data=inserted[0] if self.single_row else inserted)

        matching = [
            row
            for row in rows
            if all(row.get(column) == value for column, value in self.filters.items())
        ]
        if self.action == "update":
            for row in matching:
                row.update(self.payload)
            return SimpleNamespace(data=matching[0] if self.single_row and matching else matching)
        if self.action == "delete":
            self.client.tables[self.table_name] = [row for row in rows if row not in matching]
            return SimpleNamespace(data=matching)
        if self.order_by:
            matching.sort(key=lambda row: row.get(self.order_by, ""), reverse=self.descending)
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


def make_story(client: FakeSupabase) -> StoryInDB:
    story_id = str(uuid4())
    document_id = str(uuid4())
    client.tables["stories"] = [
        {
            "id": story_id,
            "document_id": document_id,
            "title": "Discovered story",
            "original_text": SOURCE_TEXT,
            "original_word_count": len(SOURCE_TEXT.split()),
            "estimated_spoken_duration_seconds": 200,
            "length_advisory_exceeds_600_words": False,
            "is_autobiographical": None,
            "narrator_gender": "unknown",
            "status": StoryStatus.DISCOVERED_PENDING_REVIEW.value,
            "visibility": StoryVisibility.INTERNAL_ONLY.value,
            "approved_by_user_id": None,
            "approved_at": None,
            "created_at": NOW,
            "updated_at": NOW,
        }
    ]
    client.tables["processing_jobs"] = []
    client.tables["processing_job_events"] = []
    return StoryInDB.model_validate(client.tables["stories"][0])


def mock_manager() -> AIServiceManager:
    return AIServiceManager(
        primary_provider="mock",
        fallback_providers=[],
        providers={"mock": MockAIProvider()},
    )


def make_evaluator(client: FakeSupabase, scenario: str = "success") -> StoryEvaluator:
    return StoryEvaluator(
        client,
        mock_manager(),
        request_config=AIRequestConfig(extra={"scenario": scenario}),
    )


@pytest.mark.asyncio
async def test_evaluator_persists_rubric_variants_emotions_and_step() -> None:
    client = FakeSupabase()
    story = make_story(client)
    job_id = str(uuid4())
    client.tables["processing_jobs"].append(
        {
            "id": job_id,
            "document_id": str(story.document_id),
            "job_type": "story_evaluation",
            "status": "pending",
        }
    )

    result = await make_evaluator(client).evaluate_story(story, job_id)

    assert result.evaluation.overall_classification.value == "confirmed_4_plus"
    assert (
        result.evaluation.criteria_evaluations.explicit_emotion_and_body_sensations.result.value
        == "met"
    )
    assert len(result.variants) == 1
    assert result.variants[0].variant.value == "return_to_joy"
    assert {emotion.emotion.value for emotion in result.emotions} == {"fear", "peace"}
    assert result.emotions[0].energy_level.value == "high_energy"
    assert result.emotions[1].energy_level.value == "positive_connective"
    assert result.step_analysis.setting
    assert client.tables["stories"][0]["is_autobiographical"] is True
    assert client.tables["stories"][0]["status"] == "discovered_pending_review"
    assert client.tables["stories"][0]["visibility"] == "internal_only"
    assert client.tables["processing_jobs"][0]["status"] == "completed"
    assert (
        client.tables["story_ai_evaluations"][0]["criteria_evaluations"][
            "explicit_emotion_and_body_sensations"
        ]["sensations_missing"]
        is False
    )


class HallucinatedSomaticProvider(MockAIProvider):
    async def complete_structured(self, *args: Any, **kwargs: Any) -> AIResponse:
        response = await super().complete_structured(*args, **kwargs)
        payload = json.loads(response.content)
        criterion = payload["criteria_breakdown"]["explicit_emotion_and_body_sensations"]
        criterion["sensations_identified"] = ["ice-cold fingertips"]
        criterion["sensations_missing"] = False
        payload["emotions"][0]["energy_level"] = "low_energy"
        for emotion in payload["emotions"]:
            emotion["sensations_identified"] = ["ice-cold fingertips"]
            emotion["sensations_missing"] = False
        return AIResponse(content=json.dumps(payload), usage=response.usage)


@pytest.mark.asyncio
async def test_evaluator_removes_unsubstantiated_sensations_and_marks_missing() -> None:
    client = FakeSupabase()
    story = make_story(client)
    job_id = str(uuid4())
    client.tables["processing_jobs"].append({"id": job_id, "status": "pending"})
    manager = AIServiceManager(
        primary_provider="mock",
        fallback_providers=[],
        providers={"mock": HallucinatedSomaticProvider()},
    )
    evaluator = StoryEvaluator(
        client,
        manager,
        request_config=AIRequestConfig(extra={"scenario": "success"}),
    )

    result = await evaluator.evaluate_story(story, job_id)

    criterion = result.evaluation.criteria_evaluations.explicit_emotion_and_body_sensations
    assert criterion.sensations_identified == []
    assert criterion.sensations_missing is True
    assert all(not emotion.sensations_identified for emotion in result.emotions)
    assert all(emotion.sensations_missing for emotion in result.emotions)
    assert result.emotions[0].energy_level.value == "high_energy"
    assert all(
        "ice-cold fingertips" not in row["sensations_identified"]
        for row in client.tables["story_emotions"]
    )


@pytest.mark.asyncio
async def test_uncertain_evaluation_remains_separate_from_variants() -> None:
    client = FakeSupabase()
    story = make_story(client)
    uncertain_text = (
        "When the rejection letter arrived, I set it down quietly. "
        "I told myself it was fine. These things happen. "
        "I sat with the feeling by myself for a while. "
        "I think I learned something about resilience, eventually."
    )
    story.original_text = uncertain_text
    client.tables["stories"][0]["original_text"] = uncertain_text
    job_id = str(uuid4())
    client.tables["processing_jobs"].append({"id": job_id, "status": "pending"})

    result = await make_evaluator(client, "uncertain").evaluate_story(story, job_id)

    assert result.evaluation.overall_classification.value == "uncertain_needs_review"
    assert result.variants == []
    assert result.story.status == StoryStatus.DISCOVERED_PENDING_REVIEW
    assert result.story.visibility == StoryVisibility.INTERNAL_ONLY


def test_story_evaluation_endpoints_queue_and_inspect_analysis() -> None:
    client = FakeSupabase()
    story = make_story(client)
    evaluator = make_evaluator(client)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_supabase_client] = lambda: client
    app.dependency_overrides[require_curator] = lambda: "curator-1"
    app.dependency_overrides[get_story_evaluator] = lambda: evaluator

    with TestClient(app) as test_client:
        queued = test_client.post(f"/api/v1/stories/{story.id}/evaluate")
        detail = test_client.get(f"/api/v1/stories/{story.id}/evaluation")

    assert queued.status_code == 202
    assert queued.json()["job"]["job_type"] == "story_evaluation"
    assert detail.status_code == 200
    assert detail.json()["evaluation"]["overall_classification"] == "confirmed_4_plus"
    assert (
        detail.json()["evaluation"]["criteria_evaluations"]["redemptive_outcome"]["result"] == "met"
    )
    assert detail.json()["variants"][0]["variant"] == "return_to_joy"
    assert detail.json()["step_analysis"]["setting"]
    assert detail.json()["story"]["status"] == "discovered_pending_review"


class HallucinatedEvidenceProvider(MockAIProvider):
    async def complete_structured(self, *args: Any, **kwargs: Any) -> AIResponse:
        response = await super().complete_structured(*args, **kwargs)
        payload = json.loads(response.content)
        payload["assigned_variants"][0]["evidence_quote"] = "A quote not in the source."
        return AIResponse(content=json.dumps(payload), usage=response.usage)


@pytest.mark.asyncio
async def test_evaluator_fails_job_for_unsupported_evidence() -> None:
    client = FakeSupabase()
    story = make_story(client)
    job_id = str(uuid4())
    client.tables["processing_jobs"].append({"id": job_id, "status": "pending"})
    manager = AIServiceManager(
        primary_provider="mock",
        fallback_providers=[],
        providers={"mock": HallucinatedEvidenceProvider()},
    )
    evaluator = StoryEvaluator(
        client,
        manager,
        request_config=AIRequestConfig(extra={"scenario": "success"}),
    )

    with pytest.raises(ValueError, match="not present verbatim"):
        await evaluator.evaluate_story(story, job_id)

    assert client.tables["processing_jobs"][0]["status"] == "failed"
    assert client.tables.get("story_ai_evaluations", []) == []
