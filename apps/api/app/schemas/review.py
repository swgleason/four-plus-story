"""
Pydantic v2 Schemas for Editorial Review Queue, Actions, and Audit Trail.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import (
    FourPlusClassification,
    NarratorGender,
    ReviewAction,
    StoryStatus,
    StoryVariant,
    StoryVisibility,
)


class EditorialOverrides(BaseModel):
    """Optional curator overrides applied during approval."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    title: Optional[str] = None
    primary_emotion: Optional[str] = None


class ReviewActionRequest(BaseModel):
    """Payload submitted when a curator approves or rejects a story."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    action: ReviewAction = Field(description="Review action taken")
    visibility: StoryVisibility = Field(
        default=StoryVisibility.PUBLIC,
        description="Target visibility tier upon approval"
    )
    notes: Optional[str] = Field(
        default=None,
        description="Curator review notes or revision request explanation"
    )
    editorial_overrides: Optional[EditorialOverrides] = Field(
        default=None,
        description="Direct metadata overrides applied by reviewer"
    )


class ReviewActionResponse(BaseModel):
    """Result of review action execution."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    story_id: UUID
    status: StoryStatus
    visibility: StoryVisibility
    approved_at: Optional[datetime] = None
    approved_by_user_id: Optional[UUID] = None


class ReviewQueueItem(BaseModel):
    """Summary of a story awaiting editorial review."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    title: str
    document_title: str
    original_word_count: int = Field(ge=0)
    estimated_spoken_duration_seconds: int = Field(ge=0)
    length_advisory_exceeds_600_words: bool
    is_autobiographical: Optional[bool] = None
    narrator_gender: NarratorGender = NarratorGender.UNKNOWN
    overall_classification: FourPlusClassification
    overall_confidence: float = Field(ge=0.0, le=1.0)
    assigned_variants: List[StoryVariant] = Field(default_factory=list)
    created_at: datetime


class ReviewQueueResponse(BaseModel):
    """Paginated response for review queue."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    total: int = Field(ge=0)
    items: List[ReviewQueueItem] = Field(default_factory=list)


class StoryHumanReviewInDB(BaseModel):
    """Immutable audit trail record in story_human_reviews."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    story_id: UUID
    reviewer_user_id: UUID
    action: str
    diff: Optional[Dict[str, Any]] = None
    previous_state: Dict[str, Any]
    new_state: Dict[str, Any]
    reviewer_notes: Optional[str] = None
    created_at: datetime
