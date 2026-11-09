from __future__ import annotations

import math
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from app.core.supabase import get_supabase_client
from app.routers.search import get_search_engine, get_search_user_role, router
from app.schemas.enums import EmotionType, StoryVariant, UserRole
from app.schemas.search import HybridSearchRequest
from app.services.search.embedder import StoryEmbedder
from app.services.search.embeddings import EmbeddingProvider, EmbeddingResponse
from app.services.search.engine import (
    HybridSearchEngine,
    can_access_story,
    reciprocal_rank_fusion,
)


class FakeEmbeddingProvider(EmbeddingProvider):
    def __init__(self, vector: list[float] | None = None) -> None:
        self.vector = vector or [1.0] + [0.0] * 1535
        self.inputs: list[str] = []
        self.initialized = 0
        self.closed = 0

    async def initialize(self) -> None:
        self.initialized += 1

    async def close(self) -> None:
        self.closed += 1

    async def embed(self, text: str, model_name: str, dimension: int) -> EmbeddingResponse:
        self.inputs.append(text)
        vector = self.vector[:dimension]
        return EmbeddingResponse(vector, model_name, model_name)


class FakeQuery:
    def __init__(self, client: FakeSearchSupabase, table: str) -> None:
        self.client = client
        self.table_name = table
        self.action = "select"
        self.payload: Any = None
        self.filters: dict[str, Any] = {}
        self.order_by: str | None = None
        self.desc = False
        self.offset = 0
        self.limit_count: int | None = None
        self.single = False

    def select(self, _columns: str) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self.filters[column] = value
        return self

    def order(self, column: str, desc: bool = False, **_kwargs: Any) -> FakeQuery:
        self.order_by = column
        self.desc = desc
        return self

    def range(self, start: int, end: int) -> FakeQuery:
        self.offset = start
        self.limit_count = end - start + 1
        return self

    def limit(self, count: int) -> FakeQuery:
        self.limit_count = count
        return self

    def maybe_single(self) -> FakeQuery:
        self.single = True
        return self

    def upsert(self, payload: dict[str, Any], **_kwargs: Any) -> FakeQuery:
        self.action = "upsert"
        self.payload = payload
        return self

    async def execute(self) -> SimpleNamespace:
        rows = self.client.tables.setdefault(self.table_name, [])
        if self.action == "upsert":
            existing = next(
                (
                    row
                    for row in rows
                    if all(
                        row.get(key) == self.payload.get(key)
                        for key in ("story_id", "embedding_type", "embedding_model")
                    )
                ),
                None,
            )
            if existing:
                existing.update(self.payload)
                return SimpleNamespace(data=existing)
            saved = dict(self.payload)
            saved.setdefault("id", str(uuid4()))
            saved.setdefault("created_at", datetime.now(UTC).isoformat())
            rows.append(saved)
            return SimpleNamespace(data=saved)
        matching = [
            row
            for row in rows
            if all(row.get(column) == value for column, value in self.filters.items())
        ]
        order_by = self.order_by
        if order_by:
            matching.sort(key=lambda row: row.get(order_by, ""), reverse=self.desc)
        if self.limit_count is not None:
            matching = matching[self.offset : self.offset + self.limit_count]
        if self.single:
            return SimpleNamespace(data=matching[0] if matching else None)
        return SimpleNamespace(data=matching)


class FakeRPC:
    def __init__(self, client: FakeSearchSupabase, name: str, params: dict[str, Any]) -> None:
        self.client = client
        self.name = name
        self.params = params

    async def execute(self) -> SimpleNamespace:
        assert self.name == "hybrid_story_search"
        self.client.rpc_calls.append(self.params)
        assert self.params["requested_embedding_model"]
        query = self.params["query_text"].casefold()
        query_vector = _vector(self.params["query_embedding"])
        include_registered = self.params["include_registered"]
        accessible = [
            row
            for row in self.client.search_rows
            if row["status"] == "approved"
            and row["rights_status"] in {"public_domain", "licensed", "fair_use_educational"}
            and not row.get("publication_restrictions")
            and (
                row["visibility"] == "public"
                or (include_registered and row["visibility"] == "registered_users")
            )
            and (
                self.params.get("filter_variant") is None
                or self.params["filter_variant"] in row.get("variants", [])
            )
            and (
                self.params.get("filter_emotion") is None
                or self.params["filter_emotion"] in row.get("emotions", [])
            )
        ]
        sparse_rank = {
            row["story_id"]: rank
            for rank, row in enumerate(
                sorted(
                    (row for row in accessible if query in row["search_text"].casefold()),
                    key=lambda row: row["story_id"],
                ),
                start=1,
            )
        }
        dense_rank = {
            row["story_id"]: rank
            for rank, row in enumerate(
                sorted(
                    accessible,
                    key=lambda row: _cosine_distance(
                        query_vector, _vector(row["embedding"])
                    ),
                ),
                start=1,
            )
        }
        matched_ids = set(sparse_rank) | set(dense_rank)
        ranked = sorted(
            (row for row in accessible if row["story_id"] in matched_ids),
            key=lambda row: (
                -reciprocal_rank_fusion(
                    sparse_rank.get(row["story_id"]),
                    dense_rank.get(row["story_id"]),
                ),
                row["story_id"],
            ),
        )
        total = len(ranked)
        offset = self.params.get("result_offset", 0)
        limit = self.params.get("match_count", 20)
        results = [
            {
                "story_id": row["story_id"],
                "title": row["title"],
                "original_text": row["original_text"],
                "original_word_count": row["original_word_count"],
                "estimated_spoken_duration_seconds": row["estimated_spoken_duration_seconds"],
                "length_advisory_exceeds_600_words": row[
                    "length_advisory_exceeds_600_words"
                ],
                "sparse_rank": sparse_rank.get(row["story_id"]),
                "dense_rank": dense_rank.get(row["story_id"]),
                "rrf_score": reciprocal_rank_fusion(
                    sparse_rank.get(row["story_id"]),
                    dense_rank.get(row["story_id"]),
                ),
                "total_matched": total,
            }
            for row in ranked[offset : offset + limit]
        ]
        return SimpleNamespace(data=results)


class FakeSearchSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {}
        self.search_rows: list[dict[str, Any]] = []
        self.rpc_calls: list[dict[str, Any]] = []
        self.auth: Any = None

    def table(self, table_name: str) -> FakeQuery:
        return FakeQuery(self, table_name)

    def rpc(self, name: str, params: dict[str, Any]) -> FakeRPC:
        return FakeRPC(self, name, params)


def _vector(value: str) -> list[float]:
    return [float(part) for part in value.strip("[]").split(",")]


def _cosine_distance(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(item * item for item in left))
    right_norm = math.sqrt(sum(item * item for item in right))
    return 1 - dot / (left_norm * right_norm)


def _search_row(
    *,
    search_text: str,
    vector: list[float],
    status: str = "approved",
    visibility: str = "public",
    rights_status: str = "licensed",
    restrictions: str | None = None,
    variants: list[str] | None = None,
    emotions: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "story_id": str(uuid4()),
        "title": "Search story",
        "search_text": search_text,
        "original_text": "The original exact story source.",
        "original_word_count": 6,
        "estimated_spoken_duration_seconds": 3,
        "length_advisory_exceeds_600_words": False,
        "status": status,
        "visibility": visibility,
        "rights_status": rights_status,
        "publication_restrictions": restrictions,
        "variants": variants or [],
        "emotions": emotions or [],
        "embedding": "[" + ",".join(map(str, vector)) + "]",
    }


@pytest.mark.asyncio
async def test_embedder_generates_hash_tracks_model_and_skips_unchanged() -> None:
    client = FakeSearchSupabase()
    story_id = str(uuid4())
    client.tables["stories"] = [
        {
            "id": story_id,
            "status": "approved",
            "title": "A story",
            "original_text": "A source story.",
            "created_at": datetime.now(UTC).isoformat(),
        },
        {
            "id": str(uuid4()),
            "status": "discovered_pending_review",
            "title": "Not approved",
            "original_text": "Private text.",
            "created_at": datetime.now(UTC).isoformat(),
        },
    ]
    client.tables["story_variant_assignments"] = [
        {"story_id": story_id, "variant": "return_to_joy"}
    ]
    provider = FakeEmbeddingProvider()
    embedder = StoryEmbedder(client, provider)

    first = await embedder.embed_approved_stories()
    second = await embedder.embed_approved_stories()

    assert first == {"processed": 1, "skipped": 0}
    assert second == {"processed": 0, "skipped": 1}
    assert len(client.tables["story_embeddings"]) == 1
    embedding = client.tables["story_embeddings"][0]
    assert embedding["embedding_model"] == embedder.model_name
    assert embedding["model_version"] == embedder.model_version
    assert len(embedding["content_hash"]) == 64
    assert len(_vector(embedding["embedding"])) == 1536
    assert provider.initialized == provider.closed == 2
    assert len(provider.inputs) == 1
    assert "Variants: return_to_joy" in provider.inputs[0]
    original_hash = embedding["content_hash"]
    client.tables["stories"][0]["title"] = "Updated title"
    refreshed = await embedder.embed_approved_stories()
    assert refreshed == {"processed": 1, "skipped": 0}
    assert client.tables["story_embeddings"][0]["content_hash"] != original_hash


@pytest.mark.asyncio
async def test_embedder_rejects_unapproved_stories_and_wrong_dimensions() -> None:
    client = FakeSearchSupabase()
    embedder = StoryEmbedder(client, FakeEmbeddingProvider([1.0]))
    with pytest.raises(ValueError, match="Only approved"):
        await embedder.embed_story({"id": str(uuid4()), "status": "under_review"})

    with pytest.raises(ValueError, match="returned 1 dimensions"):
        await embedder.embed_story(
            {
                "id": str(uuid4()),
                "status": "approved",
                "title": "A story",
                "original_text": "Source.",
            }
        )


def test_rrf_uses_one_based_ranks_and_omits_missing_lanes() -> None:
    assert reciprocal_rank_fusion(1, 1) == pytest.approx(2 / 61)
    assert reciprocal_rank_fusion(2, None) == pytest.approx(1 / 62)
    with pytest.raises(ValueError, match="one-based"):
        reciprocal_rank_fusion(0, None)


def test_search_visibility_rights_and_status_gates() -> None:
    assert can_access_story("approved", "public", "licensed", None, UserRole.PUBLIC_GUEST)
    assert can_access_story(
        "approved", "registered_users", "public_domain", None, UserRole.CHURCH_MEMBER
    )
    assert not can_access_story(
        "approved", "registered_users", "licensed", None, UserRole.PUBLIC_GUEST
    )
    assert not can_access_story(
        "approved", "public", "restricted_internal", None, UserRole.SUPER_ADMIN
    )
    assert not can_access_story(
        "under_review", "public", "licensed", None, UserRole.CURATOR
    )
    assert not can_access_story(
        "approved", "public", "licensed", "No publication", UserRole.PUBLIC_GUEST
    )


@pytest.mark.asyncio
async def test_hybrid_search_rrf_ranks_by_lexical_and_vector_relevance() -> None:
    client = FakeSearchSupabase()
    sparse_vector_story = _search_row(
        search_text="fear in the hospital", vector=[0.8, 0.6] + [0.0] * 1534
    )
    dense_only_story = _search_row(
        search_text="joy in a garden", vector=[1.0, 0.0] + [0.0] * 1534
    )
    other_story = _search_row(search_text="visit", vector=[0.0, 1.0] + [0.0] * 1534)
    client.search_rows = [sparse_vector_story, other_story, dense_only_story]
    provider = FakeEmbeddingProvider()
    engine = HybridSearchEngine(client, provider)

    response = await engine.search(
        HybridSearchRequest(query="hospital", limit=10),
        UserRole.PUBLIC_GUEST,
    )

    assert response.total_matched == 3
    assert str(response.results[0].story_id) == sparse_vector_story["story_id"]
    assert str(response.results[1].story_id) == dense_only_story["story_id"]
    assert str(response.results[2].story_id) == other_story["story_id"]
    assert response.results[0].rrf_score == pytest.approx(1 / 61 + 1 / 62)
    assert response.results[1].rrf_score == pytest.approx(1 / 61)
    assert response.results[2].rrf_score == pytest.approx(1 / 63)
    assert response.results[0].original_text_preview == "The original exact story source."
    assert client.rpc_calls[0]["include_registered"] is False
    assert provider.inputs == ["hospital"]
    assert provider.initialized == provider.closed == 1


@pytest.mark.asyncio
async def test_search_offset_beyond_results_preserves_total_count() -> None:
    client = FakeSearchSupabase()
    client.search_rows = [
        _search_row(search_text="peace", vector=[1.0] + [0.0] * 1535)
    ]
    engine = HybridSearchEngine(client, FakeEmbeddingProvider())

    response = await engine.search(
        HybridSearchRequest(query="peace", offset=20),
        UserRole.PUBLIC_GUEST,
    )

    assert response.results == []
    assert response.total_matched == 1
    assert len(client.rpc_calls) == 2


@pytest.mark.asyncio
async def test_search_filters_by_role_rights_publication_and_metadata() -> None:
    client = FakeSearchSupabase()
    public_result = _search_row(
        search_text="fear",
        vector=[1.0] + [0.0] * 1535,
        visibility="public",
        rights_status="licensed",
        variants=["return_to_joy"],
        emotions=["fear"],
    )
    registered_result = _search_row(
        search_text="fear",
        vector=[1.0] + [0.0] * 1535,
        visibility="registered_users",
        rights_status="public_domain",
    )
    restricted = _search_row(
        search_text="fear",
        vector=[1.0] + [0.0] * 1535,
        visibility="public",
        rights_status="restricted_internal",
    )
    unapproved = _search_row(
        search_text="fear",
        vector=[1.0] + [0.0] * 1535,
        status="discovered_pending_review",
    )
    restricted_publication = _search_row(
        search_text="fear",
        vector=[1.0] + [0.0] * 1535,
        restrictions="Permission required",
    )
    client.search_rows = [
        public_result,
        registered_result,
        restricted,
        unapproved,
        restricted_publication,
    ]
    engine = HybridSearchEngine(client, FakeEmbeddingProvider())

    public_response = await engine.search(
        HybridSearchRequest(
            query="fear",
            filter_variant=StoryVariant.RETURN_TO_JOY,
            filter_emotion=EmotionType.FEAR,
        ),
        UserRole.PUBLIC_GUEST,
    )
    member_response = await engine.search(
        HybridSearchRequest(query="fear"),
        UserRole.CHURCH_MEMBER,
    )

    assert [str(row.story_id) for row in public_response.results] == [public_result["story_id"]]
    assert {str(row.story_id) for row in member_response.results} == {
        public_result["story_id"],
        registered_result["story_id"],
    }
    assert client.rpc_calls[0]["filter_variant"] == "return_to_joy"
    assert client.rpc_calls[0]["filter_emotion"] == "fear"
    assert client.rpc_calls[0]["include_registered"] is False
    assert client.rpc_calls[1]["include_registered"] is True


def test_search_endpoint_returns_ranked_results() -> None:
    client = FakeSearchSupabase()
    client.search_rows = [
        _search_row(search_text="peace", vector=[1.0] + [0.0] * 1535)
    ]
    engine = HybridSearchEngine(client, FakeEmbeddingProvider())
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_supabase_client] = lambda: client
    app.dependency_overrides[get_search_engine] = lambda: engine
    app.dependency_overrides[get_search_user_role] = lambda: UserRole.PUBLIC_GUEST

    with TestClient(app) as test_client:
        response = test_client.post("/api/v1/stories/search", json={"query": "peace"})

    assert response.status_code == 200
    assert len(response.json()["results"]) == 1
    assert response.json()["results"][0]["rrf_score"] > 0


@pytest.mark.asyncio
async def test_authenticated_search_role_is_resolved_from_profile() -> None:
    client = FakeSearchSupabase()
    user_id = str(uuid4())
    client.tables["user_profiles"] = [{"id": user_id, "role": "church_member"}]

    async def get_user(_token: str) -> SimpleNamespace:
        return SimpleNamespace(user=SimpleNamespace(id=user_id))

    client.auth = SimpleNamespace(get_user=get_user)
    role = await get_search_user_role(
        HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid-token"),
        client,
    )

    assert role == UserRole.CHURCH_MEMBER
