"""
Mock AI provider for deterministic testing without network access or API credentials.

Supports:
  - Scenario-based responses keyed by a 'scenario' kwarg in AIRequestConfig.extra
  - Scenario "success":   valid boundary extraction + full evaluation responses
  - Scenario "uncertain": evaluation with uncertain_needs_review classification
  - Scenario "error":     simulated retryable provider error
  - Scenario "malformed": returns invalid JSON (triggers AISchemaValidationError)
  - Default:              falls back to "success"

Usage:
    provider = MockAIProvider()
    await provider.initialize()
    response = await provider.complete_structured(
        system_prompt="...",
        user_prompt="...",
        response_schema=StoryBoundaryExtractionResponse,
    )
"""

from __future__ import annotations

import json
from typing import Any, TypeVar

from pydantic import BaseModel

from app.services.ai.base import (
    AIProviderError,
    AIRequestConfig,
    AIResponse,
    AISchemaValidationError,
    AIUsageStats,
    BaseAIProvider,
)

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Canonical mock payloads — realistic Four Plus Story framework data
# ---------------------------------------------------------------------------

_BOUNDARY_SUCCESS = {
    "has_candidates": True,
    "candidates": [
        {
            "tentative_title": "The Day the Doctor's Words Changed Everything",
            "first_sentence": "I remember standing in that sterile waiting room when the nurse called my name.",
            "last_sentence": "And somehow, impossibly, I found peace in that moment — not because the news was good, but because I was not alone.",
            "approx_char_start": 1180,
            "approx_char_end": 3450,
            "evidence_quote": "I remember standing in that sterile waiting room when the nurse called my name.",
        }
    ],
}

_BOUNDARY_NO_CANDIDATES = {
    "has_candidates": False,
    "candidates": [],
}

_EVALUATION_SUCCESS = {
    "title": "The Day the Doctor's Words Changed Everything",
    "is_autobiographical": True,
    "narrator_gender": "unknown",
    "overall_classification": "confirmed_4_plus",
    "overall_confidence": 0.87,
    "criteria_breakdown": {
        "autobiographical_involvement": {
            "result": "met",
            "confidence": 0.95,
            "evidence_quote": "I remember standing in that sterile waiting room when the nurse called my name.",
            "reasoning": "First-person past-tense throughout. Speaker is the primary participant at the described event.",
        },
        "appropriate_emotional_intensity": {
            "result": "met",
            "confidence": 0.82,
            "intensity_level": "appropriate_moderate",
            "evidence_quote": "My hands were trembling but I was still present, still able to hear.",
            "reasoning": "Emotional arousal is authentic and digestible. Neither flat nor overwhelming.",
        },
        "explicit_emotion_and_body_sensations": {
            "result": "met",
            "confidence": 0.91,
            "emotions_identified": ["fear", "grief", "peace"],
            "sensations_identified": [
                "trembling hands",
                "knot in stomach",
                "tears blurring vision",
            ],
            "sensations_missing": False,
            "evidence_quote": "My hands were trembling, tears blurring my vision, a knot tightening in my stomach.",
            "reasoning": "Named emotions (fear, grief) paired with explicit somatic markers. Progression to peace.",
        },
        "relational_co_regulation": {
            "result": "met",
            "confidence": 0.88,
            "coregulator_type": "divine_god_jesus_spirit",
            "evidence_quote": "I whispered 'I can't do this alone' and felt a presence, steady and warm, hold me.",
            "reasoning": "Explicit relational turning toward God as co-regulator. Calming effect is described.",
        },
        "redemptive_outcome": {
            "result": "met",
            "confidence": 0.84,
            "evidence_quote": "And somehow, impossibly, I found peace — not because the news was good, but because I was not alone.",
            "reasoning": "Return to joy/peace through relational presence. Resolution is explicitly stated.",
        },
    },
    "assigned_variants": [
        {
            "variant": "return_to_joy",
            "assignment_source": "ai_proposed",
            "confidence": 0.86,
            "evidence_quote": "I found peace in that moment — not because the news was good, but because I was not alone.",
            "reasoning": "Narrative arc moves from fear and grief through relational co-regulation back to peace/joy.",
        }
    ],
    "emotions": [
        {
            "emotion": "fear",
            "energy_level": "high_energy",
            "progression_stage": "initial",
            "evidence_quote": "My hands were trembling, tears blurring my vision.",
            "source_page": 42,
            "source_char_offset": 1240,
            "sensations_identified": ["trembling hands", "tears blurring vision"],
            "sensations_missing": False,
        },
        {
            "emotion": "peace",
            "energy_level": "positive_connective",
            "progression_stage": "resolving",
            "evidence_quote": "I found peace in that moment.",
            "source_page": 44,
            "source_char_offset": 3100,
            "sensations_identified": [],
            "sensations_missing": True,
        },
    ],
    "step_analysis": {
        "setting": "A sterile hospital waiting room, afternoon, surrounded by other anxious families. Speaker is alone.",
        "trigger": "The nurse called the speaker's name and the doctor walked in with a grave expression.",
        "emotion_and_body_sensations": "Fear rising in the chest; trembling hands; knot tightening in stomach; tears blurring vision. Grief settling.",
        "point": "In the darkest moments we are not alone — God's presence holds us when our own strength fails.",
        "internal_thoughts": None,
        "relational_presence": "Quiet, steady sense of divine presence described as warm and stabilizing.",
    },
    "suggested_curated_telling": None,
    "reasoning_summary": (
        "This story meets all five 4+ criteria with high confidence. The autobiographical "
        "first-person framing is unambiguous. Emotional intensity is appropriately distressing "
        "without being traumatically flooding. Named emotions (fear, grief, peace) are anchored "
        "to explicit somatic markers. Relational co-regulation with God is described directly. "
        "The resolution is explicit and relational. The Return to Joy variant is a strong match."
    ),
}

_EVALUATION_UNCERTAIN = {
    "title": "A Quiet Disappointment",
    "is_autobiographical": True,
    "narrator_gender": "unknown",
    "overall_classification": "uncertain_needs_review",
    "overall_confidence": 0.52,
    "criteria_breakdown": {
        "autobiographical_involvement": {
            "result": "met",
            "confidence": 0.90,
            "evidence_quote": "When the rejection letter arrived, I set it down quietly.",
            "reasoning": "First-person framing throughout.",
        },
        "appropriate_emotional_intensity": {
            "result": "partially_met",
            "confidence": 0.55,
            "intensity_level": "flat_detached",
            "evidence_quote": "I told myself it was fine. These things happen.",
            "reasoning": "Emotional processing appears intellectualized. Genuine felt distress is subdued.",
        },
        "explicit_emotion_and_body_sensations": {
            "result": "not_met",
            "confidence": 0.70,
            "emotions_identified": ["disappointment"],
            "sensations_identified": [],
            "sensations_missing": True,
            "evidence_quote": "I told myself it was fine.",
            "reasoning": "No explicit physical body sensations mentioned anywhere in the narrative.",
        },
        "relational_co_regulation": {
            "result": "uncertain",
            "confidence": 0.45,
            "coregulator_type": "none",
            "evidence_quote": "I sat with the feeling by myself for a while.",
            "reasoning": "No clear co-regulation with God or another person. Ambiguous isolation.",
        },
        "redemptive_outcome": {
            "result": "partially_met",
            "confidence": 0.50,
            "evidence_quote": "I think I learned something about resilience, eventually.",
            "reasoning": "Vague, intellectualized resolution without explicit return to joy.",
        },
    },
    "assigned_variants": [],
    "emotions": [
        {
            "emotion": "sadness",
            "energy_level": "low_energy",
            "progression_stage": "initial",
            "evidence_quote": "When the rejection letter arrived, I set it down quietly.",
            "source_page": None,
            "source_char_offset": None,
            "sensations_identified": [],
            "sensations_missing": True,
        }
    ],
    "step_analysis": {
        "setting": "Home, indeterminate time, speaker alone.",
        "trigger": "Arrival of a rejection letter.",
        "emotion_and_body_sensations": "Quiet disappointment and sadness. No physical sensations reported in text.",
        "point": "Vaguely stated: resilience can be learned from disappointment.",
        "internal_thoughts": "Speaker tells themselves 'it was fine' — apparent minimization.",
        "relational_presence": None,
    },
    "suggested_curated_telling": None,
    "reasoning_summary": (
        "Classification is uncertain. The story is autobiographical but emotional processing is "
        "flat and intellectualized. No somatic sensations are present. Co-regulation is absent. "
        "Resolution is vague. Human reviewer should assess whether deeper somatic/relational "
        "elements exist in the original source that the AI may have missed."
    ),
}


class MockAIProvider(BaseAIProvider):
    """
    Deterministic AI provider for testing. No network access or API keys required.

    Scenario selection via AIRequestConfig.extra['scenario']:
      "success"            → valid boundary + evaluation responses
      "uncertain"          → uncertain_needs_review evaluation
      "no_candidates"      → boundary response with no candidates
      "error"              → raises retryable AIProviderError
      "auth_error"         → raises non-retryable AIProviderError
      "malformed"          → raises AISchemaValidationError (invalid JSON)
      anything else / None → defaults to "success"
    """

    _SIMULATED_LATENCY_MS = 25.0

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def default_model(self) -> str:
        return "mock-v1"

    async def initialize(self) -> None:
        """No-op. Mock requires no connections."""

    async def close(self) -> None:
        """No-op. Mock has no connections to release."""

    def _make_usage(self, content: str, config: AIRequestConfig | None) -> AIUsageStats:
        model = config.model_name if config and config.model_name else self.default_model
        # Approximate: 4 chars per token
        approx_tokens = max(1, len(content) // 4)
        return AIUsageStats(
            input_tokens=512,
            output_tokens=approx_tokens,
            total_tokens=512 + approx_tokens,
            model_name=model,
            provider_name=self.provider_name,
            latency_ms=self._SIMULATED_LATENCY_MS,
        )

    def _get_scenario(self, config: AIRequestConfig | None) -> str:
        if config and config.extra:
            return str(config.extra.get("scenario", "success"))
        return "success"

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        config: AIRequestConfig | None = None,
    ) -> AIResponse:
        """Return raw JSON string for the configured scenario."""
        scenario = self._get_scenario(config)

        if scenario == "error":
            raise AIProviderError(
                "Simulated transient provider error",
                provider=self.provider_name,
                status_code=503,
                retryable=True,
            )
        if scenario == "auth_error":
            raise AIProviderError(
                "Simulated authentication failure",
                provider=self.provider_name,
                status_code=401,
                retryable=False,
            )
        if scenario == "malformed":
            content = "{ this is not valid JSON }"
            return AIResponse(content=content, usage=self._make_usage(content, config))

        if scenario == "no_candidates":
            content = json.dumps(_BOUNDARY_NO_CANDIDATES)
        elif scenario == "uncertain":
            content = json.dumps(_EVALUATION_UNCERTAIN)
        else:
            # Default to boundary success when prompt suggests boundary detection
            if "boundary" in system_prompt.lower() or "boundary" in user_prompt.lower():
                content = json.dumps(_BOUNDARY_SUCCESS)
            else:
                content = json.dumps(_EVALUATION_SUCCESS)

        return AIResponse(content=content, usage=self._make_usage(content, config))

    async def complete_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[BaseModel],
        config: AIRequestConfig | None = None,
    ) -> AIResponse:
        """
        Return a validated structured response for the requested Pydantic schema.

        Raises:
            AIProviderError: on simulated transient or auth errors.
            AISchemaValidationError: on simulated malformed response.
        """
        import pydantic

        scenario = self._get_scenario(config)

        # Error scenarios — raised before attempting schema validation
        if scenario == "error":
            raise AIProviderError(
                "Simulated transient provider error",
                provider=self.provider_name,
                status_code=503,
                retryable=True,
            )
        if scenario == "auth_error":
            raise AIProviderError(
                "Simulated authentication failure",
                provider=self.provider_name,
                status_code=401,
                retryable=False,
            )
        if scenario == "malformed":
            raise AISchemaValidationError(
                message=f"Mock produced invalid JSON for schema {response_schema.__name__}",
                raw_content="{ this is not valid JSON }",
                schema_name=response_schema.__name__,
            )

        # Pick payload based on scenario + schema name
        schema_name = response_schema.__name__

        if "Boundary" in schema_name or "Extraction" in schema_name:
            if scenario == "no_candidates":
                raw = _BOUNDARY_NO_CANDIDATES
            else:
                raw = json.loads(json.dumps(_BOUNDARY_SUCCESS))
                for candidate in raw["candidates"]:
                    self._align_mock_offsets(candidate, user_prompt)
        elif scenario == "uncertain":
            raw = _EVALUATION_UNCERTAIN
        else:
            raw = _EVALUATION_SUCCESS

        # Validate payload against the schema — surfaces any mock drift early
        try:
            response_schema.model_validate(raw)
        except pydantic.ValidationError as exc:
            raise AISchemaValidationError(
                message=f"Mock payload failed schema validation for {schema_name}: {exc}",
                raw_content=json.dumps(raw),
                schema_name=schema_name,
            ) from exc

        content = json.dumps(raw)
        return AIResponse(content=content, usage=self._make_usage(content, config))

    @staticmethod
    def _align_mock_offsets(candidate: dict[str, Any], source_text: str) -> None:
        source_segments = candidate.get("source_segments", [])
        segments: list[dict[str, Any]] = [candidate, *source_segments]
        for segment in segments:
            first = segment.get("first_sentence")
            last = segment.get("last_sentence")
            if not isinstance(first, str) or not isinstance(last, str):
                continue
            start = source_text.find(first)
            end_start = source_text.find(last, start + len(first)) if start >= 0 else -1
            if start >= 0 and end_start >= 0:
                segment["approx_char_start"] = start
                segment["approx_char_end"] = end_start + len(last)

    async def health_check(self) -> bool:
        return True
