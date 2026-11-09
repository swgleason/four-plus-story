"""Curator workbench APIs for jobs, story review, and curated telling drafts."""

# FastAPI uses Depends() in parameter defaults for request handling.
# ruff: noqa: B008

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from app.core.supabase import get_supabase_client, require_curator
from app.schemas.enums import DocumentRightsStatus, ReviewAction, StoryStatus, StoryVisibility
from app.schemas.review import ReviewActionRequest, ReviewActionResponse

router = APIRouter(prefix="/admin", tags=["admin workbench"])
_CLEARED_RIGHTS = {
    DocumentRightsStatus.PUBLIC_DOMAIN.value,
    DocumentRightsStatus.LICENSED.value,
    DocumentRightsStatus.FAIR_USE_EDUCATIONAL.value,
}


class CuratedDraftRequest(BaseModel):
    curated_title: str = Field(min_length=1, max_length=500)
    curated_text: str = Field(min_length=1)
    editorial_notes: str | None = None
    version_id: UUID | None = None

    @field_validator("curated_title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Curated title must not be blank.")
        return normalized


def _rows(result: Any) -> list[dict[str, Any]]:
    data = getattr(result, "data", None)
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def _first_row(result: Any) -> dict[str, Any] | None:
    data = getattr(result, "data", None)
    if isinstance(data, list):
        return data[0] if data else None
    return data if isinstance(data, dict) else None


async def _related(
    supabase: Any, table: str, story_id: str, *, order_by: str = "created_at"
) -> list[dict[str, Any]]:
    result = await (
        supabase.table(table)
        .select("*")
        .eq("story_id", story_id)
        .order(order_by)
        .execute()
    )
    return _rows(result)


async def _related_many(
    supabase: Any,
    table: str,
    foreign_key: str,
    ids: list[str],
    *,
    order_by: str = "created_at",
    desc: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    if not ids:
        return {}
    result = await (
        supabase.table(table)
        .select("*")
        .in_(foreign_key, ids)
        .order(order_by, desc=desc)
        .execute()
    )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in _rows(result):
        grouped.setdefault(str(row[foreign_key]), []).append(row)
    return grouped


@router.get("/jobs")
async def list_processing_jobs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    job_status: str | None = Query(default=None, alias="status"),
    supabase: Any = Depends(get_supabase_client),
    _curator_id: str = Depends(require_curator),
) -> list[dict[str, Any]]:
    query = (
        supabase.table("processing_jobs")
        .select("*")
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
    )
    if job_status:
        query = query.eq("status", job_status)
    jobs = _rows(await query.execute())
    document_ids = list({str(job["document_id"]) for job in jobs if job.get("document_id")})
    documents: dict[str, dict[str, Any]] = {}
    if document_ids:
        result = await supabase.table("documents").select("id,title").in_("id", document_ids).execute()
        documents = {str(row["id"]): row for row in _rows(result)}
    job_ids = [str(job["id"]) for job in jobs]
    job_events = await _related_many(
        supabase, "processing_job_events", "job_id", job_ids
    )
    for job in jobs:
        job["document_title"] = documents.get(str(job.get("document_id")), {}).get("title")
        job["events"] = job_events.get(str(job["id"]), [])
    return jobs


@router.get("/review-queue")
async def get_review_queue(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    supabase: Any = Depends(get_supabase_client),
    _curator_id: str = Depends(require_curator),
) -> list[dict[str, Any]]:
    stories_result = await (
        supabase.table("stories")
        .select("*")
        .in_(
            "status",
            [
                StoryStatus.DISCOVERED_PENDING_REVIEW.value,
                StoryStatus.UNDER_REVIEW.value,
            ],
        )
        .order("created_at")
        .range(offset, offset + limit - 1)
        .execute()
    )
    stories = _rows(stories_result)
    document_ids = list({str(story["document_id"]) for story in stories})
    documents: dict[str, dict[str, Any]] = {}
    if document_ids:
        result = await supabase.table("documents").select("*").in_("id", document_ids).execute()
        documents = {str(row["id"]): row for row in _rows(result)}

    story_ids = [str(story["id"]) for story in stories]
    evaluations = await _related_many(
        supabase,
        "story_ai_evaluations",
        "story_id",
        story_ids,
        desc=True,
    )
    boundaries = await _related_many(
        supabase,
        "story_boundary_candidates",
        "story_id",
        story_ids,
        desc=True,
    )
    spans = await _related_many(
        supabase,
        "story_source_spans",
        "story_id",
        story_ids,
        order_by="span_order",
    )
    variants = await _related_many(
        supabase, "story_variant_assignments", "story_id", story_ids
    )
    emotions = await _related_many(supabase, "story_emotions", "story_id", story_ids)
    step_analyses = await _related_many(
        supabase, "story_step_analyses", "story_id", story_ids
    )

    items = []
    for story in stories:
        story_id = str(story["id"])
        items.append(
            {
                "story": story,
                "document": documents.get(str(story["document_id"])),
                "spans": spans.get(story_id, []),
                "evaluation": _latest(evaluations.get(story_id, [])),
                "boundary": _latest(boundaries.get(story_id, [])),
                "variants": variants.get(story_id, []),
                "emotions": emotions.get(story_id, []),
                "step_analysis": _latest(step_analyses.get(story_id, [])),
            }
        )
    return items


def _latest(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    return rows[0] if rows else None


@router.get("/stories/{story_id}")
async def get_admin_story(
    story_id: UUID,
    supabase: Any = Depends(get_supabase_client),
    _curator_id: str = Depends(require_curator),
) -> dict[str, Any]:
    story_result = await (
        supabase.table("stories").select("*").eq("id", str(story_id)).maybe_single().execute()
    )
    story = _first_row(story_result)
    if story is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found.")
    document_result = await (
        supabase.table("documents")
        .select("*")
        .eq("id", str(story["document_id"]))
        .maybe_single()
        .execute()
    )
    evaluation_result = await (
        supabase.table("story_ai_evaluations")
        .select("*")
        .eq("story_id", str(story_id))
        .order("created_at", desc=True)
        .limit(1)
        .maybe_single()
        .execute()
    )
    step_result = await (
        supabase.table("story_step_analyses")
        .select("*")
        .eq("story_id", str(story_id))
        .maybe_single()
        .execute()
    )
    return {
        "story": story,
        "document": _first_row(document_result),
        "spans": await _related(supabase, "story_source_spans", str(story_id), order_by="span_order"),
        "evaluation": _first_row(evaluation_result),
        "variants": await _related(supabase, "story_variant_assignments", str(story_id)),
        "emotions": await _related(supabase, "story_emotions", str(story_id)),
        "step_analysis": _first_row(step_result),
        "curated_versions": await _related(
            supabase, "story_curated_versions", str(story_id), order_by="updated_at"
        ),
    }


@router.post("/stories/{story_id}/review", response_model=ReviewActionResponse)
async def review_story(
    story_id: UUID,
    request: ReviewActionRequest,
    supabase: Any = Depends(get_supabase_client),
    curator_id: str = Depends(require_curator),
) -> ReviewActionResponse:
    story_result = await (
        supabase.table("stories").select("*").eq("id", str(story_id)).maybe_single().execute()
    )
    story = _first_row(story_result)
    if story is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found.")
    if story.get("status") not in {
        StoryStatus.DISCOVERED_PENDING_REVIEW.value,
        StoryStatus.UNDER_REVIEW.value,
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only stories awaiting editorial review can be reviewed.",
        )

    document_result = await (
        supabase.table("documents")
        .select("rights_status,publication_restrictions")
        .eq("id", str(story["document_id"]))
        .maybe_single()
        .execute()
    )
    document = _first_row(document_result)
    if document is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Source document is missing.")

    if request.action in {ReviewAction.APPROVE, ReviewAction.EDIT_AND_APPROVE}:
        visibility = request.visibility
        if visibility != StoryVisibility.INTERNAL_ONLY and (
            document.get("rights_status") not in _CLEARED_RIGHTS
            or document.get("publication_restrictions")
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Document rights must be cleared and publication restrictions removed.",
            )
        next_visibility = visibility.value
    elif request.action == ReviewAction.REJECT:
        next_visibility = StoryVisibility.INTERNAL_ONLY.value
    else:
        next_visibility = StoryVisibility.INTERNAL_ONLY.value

    override_title = None
    if request.editorial_overrides and request.action == ReviewAction.EDIT_AND_APPROVE:
        override_title = request.editorial_overrides.title
    result = await supabase.rpc(
        "admin_review_story",
        {
            "p_story_id": str(story_id),
            "p_reviewer_user_id": curator_id,
            "p_action": request.action.value,
            "p_visibility": next_visibility,
            "p_notes": request.notes,
            "p_override_title": override_title,
        },
    ).execute()
    review_result = getattr(result, "data", None)
    if isinstance(review_result, list):
        review_result = review_result[0] if review_result else None
    if not isinstance(review_result, dict):
        raise TypeError("Atomic story review did not return a result object.")
    return ReviewActionResponse.model_validate(review_result)


@router.post("/stories/{story_id}/curated")
async def save_curated_draft(
    story_id: UUID,
    request: CuratedDraftRequest,
    supabase: Any = Depends(get_supabase_client),
    curator_id: str = Depends(require_curator),
) -> dict[str, Any]:
    text = request.curated_text.strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Curated text must contain at least one word.",
        )
    story_result = await (
        supabase.table("stories").select("id").eq("id", str(story_id)).maybe_single().execute()
    )
    if _first_row(story_result) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found.")
    result = await supabase.rpc(
        "admin_save_curated_draft",
        {
            "p_story_id": str(story_id),
            "p_reviewer_user_id": curator_id,
            "p_curated_title": request.curated_title.strip(),
            "p_curated_text": text,
            "p_editorial_notes": request.editorial_notes,
            "p_version_id": str(request.version_id) if request.version_id else None,
        },
    ).execute()
    draft = getattr(result, "data", None)
    if isinstance(draft, list):
        draft = draft[0] if draft else None
    if not isinstance(draft, dict):
        raise TypeError("Atomic curated draft save did not return a result object.")
    return draft
