"""
Task 1.2: Cross-language parity fixture tests for Pydantic v2 schemas.

These tests verify:
1. Pydantic schema files import cleanly.
2. All enum values match the agreed taxonomy.
3. Sample JSON payloads (from fixtures/sample_payloads.json) validate
   against each Pydantic schema model.
4. All required fields are present and serialization round-trips losslessly.

Run with:
    pytest apps/api/tests/test_schemas.py -v

Requires pydantic>=2.0 installed (apps/api/.venv or system).
"""

from __future__ import annotations

import json
import os

import pytest

# ---------------------------------------------------------------------------
# Import schema modules — this acts as the first gate (import-time errors)
# ---------------------------------------------------------------------------
from app.schemas import (
    CandidateStoryBoundary,
    CoregulatorType,
    CriteriaBreakdown,
    CriterionEvaluationDetail,
    CriterionResult,
    DocumentBase,
    DocumentCreate,
    DocumentInDB,
    DocumentRightsStatus,
    DocumentType,
    EmotionalIntensityLevel,
    EmotionEnergyLevel,
    EmotionType,
    FourPlusClassification,
    HybridSearchRequest,
    HybridSearchResponse,
    JobStatus,
    NarratorGender,
    ProgressionStage,
    ReviewAction,
    ReviewActionRequest,
    ReviewActionResponse,
    ReviewQueueItem,
    StepAnalysis,
    StepAnalysisInDB,
    StoryBase,
    StoryBoundaryExtractionResponse,
    StoryDetail,
    StoryEmotion,
    StoryEvaluationResponse,
    StorySourceSpanBase,
    StoryStatus,
    StoryVariant,
    StoryVariantAssignment,
    StoryVisibility,
    UserRole,
)

# ---------------------------------------------------------------------------
# Load fixture payloads
# ---------------------------------------------------------------------------
FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "sample_payloads.json")

@pytest.fixture(scope="module")
def payloads():
    with open(FIXTURE_PATH) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Enum integrity tests
# ---------------------------------------------------------------------------
class TestEnumIntegrity:
    def test_story_variant_values(self):
        expected = {"return_to_joy", "acting_like_myself", "godsight_immanuel", "appreciation_joy_spreading"}
        actual = {v.value for v in StoryVariant}
        assert actual == expected

    def test_story_variant_excludes_prohibited_values(self):
        prohibited = {"distress_to_peace", "rupture_and_repair", "endurance_and_hope"}
        actual = {v.value for v in StoryVariant}
        overlap = prohibited & actual
        assert overlap == set(), f"Prohibited variants found: {overlap}"

    def test_story_status_values(self):
        expected = {"discovered_pending_review", "under_review", "approved", "rejected", "archived"}
        actual = {v.value for v in StoryStatus}
        assert actual == expected

    def test_visibility_values(self):
        expected = {"internal_only", "registered_users", "public"}
        actual = {v.value for v in StoryVisibility}
        assert actual == expected

    def test_narrator_gender_values(self):
        assert {v.value for v in NarratorGender} == {"male", "female", "unknown"}

    def test_four_plus_classification_values(self):
        expected = {"confirmed_4_plus", "not_4_plus", "uncertain_needs_review"}
        actual = {v.value for v in FourPlusClassification}
        assert actual == expected

    def test_criterion_result_has_five_values(self):
        expected = {"met", "partially_met", "not_met", "uncertain", "not_applicable"}
        actual = {v.value for v in CriterionResult}
        assert actual == expected

    def test_big_6_emotion_types(self):
        big_six = {"fear", "anger", "sadness", "shame", "disgust", "hopeless_despair"}
        positive = {"joy", "gratitude", "peace", "other"}
        actual = {v.value for v in EmotionType}
        assert big_six <= actual, f"Missing Big 6 values: {big_six - actual}"
        assert positive <= actual, f"Missing positive values: {positive - actual}"

    def test_emotion_energy_levels(self):
        expected = {"high_energy", "low_energy", "positive_connective"}
        actual = {v.value for v in EmotionEnergyLevel}
        assert actual == expected

    def test_progression_stages(self):
        expected = {"initial", "escalation", "peak", "shift", "resolving"}
        actual = {v.value for v in ProgressionStage}
        assert actual == expected

    def test_document_rights_status_values(self):
        expected = {"public_domain", "licensed", "restricted_internal", "fair_use_educational"}
        actual = {v.value for v in DocumentRightsStatus}
        assert actual == expected

    def test_coregulator_types(self):
        expected = {"divine_god_jesus_spirit", "human_other", "both", "none"}
        actual = {v.value for v in CoregulatorType}
        assert actual == expected

    def test_emotional_intensity_levels(self):
        expected = {"flat_detached", "appropriate_moderate", "overwhelming_flooding"}
        actual = {v.value for v in EmotionalIntensityLevel}
        assert actual == expected

    def test_review_action_values(self):
        expected = {"approve", "reject", "request_revision", "edit_and_approve"}
        actual = {v.value for v in ReviewAction}
        assert actual == expected


# ---------------------------------------------------------------------------
# Payload fixture validation tests
# ---------------------------------------------------------------------------
class TestStoryVariantAssignment:
    def test_valid_fixture(self, payloads):
        data = payloads["story_variant_assignment"]
        m = StoryVariantAssignment.model_validate(data)
        assert m.variant == StoryVariant.RETURN_TO_JOY
        assert 0.0 <= m.confidence <= 1.0
        assert m.evidence_quote != ""

    def test_round_trip_serialization(self, payloads):
        data = payloads["story_variant_assignment"]
        m = StoryVariantAssignment.model_validate(data)
        serialized = m.model_dump(mode="json")
        m2 = StoryVariantAssignment.model_validate(serialized)
        assert m == m2

    def test_rejects_prohibited_variant(self):
        with pytest.raises(Exception):
            StoryVariantAssignment(
                variant="distress_to_peace",  # type: ignore[arg-type]
                assignment_source="ai_proposed",
                confidence=0.8,
                evidence_quote="...",
                reasoning="...",
            )


class TestStoryEmotion:
    def test_valid_fixture(self, payloads):
        data = payloads["story_emotion"]
        m = StoryEmotion.model_validate(data)
        assert m.emotion == EmotionType.FEAR
        assert m.energy_level == EmotionEnergyLevel.HIGH_ENERGY
        assert len(m.sensations_identified) == 2
        assert m.sensations_missing is False

    def test_missing_sensations_flag(self):
        m = StoryEmotion(
            emotion=EmotionType.SHAME,
            energy_level=EmotionEnergyLevel.LOW_ENERGY,
            progression_stage=ProgressionStage.INITIAL,
            evidence_quote="I felt so ashamed I couldn't speak.",
            sensations_identified=[],
            sensations_missing=True,
        )
        assert m.sensations_missing is True
        assert m.sensations_identified == []

    def test_round_trip_serialization(self, payloads):
        data = payloads["story_emotion"]
        m = StoryEmotion.model_validate(data)
        m2 = StoryEmotion.model_validate(m.model_dump(mode="json"))
        assert m == m2


class TestStepAnalysis:
    def test_valid_fixture(self, payloads):
        data = payloads["step_analysis"]
        m = StepAnalysis.model_validate(data)
        assert m.setting != ""
        assert m.trigger != ""
        assert m.emotion_and_body_sensations != ""
        assert m.point != ""

    def test_supplementary_fields_optional(self, payloads):
        data = payloads["step_analysis"]
        m = StepAnalysis.model_validate(data)
        assert m.internal_thoughts is None
        assert m.relational_presence is None

    def test_supplementary_does_not_replace_step(self):
        """Verify STEP core fields are always required."""
        import pydantic
        with pytest.raises((pydantic.ValidationError, TypeError)):
            StepAnalysis(
                setting="A room",
                trigger="Something happened",
                # Missing: emotion_and_body_sensations and point
            )

    def test_round_trip_serialization(self, payloads):
        data = payloads["step_analysis"]
        m = StepAnalysis.model_validate(data)
        m2 = StepAnalysis.model_validate(m.model_dump(mode="json"))
        assert m == m2


class TestCandidateStoryBoundary:
    def test_valid_fixture(self, payloads):
        data = payloads["candidate_story_boundary"]
        m = CandidateStoryBoundary.model_validate(data)
        assert m.approx_char_start >= 0
        assert m.approx_char_end > m.approx_char_start

    def test_no_verbatim_full_text_field(self):
        """AI output model must NOT contain a verbatim_text field."""
        fields = set(CandidateStoryBoundary.model_fields.keys())
        assert "verbatim_text" not in fields, (
            "CandidateStoryBoundary must not contain verbatim_text to prevent AI hallucination"
        )

    def test_evaluation_response_no_verbatim_text_field(self):
        """StoryEvaluationResponse must NOT contain verbatim_text field."""
        fields = set(StoryEvaluationResponse.model_fields.keys())
        assert "verbatim_text" not in fields


class TestNarratorGender:
    def test_story_defaults_narrator_gender_to_unknown(self):
        from uuid import uuid4

        story = StoryBase(
            document_id=uuid4(),
            title="A story",
            original_text="I remember that day.",
            original_word_count=4,
            estimated_spoken_duration_seconds=2,
        )
        assert story.narrator_gender is NarratorGender.UNKNOWN

    def test_enum_rejects_invalid_values(self):
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            StoryBase(
                document_id="00000000-0000-0000-0000-000000000001",
                title="A story",
                original_text="I remember that day.",
                original_word_count=4,
                estimated_spoken_duration_seconds=2,
                narrator_gender="other",
            )


class TestStoryBoundaryExtractionResponse:
    def test_no_candidates(self):
        m = StoryBoundaryExtractionResponse(has_candidates=False, candidates=[])
        assert m.has_candidates is False
        assert len(m.candidates) == 0


class TestCriterionEvaluationDetail:
    def test_valid_fixture(self, payloads):
        data = payloads["criterion_evaluation"]
        m = CriterionEvaluationDetail.model_validate(data)
        assert m.result == CriterionResult.MET
        assert 0.0 <= m.confidence <= 1.0

    def test_confidence_bounds(self):
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            CriterionEvaluationDetail(
                result=CriterionResult.MET,
                confidence=1.5,  # out of bounds
                evidence_quote="...",
                reasoning="...",
            )


class TestHybridSearchRequest:
    def test_valid_fixture(self, payloads):
        data = payloads["hybrid_search_request"]
        m = HybridSearchRequest.model_validate(data)
        assert m.query == "overcoming fear with God's help"
        assert m.filter_variant == StoryVariant.RETURN_TO_JOY
        assert m.filter_emotion == EmotionType.FEAR
        assert 1 <= m.limit <= 50


class TestReviewActionRequest:
    def test_valid_fixture(self, payloads):
        data = payloads["review_action_request"]
        m = ReviewActionRequest.model_validate(data)
        assert m.action == ReviewAction.APPROVE
        assert m.visibility == StoryVisibility.PUBLIC


# ---------------------------------------------------------------------------
# Parity sanity check: Pydantic enum values match TypeScript Zod definitions
# ---------------------------------------------------------------------------
class TestZodParity:
    """
    Validates that Pydantic enum values match the locked TypeScript Zod enums.
    If the TS/Zod schema is updated, these tests must be updated simultaneously.
    """
    TS_VARIANTS = ["return_to_joy", "acting_like_myself", "godsight_immanuel", "appreciation_joy_spreading"]
    TS_STORY_STATUS = ["discovered_pending_review", "under_review", "approved", "rejected", "archived"]
    TS_VISIBILITY = ["internal_only", "registered_users", "public"]
    TS_NARRATOR_GENDER = ["male", "female", "unknown"]
    TS_CLASSIFICATION = ["confirmed_4_plus", "not_4_plus", "uncertain_needs_review"]
    TS_CRITERION_RESULT = ["met", "partially_met", "not_met", "uncertain", "not_applicable"]
    TS_EMOTION_TYPES = ["fear", "anger", "sadness", "shame", "disgust", "hopeless_despair", "joy", "gratitude", "peace", "other"]
    TS_ENERGY_LEVELS = ["high_energy", "low_energy", "positive_connective"]
    TS_PROGRESSION_STAGES = ["initial", "escalation", "peak", "shift", "resolving"]
    TS_RIGHTS_STATUS = ["public_domain", "licensed", "restricted_internal", "fair_use_educational"]
    TS_USER_ROLES = ["super_admin", "curator", "reviewer", "church_member", "public_guest"]
    TS_DOC_TYPES = ["pdf_book", "pdf_article", "txt_transcript", "txt_story_note"]
    TS_JOB_STATUS = ["pending", "processing", "completed", "failed", "cancelled"]

    def _enum_values(self, enum_cls):
        return sorted(v.value for v in enum_cls)

    def test_story_variant_parity(self):
        assert self._enum_values(StoryVariant) == sorted(self.TS_VARIANTS)

    def test_story_status_parity(self):
        assert self._enum_values(StoryStatus) == sorted(self.TS_STORY_STATUS)

    def test_story_visibility_parity(self):
        assert self._enum_values(StoryVisibility) == sorted(self.TS_VISIBILITY)

    def test_narrator_gender_parity(self):
        assert self._enum_values(NarratorGender) == sorted(self.TS_NARRATOR_GENDER)

    def test_four_plus_classification_parity(self):
        assert self._enum_values(FourPlusClassification) == sorted(self.TS_CLASSIFICATION)

    def test_criterion_result_parity(self):
        assert self._enum_values(CriterionResult) == sorted(self.TS_CRITERION_RESULT)

    def test_emotion_type_parity(self):
        assert self._enum_values(EmotionType) == sorted(self.TS_EMOTION_TYPES)

    def test_emotion_energy_level_parity(self):
        assert self._enum_values(EmotionEnergyLevel) == sorted(self.TS_ENERGY_LEVELS)

    def test_progression_stage_parity(self):
        assert self._enum_values(ProgressionStage) == sorted(self.TS_PROGRESSION_STAGES)

    def test_document_rights_parity(self):
        assert self._enum_values(DocumentRightsStatus) == sorted(self.TS_RIGHTS_STATUS)

    def test_user_role_parity(self):
        assert self._enum_values(UserRole) == sorted(self.TS_USER_ROLES)

    def test_document_type_parity(self):
        assert self._enum_values(DocumentType) == sorted(self.TS_DOC_TYPES)

    def test_job_status_parity(self):
        assert self._enum_values(JobStatus) == sorted(self.TS_JOB_STATUS)
