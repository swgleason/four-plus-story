"""Curator-only story evaluation and multidimensional analysis endpoints."""

# FastAPI uses Depends() in parameter defaults for request handling.
# ruff: noqa: B008

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.supabase import get_supabase_client, require_curator
from app.schemas.ai import StoryAIEvaluationInDB
from app.schemas.document import ProcessingJobInDB
from app.schemas.emotions import StoryEmotionInDB
from app.schemas.enums import JobStatus, StoryStatus, StoryVisibility
from app.schemas.step import StepAnalysisInDB
from app.schemas.story import StoryInDB
from app.schemas.variants import StoryVariantAssignmentInDB
from app.services.ai.manager import create_default_manager
from app.services.ai_pipeline.evaluator import StoryEvaluator

router = APIRouter(prefix="/stories", tags=["story evaluation"])


class StoryEvaluationJobResponse(BaseModel):
    job: ProcessingJobInDB


class StoryEvaluationDetail(BaseModel):
    story: StoryInDB
    evaluation: StoryAIEvaluationInDB
    variants: list[StoryVariantAssignmentInDB]
    emotions: list[StoryEmotionInDB]
    step_analysis: StepAnalysisInDB | None = None


def _first_row(result: Any) -> dict[str, Any] | None:
    data = getattr(result, "data", None)
    if isinstance(data, list):
        return data[0] if data else None
    return data if isinstance(data, dict) else None


async def get_story_evaluator(
    supabase: Any = Depends(get_supabase_client),
) -> StoryEvaluator:
    return StoryEvaluator(supabase, await create_default_manager())


@router.post(
    "/{story_id}/evaluate",
    response_model=StoryEvaluationJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def evaluate_story(
    story_id: str,
    background_tasks: BackgroundTasks,
    supabase: Any = Depends(get_supabase_client),
    evaluator: StoryEvaluator = Depends(get_story_evaluator),
    _curator_id: str = Depends(require_curator),
) -> StoryEvaluationJobResponse:
    story_result = await (
        supabase.table("stories").select("*").eq("id", story_id).maybe_single().execute()
    )
    story_row = _first_row(story_result)
    if story_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found.")
    story = StoryInDB.model_validate(story_row)
    if (
        story.status != StoryStatus.DISCOVERED_PENDING_REVIEW
        or story.visibility != StoryVisibility.INTERNAL_ONLY
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending-review, internal-only stories can be evaluated.",
        )

    job_id = str(uuid4())
    job_result = await (
        supabase.table("processing_jobs")
        .insert(
            {
                "id": job_id,
                "document_id": str(story.document_id),
                "job_type": "story_evaluation",
                "status": JobStatus.PENDING.value,
                "config": {"pipeline": "multidimensional_evaluation_v1"},
            }
        )
        .select("*")
        .single()
        .execute()
    )
    job = _first_row(job_result)
    if job is None:
        raise RuntimeError("Story evaluation job insert returned no row.")

    await (
        supabase.table("processing_job_events")
        .insert(
            {
                "job_id": job_id,
                "stage": "queued",
                "level": "info",
                "message": "Multidimensional story evaluation job queued.",
                "details": {"story_id": story_id},
            }
        )
        .execute()
    )
    background_tasks.add_task(evaluator.evaluate_story, story, job_id)
    return StoryEvaluationJobResponse(job=ProcessingJobInDB.model_validate(job))


@router.get("/{story_id}/evaluation", response_model=StoryEvaluationDetail)
async def get_story_evaluation(
    story_id: str,
    supabase: Any = Depends(get_supabase_client),
    _curator_id: str = Depends(require_curator),
) -> StoryEvaluationDetail:
    story_result = await (
        supabase.table("stories").select("*").eq("id", story_id).maybe_single().execute()
    )
    story_row = _first_row(story_result)
    if story_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found.")

    evaluation_result = await (
        supabase.table("story_ai_evaluations")
        .select("*")
        .eq("story_id", story_id)
        .order("created_at", desc=True)
        .limit(1)
        .maybe_single()
        .execute()
    )
    evaluation_row = _first_row(evaluation_result)
    if evaluation_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No AI evaluation is available for this story.",
        )

    variant_result = await (
        supabase.table("story_variant_assignments")
        .select("*")
        .eq("story_id", story_id)
        .order("created_at")
        .execute()
    )
    emotion_result = await (
        supabase.table("story_emotions")
        .select("*")
        .eq("story_id", story_id)
        .order("created_at")
        .execute()
    )
    step_result = await (
        supabase.table("story_step_analyses")
        .select("*")
        .eq("story_id", story_id)
        .maybe_single()
        .execute()
    )

    step_row = _first_row(step_result)
    return StoryEvaluationDetail(
        story=StoryInDB.model_validate(story_row),
        evaluation=StoryAIEvaluationInDB.model_validate(evaluation_row),
        variants=[
            StoryVariantAssignmentInDB.model_validate(row)
            for row in (getattr(variant_result, "data", None) or [])
        ],
        emotions=[
            StoryEmotionInDB.model_validate(row)
            for row in (getattr(emotion_result, "data", None) or [])
        ],
        step_analysis=StepAnalysisInDB.model_validate(step_row) if step_row else None,
    )
