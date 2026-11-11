from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.supabase import get_supabase_client, require_curator
from app.routers.admin import router


class Query:
    def __init__(self, client: FakeSupabase, table: str) -> None:
        self.client = client
        self.table_name = table
        self.action = "select"
        self.payload: Any = None
        self.filters: list[tuple[str, str, Any]] = []
        self.order_by: str | None = None
        self.desc = False
        self.start = 0
        self.end: int | None = None
        self.one = False

    def select(self, _columns: str) -> Query:
        return self

    def eq(self, column: str, value: Any) -> Query:
        self.filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> Query:
        self.filters.append(("in", column, values))
        return self

    def is_(self, column: str, value: Any) -> Query:
        self.filters.append(("is", column, value))
        return self

    def order(self, column: str, desc: bool = False, **_kwargs: Any) -> Query:
        self.order_by = column
        self.desc = desc
        return self

    def range(self, start: int, end: int) -> Query:
        self.start, self.end = start, end
        return self

    def limit(self, count: int) -> Query:
        self.end = self.start + count - 1
        return self

    def maybe_single(self) -> Query:
        self.one = True
        return self

    def single(self) -> Query:
        self.one = True
        return self

    def insert(self, payload: dict[str, Any]) -> Query:
        self.action, self.payload = "insert", payload
        return self

    def update(self, payload: dict[str, Any]) -> Query:
        self.action, self.payload = "update", payload
        return self

    async def execute(self) -> SimpleNamespace:
        rows = self.client.tables.setdefault(self.table_name, [])
        if self.action == "insert":
            saved = dict(self.payload)
            saved.setdefault("id", str(uuid4()))
            saved.setdefault("created_at", datetime.now(UTC).isoformat())
            saved.setdefault("updated_at", datetime.now(UTC).isoformat())
            rows.append(saved)
            return SimpleNamespace(data=saved if self.one else [saved])

        matched = [row for row in rows if self._matches(row)]
        if self.action == "update":
            for row in matched:
                row.update(self.payload)
            return SimpleNamespace(data=matched[0] if self.one and matched else matched)

        if self.order_by:
            order_by = self.order_by
            matched.sort(key=lambda row: row.get(order_by) or "", reverse=self.desc)
        if self.end is not None:
            matched = matched[self.start : self.end + 1]
        if self.one:
            return SimpleNamespace(data=matched[0] if matched else None)
        return SimpleNamespace(data=matched)

    def _matches(self, row: dict[str, Any]) -> bool:
        for operation, column, value in self.filters:
            if operation == "eq" and row.get(column) != value:
                return False
            if operation == "in" and row.get(column) not in value:
                return False
            if operation == "is" and row.get(column) is not value:
                return False
        return True


class FakeSupabase:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self.tables = tables

    def table(self, name: str) -> Query:
        return Query(self, name)

    def rpc(self, name: str, params: dict[str, Any]) -> FakeRPC:
        return FakeRPC(self, name, params)


class FakeRPC:
    def __init__(self, client: FakeSupabase, name: str, params: dict[str, Any]) -> None:
        self.client = client
        self.name = name
        self.params = params

    async def execute(self) -> SimpleNamespace:
        if self.name == "admin_save_curated_draft":
            return await self._save_curated_draft()
        assert self.name == "admin_review_story"
        story = next(
            row
            for row in self.client.tables["stories"]
            if row["id"] == self.params["p_story_id"]
        )
        previous = dict(story)
        story.update(
            status="approved" if self.params["p_action"] in {"approve", "edit_and_approve"} else (
                "rejected" if self.params["p_action"] == "reject" else "under_review"
            ),
            visibility=self.params["p_visibility"]
            if self.params["p_action"] in {"approve", "edit_and_approve"}
            else "internal_only",
            approved_by_user_id=self.params["p_reviewer_user_id"]
            if self.params["p_action"] in {"approve", "edit_and_approve"}
            else None,
            approved_at=datetime.now(UTC).isoformat()
            if self.params["p_action"] in {"approve", "edit_and_approve"}
            else None,
        )
        if self.params.get("p_override_title"):
            story["title"] = self.params["p_override_title"]
        self.client.tables.setdefault("story_human_reviews", []).append(
            {
                "story_id": story["id"],
                "reviewer_user_id": self.params["p_reviewer_user_id"],
                "action": self.params["p_action"],
                "previous_state": previous,
                "new_state": dict(story),
                "reviewer_notes": self.params.get("p_notes"),
            }
        )
        return SimpleNamespace(
            data={
                "story_id": story["id"],
                "status": story["status"],
                "visibility": story["visibility"],
                "approved_at": story["approved_at"],
                "approved_by_user_id": story["approved_by_user_id"],
            }
        )

    async def _save_curated_draft(self) -> SimpleNamespace:
        word_count = len(self.params["p_curated_text"].split())
        version = {
            "id": str(uuid4()),
            "story_id": self.params["p_story_id"],
            "curated_title": self.params["p_curated_title"],
            "curated_text": self.params["p_curated_text"],
            "curated_word_count": word_count,
            "curated_spoken_duration_seconds": (word_count * 60 + 139) // 140,
            "editorial_notes": self.params["p_editorial_notes"],
            "is_approved": False,
            "length_advisory_exceeds_800_words": word_count > 800,
        }
        self.client.tables.setdefault("story_curated_versions", []).append(version)
        self.client.tables.setdefault("story_human_reviews", []).append(
            {
                "story_id": self.params["p_story_id"],
                "reviewer_user_id": self.params["p_reviewer_user_id"],
                "action": "curate_version",
                "new_state": version,
            }
        )
        return SimpleNamespace(data=version)


def _client(tables: dict[str, list[dict[str, Any]]]) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    client = FakeSupabase(tables)
    app.dependency_overrides[get_supabase_client] = lambda: client
    app.dependency_overrides[require_curator] = lambda: str(uuid4())
    return TestClient(app)


def test_jobs_endpoint_includes_document_title_and_audit_events() -> None:
    job_id, document_id = str(uuid4()), str(uuid4())
    with _client(
        {
            "processing_jobs": [
                {
                    "id": job_id,
                    "document_id": document_id,
                    "job_type": "pdf_extraction",
                    "status": "processing",
                    "created_at": "2026-11-08T10:00:00Z",
                }
            ],
            "documents": [{"id": document_id, "title": "Source book"}],
            "processing_job_events": [
                {
                    "id": str(uuid4()),
                    "job_id": job_id,
                    "stage": "extract",
                    "message": "Extracting pages",
                    "created_at": "2026-11-08T10:01:00Z",
                }
            ],
        }
    ) as client:
        response = client.get("/api/v1/admin/jobs")

    assert response.status_code == 200
    assert response.json()[0]["document_title"] == "Source book"
    assert response.json()[0]["events"][0]["message"] == "Extracting pages"


def test_review_queue_returns_multispan_source_and_analysis() -> None:
    story_id, document_id = str(uuid4()), str(uuid4())
    span_id = str(uuid4())
    with _client(
        {
            "stories": [
                {
                    "id": story_id,
                    "document_id": document_id,
                    "status": "under_review",
                    "title": "Across pages",
                }
            ],
            "documents": [{"id": document_id, "title": "Source", "rights_status": "licensed"}],
            "story_source_spans": [
                {
                    "id": span_id,
                    "story_id": story_id,
                    "span_order": 2,
                    "page_number": 12,
                    "verbatim_text": "The closing source passage.",
                }
            ],
            "story_ai_evaluations": [
                {"id": str(uuid4()), "story_id": story_id, "overall_classification": "confirmed_4_plus"}
            ],
            "story_boundary_candidates": [],
            "story_step_analyses": [
                {"id": str(uuid4()), "story_id": story_id, "setting": "In a hospital"}
            ],
            "story_variant_assignments": [],
            "story_emotions": [],
        }
    ) as client:
        response = client.get("/api/v1/admin/review-queue")

    assert response.status_code == 200
    item = response.json()[0]
    assert item["spans"][0]["verbatim_text"] == "The closing source passage."
    assert item["evaluation"]["overall_classification"] == "confirmed_4_plus"
    assert item["step_analysis"]["setting"] == "In a hospital"


def test_review_approval_requires_cleared_document_rights() -> None:
    story_id, document_id = str(uuid4()), str(uuid4())
    tables: dict[str, list[dict[str, Any]]] = {
        "stories": [
            {
                "id": story_id,
                "document_id": document_id,
                "status": "discovered_pending_review",
                "visibility": "internal_only",
                "title": "Story title",
            }
        ],
        "documents": [
            {
                "id": document_id,
                "rights_status": "restricted_internal",
                "publication_restrictions": None,
            }
        ],
        "story_human_reviews": [],
    }
    with _client(tables) as client:
        response = client.post(
            f"/api/v1/admin/stories/{story_id}/review",
            json={"action": "approve", "visibility": "public"},
        )

    assert response.status_code == 409
    assert tables["stories"][0]["status"] == "discovered_pending_review"
    assert tables["story_human_reviews"] == []


def test_review_approval_records_audit_and_preserves_internal_default() -> None:
    story_id, document_id = str(uuid4()), str(uuid4())
    tables: dict[str, list[dict[str, Any]]] = {
        "stories": [
            {
                "id": story_id,
                "document_id": document_id,
                "status": "discovered_pending_review",
                "visibility": "internal_only",
                "title": "Story title",
            }
        ],
        "documents": [
            {"id": document_id, "rights_status": "licensed", "publication_restrictions": None}
        ],
        "story_human_reviews": [],
    }
    with _client(tables) as client:
        response = client.post(
            f"/api/v1/admin/stories/{story_id}/review",
            json={
                "action": "approve",
                "visibility": "registered_users",
                "notes": "Rights confirmed",
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert response.json()["visibility"] == "registered_users"
    assert tables["story_human_reviews"][0]["reviewer_notes"] == "Rights confirmed"


def test_curated_draft_metrics_are_computed_and_left_unapproved() -> None:
    story_id = str(uuid4())
    body = {
        "curated_title": "A telling",
        "curated_text": " ".join(["word"] * 801),
        "editorial_notes": "Trim before sharing",
    }
    tables: dict[str, list[dict[str, Any]]] = {
        "stories": [{"id": story_id}],
        "story_curated_versions": [],
    }
    with _client(tables) as client:
        response = client.post(f"/api/v1/admin/stories/{story_id}/curated", json=body)

    assert response.status_code == 200
    assert response.json()["curated_word_count"] == 801
    assert response.json()["curated_spoken_duration_seconds"] == 344
    assert response.json()["length_advisory_exceeds_800_words"] is True
    assert response.json()["is_approved"] is False
    assert tables["story_human_reviews"][0]["action"] == "curate_version"
