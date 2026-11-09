"""
Pydantic v2 Schemas for AI Extraction, Classification, and Evaluation.

Strict Guardrails:
1. Anti-hallucination boundary schema: AI identifies boundary markers
   (first_sentence, last_sentence, approx offsets, quote) and NEVER
   reproduces the entire verbatim story. The backend extracts verified text.
2. Structured JSON response models for multi-provider AI adapters.
3. Separation of classification dimensions.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.criteria import CriteriaBreakdown
from app.schemas.emotions import StoryEmotion
from app.schemas.enums import FourPlusClassification, NarratorGender
from app.schemas.step import StepAnalysis
from app.schemas.variants import StoryVariantAssignment


class CandidateStorySegment(BaseModel):
    """AI-proposed continuous part of a story; the backend verifies both anchors."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    first_sentence: str = Field(description="Exact first sentence of this story segment")
    last_sentence: str = Field(description="Exact last sentence of this story segment")
    approx_char_start: int = Field(ge=0, description="Approximate start offset in the chunk")
    approx_char_end: int = Field(ge=1, description="Approximate end offset in the chunk")


class CandidateStoryBoundary(BaseModel):
    """
    AI output model for story candidate detection.
    Does NOT contain full verbatim text to prevent hallucination and token waste.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    tentative_title: str = Field(description="Tentative descriptive title for the candidate story")
    first_sentence: str = Field(description="Exact first sentence of the story")
    last_sentence: str = Field(description="Exact last sentence of the story")
    approx_char_start: int = Field(ge=0, description="Approximate start character offset in chunk")
    approx_char_end: int = Field(ge=1, description="Approximate end character offset in chunk")
    evidence_quote: str = Field(
        min_length=1,
        description="Representative quote illustrating the narrative",
    )
    source_segments: list[CandidateStorySegment] = Field(
        default_factory=list,
        description=(
            "For a story interrupted by unrelated material, provide every ordered story segment, "
            "including the first and final segments. Exclude unrelated sidebars."
        ),
    )


class StoryBoundaryExtractionResponse(BaseModel):
    """Response returned by the boundary extraction prompt."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    has_candidates: bool = Field(description="True if one or more candidates were detected")
    candidates: list[CandidateStoryBoundary] = Field(
        default_factory=list, description="List of detected candidate boundaries"
    )


class StoryBoundaryCandidateInDB(BaseModel):
    """Persisted AI boundary proposal linked to its pending-review story."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    document_id: UUID
    story_id: UUID
    chunk_id: UUID | None = None
    tentative_title: str
    first_sentence: str
    last_sentence: str
    evidence_quote: str
    approx_char_start: int = Field(ge=0)
    approx_char_end: int = Field(ge=1)
    document_char_start: int = Field(ge=0)
    document_char_end: int = Field(gt=0)
    created_at: datetime


class StoryEvaluationResponse(BaseModel):
    """
    Comprehensive structured response from the 4+ evaluation prompt.
    Validates all five criteria, variants, emotions, and STEP analysis.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    title: str = Field(description="Refined descriptive title")
    is_autobiographical: bool = Field(
        description="Whether story is autobiographical lived experience"
    )
    narrator_gender: NarratorGender = Field(
        description=(
            "Narrator gender inferred only from explicit textual evidence such as pronouns or "
            "self-identification; use unknown when evidence is absent or ambiguous"
        ),
    )
    overall_classification: FourPlusClassification = Field(
        description=(
            "Overall 4+ classification (confirmed_4_plus, not_4_plus, uncertain_needs_review)"
        )
    )
    overall_confidence: float = Field(
        ge=0.0, le=1.0, description="Overall classification confidence score"
    )
    criteria_breakdown: CriteriaBreakdown = Field(
        description="Independent evaluations for all 5 criteria"
    )
    assigned_variants: list[StoryVariantAssignment] = Field(
        default_factory=list, description="Authoritative variant assignments (0, 1, or multiple)"
    )
    emotions: list[StoryEmotion] = Field(
        default_factory=list, description="Big 6 and connective emotions with somatic rigor"
    )
    step_analysis: StepAnalysis = Field(description="Restored STEP framework breakdown")
    suggested_curated_telling: str | None = Field(
        default=None,
        description="Suggested oral telling adaptation (requires human approval before publishing)",
    )
    reasoning_summary: str = Field(description="Holistic evaluation rationale and summary")


class StoryAIEvaluationInDB(BaseModel):
    """Database representation of an AI evaluation record in story_ai_evaluations."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID = Field(description="Evaluation UUID")
    story_id: UUID = Field(description="Foreign key referencing stories(id)")
    model_name: str = Field(description="Provider/model name (e.g. 'claude-3-5-sonnet', 'gpt-4o')")
    model_version: str = Field(description="Specific model checkpoint or release date")
    prompt_version: str = Field(description="Semantic version of prompt template used")
    overall_classification: FourPlusClassification = Field(description="Evaluation outcome")
    overall_confidence: float = Field(ge=0.0, le=1.0, description="Confidence score")
    criteria_evaluations: CriteriaBreakdown = Field(description="Serialized 5 criteria evaluations")
    reasoning_summary: str = Field(description="Holistic analytical reasoning")
    token_usage: dict[str, Any] = Field(default_factory=dict, description="Token usage statistics")
    created_at: datetime = Field(description="Evaluation timestamp")
