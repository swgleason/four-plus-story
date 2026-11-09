"""
Pydantic v2 Schemas for Big 6 Emotion Taxonomy & Somatic Rigor.

Emotions classified in the Life Model taxonomy:
- High-energy: fear, anger
- Low-energy: sadness, shame, disgust, hopeless_despair
- Connective/positive: joy, gratitude, peace, other

Physical body sensations must be recorded strictly when present in the text.
If no sensations are stated in the source, sensations_missing must be True.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import EmotionType, EmotionEnergyLevel, ProgressionStage


class StoryEmotion(BaseModel):
    """Emotion and somatic sensation payload for AI evaluation and presentation."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    emotion: EmotionType = Field(
        description="Emotion categorized under Big 6 or positive/connective states"
    )
    energy_level: EmotionEnergyLevel = Field(
        description="Arousal state: high_energy, low_energy, or positive_connective"
    )
    progression_stage: ProgressionStage = Field(
        default=ProgressionStage.INITIAL,
        description="Narrative progression: initial, escalation, peak, shift, resolving"
    )
    evidence_quote: str = Field(
        description="Verbatim excerpt establishing the presence of this emotion"
    )
    source_page: Optional[int] = Field(
        default=None,
        ge=1,
        description="Page number where emotion appears"
    )
    source_char_offset: Optional[int] = Field(
        default=None,
        ge=0,
        description="Character offset on page where quote starts"
    )
    sensations_identified: List[str] = Field(
        default_factory=list,
        description="Explicit physical sensations mentioned in text (tight chest, tears, etc.)"
    )
    sensations_missing: bool = Field(
        default=False,
        description="True if physical sensations are absent for this emotional moment"
    )


class StoryEmotionInDB(StoryEmotion):
    """Database entity representation for story_emotions."""
    id: Optional[UUID] = Field(default=None, description="Primary key UUID")
    story_id: UUID = Field(description="Foreign key referencing stories(id)")
    assigned_by: str = Field(
        default="ai_extracted",
        description="Origin of classification ('ai_extracted' or user identifier)"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Creation timestamp"
    )

