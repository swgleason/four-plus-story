"""
Pydantic v2 Schemas for the Five 4+ Evaluation Criteria.

In the Life Model framework, the five independent criteria are:
1. Autobiographical Involvement (First-person, lived experience)
2. Appropriate Emotional Intensity (Neither flat detachment nor overwhelming flooding)
3. Explicit Emotion and Body Sensations (Named feelings and somatic sensations; no hallucination)
4. Relational Co-Regulation (Connecting with God or other people)
5. Redemptive Outcome (Return to peace/joy, relational repair, or lesson anchored)
"""

from typing import List
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import (
    CriterionResult,
    EmotionalIntensityLevel,
    CoregulatorType,
)


class CriterionEvaluationDetail(BaseModel):
    """Evaluation result for an individual criterion."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    result: CriterionResult = Field(
        description="5-way evaluation result (met, partially_met, not_met, uncertain, not_applicable)"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0"
    )
    evidence_quote: str = Field(
        description="Direct verbatim quote from source text supporting the evaluation"
    )
    reasoning: str = Field(
        description="Detailed analytical reasoning explaining the evaluation"
    )


class EmotionalIntensityDetail(CriterionEvaluationDetail):
    """Criterion 2: Appropriate Emotional Intensity."""
    intensity_level: EmotionalIntensityLevel = Field(
        description="Arousal intensity level (flat_detached, appropriate_moderate, overwhelming_flooding)"
    )


class ExplicitEmotionSensationDetail(CriterionEvaluationDetail):
    """
    Criterion 3: Explicit Emotion & Somatic Sensations.
    Sensations must never be invented. If not mentioned in source, sensations_missing must be True.
    """
    emotions_identified: List[str] = Field(
        default_factory=list,
        description="List of explicit emotions named in the text"
    )
    sensations_identified: List[str] = Field(
        default_factory=list,
        description="List of explicit somatic/physical sensations named in the text"
    )
    sensations_missing: bool = Field(
        default=False,
        description="True if physical sensations are absent or unmentioned in the source narrative"
    )


class CoRegulationDetail(CriterionEvaluationDetail):
    """Criterion 4: Relational Co-Regulation."""
    coregulator_type: CoregulatorType = Field(
        description="Type of co-regulator identified (divine, human, both, or none)"
    )


class CriteriaBreakdown(BaseModel):
    """Structured breakdown of all five 4+ evaluation criteria."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    autobiographical_involvement: CriterionEvaluationDetail = Field(
        description="Criterion 1: First-person lived autobiographical experience"
    )
    appropriate_emotional_intensity: EmotionalIntensityDetail = Field(
        description="Criterion 2: Emotional arousal intensity"
    )
    explicit_emotion_and_body_sensations: ExplicitEmotionSensationDetail = Field(
        description="Criterion 3: Named feelings and somatic physical sensations"
    )
    relational_co_regulation: CoRegulationDetail = Field(
        description="Criterion 4: Relational presence and co-regulation"
    )
    redemptive_outcome: CriterionEvaluationDetail = Field(
        description="Criterion 5: Return to joy, repair, or spiritual/relational resolution"
    )

