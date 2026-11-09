"""
Pydantic v2 Schemas for the Restored STEP Framework.

Agreed STEP Components:
S — Setting: Time, place, context, people present, relational atmosphere.
T — Trigger: Specific incident, word, event, or disruption catalyzing the reaction.
E — Emotion & Body Sensations: Explicit feelings AND somatic sensations.
P — Point: The core relational, spiritual, or life lesson/takeaway.

Thoughts and relational presence may be captured as supplementary analysis
fields, but never substituted for STEP.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class StepAnalysis(BaseModel):
    """STEP analysis payload for AI extraction and story display."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    setting: str = Field(
        description="S — Setting: Time, place, context, people present, relational atmosphere"
    )
    trigger: str = Field(
        description="T — Trigger: Specific incident, word, event, or disruption catalyzing the reaction"
    )
    emotion_and_body_sensations: str = Field(
        description="E — Emotion & Body Sensations: Explicit feelings AND somatic sensations"
    )
    point: str = Field(
        description="P — Point: The core relational, spiritual, or life lesson/takeaway"
    )
    internal_thoughts: Optional[str] = Field(
        default=None,
        description="Supplementary: Automatic cognitions, assumptions, or beliefs"
    )
    relational_presence: Optional[str] = Field(
        default=None,
        description="Supplementary: Relational presence, attunement, or comfort"
    )


class StepAnalysisInDB(StepAnalysis):
    """Database entity representation for story_step_analyses."""
    id: Optional[UUID] = Field(default=None, description="Primary key UUID")
    story_id: UUID = Field(description="Foreign key referencing stories(id)")
    is_human_edited: bool = Field(
        default=False,
        description="True if an editor has modified the AI-generated STEP fields"
    )
    edited_by_user_id: Optional[UUID] = Field(
        default=None,
        description="User UUID of curator/reviewer who edited"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Last updated timestamp"
    )

