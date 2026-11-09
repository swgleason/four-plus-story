"""Curator-only endpoints for starting and reviewing story discovery."""

# FastAPI uses Depends() in parameter defaults for request handling.
# ruff: noqa: B008

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.core.supabase import get_supabase_client, require_curator
from app.schemas.ai import StoryBoundaryCandidateInDB
from app.schemas.document import ProcessingJobInDB
from app.schemas.enums import JobStatus, StoryStatus, StoryVisibility
from app.schemas.story import StoryInDB
from app.services.ai.manager import create_default_manager
from app.services.ai_pipeline.scanner import StoryBoundaryScanner

router = APIRouter(prefix="/documents", tags=["story discovery"])


class StoryDiscoveryJobResponse(BaseModel):
    job: ProcessingJobInDB


class DiscoveredStoryCandidate(BaseModel):
    story: StoryInDB
    boundary: StoryBoundaryCandidateInDB


def _first_row(result: Any) -> dict[str, Any] | None:
    data = getattr(result, "data", None)
    if isinstance(data, list):
        return data[0] if data else None
    return data if isinstance(data, dict) else None


async def get_story_boundary_scanner(
    supabase: Any = Depends(get_supabase_client),
) -> StoryBoundaryScanner:
    manager = await create_default_manager()
    return StoryBoundaryScanner(supabase, manager)


@router.post(
    "/{document_id}/scan",
    response_model=StoryDiscoveryJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def scan_document_stories(
    document_id: str,
    background_tasks: BackgroundTasks,
    supabase: Any = Depends(get_supabase_client),
    scanner: StoryBoundaryScanner = Depends(get_story_boundary_scanner),
    _curator_id: str = Depends(require_curator),
) -> StoryDiscoveryJobResponse:
    document_result = await (
        supabase.table("documents").select("id").eq("id", document_id).maybe_single().execute()
    )
    if _first_row(document_result) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    chunks_result = await (
        supabase.table("document_chunks")
        .select("id")
        .eq("document_id", document_id)
        .limit(1)
        .execute()
    )
    if not getattr(chunks_result, "data", None):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document ingestion must complete before story discovery.",
        )

    job_id = str(uuid4())
    job_result = await (
        supabase.table("processing_jobs")
        .insert(
            {
                "id": job_id,
                "document_id": document_id,
                "job_type": "story_discovery",
                "status": JobStatus.PENDING.value,
                "config": {"pipeline": "boundary_scan_v1"},
            }
        )
        .select("*")
        .single()
        .execute()
    )
    job = _first_row(job_result)
    if job is None:
        raise RuntimeError("Story discovery job insert returned no row.")

    await (
        supabase.table("processing_job_events")
        .insert(
            {
                "job_id": job_id,
                "stage": "queued",
                "level": "info",
                "message": "Story boundary scanning job queued.",
                "details": {"document_id": document_id},
            }
        )
        .execute()
    )
    background_tasks.add_task(scanner.scan_document, document_id, job_id)
    return StoryDiscoveryJobResponse(job=ProcessingJobInDB.model_validate(job))


@router.get(
    "/{document_id}/candidates",
    response_model=list[DiscoveredStoryCandidate],
)
async def get_discovered_candidates(
    document_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    supabase: Any = Depends(get_supabase_client),
    _curator_id: str = Depends(require_curator),
) -> list[DiscoveredStoryCandidate]:
    document_result = await (
        supabase.table("documents").select("id").eq("id", document_id).maybe_single().execute()
    )
    if _first_row(document_result) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    boundary_result = await (
        supabase.table("story_boundary_candidates")
        .select("*")
        .eq("document_id", document_id)
        .order("created_at")
        .range(offset, offset + limit - 1)
        .execute()
    )
    boundaries = getattr(boundary_result, "data", None) or []
    story_ids = [str(boundary["story_id"]) for boundary in boundaries]
    if not story_ids:
        return []

    story_result = await supabase.table("stories").select("*").in_("id", story_ids).execute()
    stories = {
        str(row["id"]): row
        for row in (getattr(story_result, "data", None) or [])
        if row.get("status") == StoryStatus.DISCOVERED_PENDING_REVIEW.value
        and row.get("visibility") == StoryVisibility.INTERNAL_ONLY.value
    }
    return [
        DiscoveredStoryCandidate(
            story=StoryInDB.model_validate(stories[str(boundary["story_id"])]),
            boundary=StoryBoundaryCandidateInDB.model_validate(boundary),
        )
        for boundary in boundaries
        if str(boundary["story_id"]) in stories
    ]
