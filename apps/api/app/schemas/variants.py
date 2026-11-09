"""
Pydantic v2 Schemas for Authoritative Story Variants.

The authoritative 4 variants in the Life Model framework:
1. Return to Joy (Level 3)
2. Acting Like Myself (Level 4)
3. Godsight / Immanuel
4. Appreciation / Joy-Spreading

A story may have zero, one, or multiple variants. Variant classification
is completely independent of 4+ classification.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import StoryVariant


class StoryVariantAssignment(BaseModel):
    """Variant assignment payload used in AI analysis and story presentation."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    variant: StoryVariant = Field(
        description="One of the 4 authoritative Life Model variants"
    )
    assignment_source: str = Field(
        default="ai_proposed",
        description="Origin of assignment: 'ai_proposed' or 'human_curated'"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence rating between 0.0 and 1.0"
    )
    evidence_quote: str = Field(
        description="Direct verbatim text excerpt justifying variant assignment"
    )
    reasoning: str = Field(
        description="Detailed explanation of how the narrative exemplifies this variant"
    )


class StoryVariantAssignmentInDB(StoryVariantAssignment):
    """Database entity representation for story_variant_assignments."""
    id: Optional[UUID] = Field(default=None, description="Primary key UUID")
    story_id: UUID = Field(description="Foreign key referencing stories(id)")
    assigned_by_user_id: Optional[UUID] = Field(
        default=None,
        description="User profile UUID if manually assigned/reviewed"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Creation timestamp"
    )

