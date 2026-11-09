"""
Pydantic v2 Schemas for Core Stories, Multi-Span Sources, and Curated Versions.

Domain Invariants:
1. Complete original text is preserved and immutable.
2. Multiple spans supported for page breaks / sidebars.
3. Word count (>600 word advisory) and spoken duration (~140 wpm).
4. Separate curated telling versions stored independently.
5. Publication requires status='approved', visibility='public', and document clearance.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.emotions import StoryEmotion
from app.schemas.enums import (
    DocumentRightsStatus,
    NarratorGender,
    StoryStatus,
    StoryVisibility,
)
from app.schemas.step import StepAnalysis
from app.schemas.variants import StoryVariantAssignment


class StorySourceSpanBase(BaseModel):
    """Source text span mapping to an exact page offset."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    document_page_id: UUID = Field(description="Foreign key to document_pages(id)")
    chunk_id: Optional[UUID] = Field(default=None, description="Optional chunk reference")
    span_order: int = Field(ge=1, description="Sequential 1-based order of span")
    page_number: int = Field(ge=1, description="Page number of span")
    char_start: int = Field(ge=0, description="Start character offset on page")
    char_end: int = Field(ge=1, description="End character offset on page")
    verbatim_text: str = Field(description="Exact verbatim extracted text from document page")


class StorySourceSpanCreate(StorySourceSpanBase):
    """Payload to register a source span."""
    pass


class StorySourceSpanInDB(StorySourceSpanBase):
    """Database representation of a story source span."""
    id: UUID = Field(description="Primary key UUID")
    story_id: UUID = Field(description="Parent story UUID")
    created_at: datetime = Field(description="Creation timestamp")


class StoryCuratedVersionBase(BaseModel):
    """Separate human-approved oral telling version of a story."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    curated_title: str = Field(description="Curated, engaging oral storytelling title")
    curated_text: str = Field(description="Curated story text optimized for spoken delivery")
    curated_word_count: int = Field(ge=1, description="Word count of curated text")
    curated_spoken_duration_seconds: int = Field(
        ge=1,
        description="Spoken delivery duration in seconds (~140 wpm)"
    )
    is_approved: bool = Field(
        default=False,
        description="Requires human curator approval before public exposure"
    )
    approved_by_user_id: Optional[UUID] = Field(default=None, description="Curator user UUID")
    approved_at: Optional[datetime] = Field(default=None, description="Curator approval timestamp")
    editorial_notes: Optional[str] = Field(default=None, description="Editorial rationale or notes")


class StoryCuratedVersionCreate(StoryCuratedVersionBase):
    """Payload to propose or save a curated version."""
    pass


class StoryCuratedVersionInDB(StoryCuratedVersionBase):
    """Database representation of a curated version."""
    id: UUID = Field(description="Primary key UUID")
    story_id: UUID = Field(description="Parent story UUID")
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last updated timestamp")


class StoryBase(BaseModel):
    """Base attributes of a discovered story."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    document_id: UUID = Field(description="Source document UUID")
    title: str = Field(description="Story title")
    original_text: str = Field(description="Complete original story text (concatenated from spans)")
    original_word_count: int = Field(ge=0, description="Total word count")
    estimated_spoken_duration_seconds: int = Field(
        ge=0,
        description="Spoken duration in seconds (~140 wpm)"
    )
    length_advisory_exceeds_600_words: bool = Field(
        default=False,
        description="Flagged true if original_word_count > 600 words"
    )
    is_autobiographical: Optional[bool] = Field(
        default=None,
        description="Autobiographical status (independent from 4+ classification)"
    )
    narrator_gender: NarratorGender = Field(
        default=NarratorGender.UNKNOWN,
        description=(
            "Narrator gender based on explicit textual evidence; unknown when evidence is "
            "insufficient"
        ),
    )
    status: StoryStatus = Field(
        default=StoryStatus.DISCOVERED_PENDING_REVIEW,
        description="Editorial review lifecycle status"
    )
    visibility: StoryVisibility = Field(
        default=StoryVisibility.INTERNAL_ONLY,
        description="Visibility tier"
    )


class StoryCreate(StoryBase):
    """Payload to create a discovered story with source spans."""
    spans: List[StorySourceSpanBase] = Field(
        default_factory=list,
        description="Source spans from document pages"
    )


class StoryUpdate(BaseModel):
    """Payload to update story attributes."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    title: Optional[str] = None
    is_autobiographical: Optional[bool] = None
    narrator_gender: Optional[NarratorGender] = None
    status: Optional[StoryStatus] = None
    visibility: Optional[StoryVisibility] = None


class StoryInDB(StoryBase):
    """Database representation of a core story."""
    id: UUID = Field(description="Story primary key UUID")
    approved_by_user_id: Optional[UUID] = Field(
        default=None,
        description="User UUID who approved publication"
    )
    approved_at: Optional[datetime] = Field(
        default=None,
        description="Publication approval timestamp"
    )
    created_at: datetime = Field(description="Discovery timestamp")
    updated_at: datetime = Field(description="Last update timestamp")


class StoryDocumentSummary(BaseModel):
    """Document summary attached to story detail view."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    title: str
    author: Optional[str] = None
    rights_status: DocumentRightsStatus
    publication_restrictions: Optional[str] = None


class StoryDetail(StoryInDB):
    """Composite story detail representation with all relations."""
    document: StoryDocumentSummary
    spans: List[StorySourceSpanInDB] = Field(default_factory=list)
    assigned_variants: List[StoryVariantAssignment] = Field(default_factory=list)
    emotions: List[StoryEmotion] = Field(default_factory=list)
    step_analysis: Optional[StepAnalysis] = None
    curated_version: Optional[StoryCuratedVersionInDB] = None
