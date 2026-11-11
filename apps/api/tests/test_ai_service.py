from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Optional, Type

import pytest

from app.schemas.ai import StoryBoundaryExtractionResponse, StoryEvaluationResponse
from app.schemas.enums import FourPlusClassification
from app.services.ai.base import (
    AIProviderError,
    AIRequestConfig,
    AIResponse,
    AISchemaValidationError,
    AIUsageStats,
    BaseAIProvider,
)
from app.services.ai.anthropic import AnthropicProvider
from app.services.ai.gemini import GeminiProvider
from app.services.ai.manager import AIServiceManager
from app.services.ai.mock import MockAIProvider


@pytest.mark.asyncio
async def test_mock_provider_satisfies_base_interface() -> None:
    provider = MockAIProvider()
    assert isinstance(provider, BaseAIProvider)
    assert provider.provider_name == "mock"


@pytest.mark.asyncio
async def test_mock_boundary_response_validates() -> None:
    provider = MockAIProvider()
    response = await provider.complete_structured(
        system_prompt="boundary detection",
        user_prompt="A small example story.",
        response_schema=StoryBoundaryExtractionResponse,
    )
    parsed = StoryBoundaryExtractionResponse.model_validate_json(response.content)
    assert parsed.has_candidates is True
    assert len(parsed.candidates) >= 1


@pytest.mark.asyncio
async def test_mock_evaluation_handles_uncertain_classification() -> None:
    provider = MockAIProvider()
    response = await provider.complete_structured(
        system_prompt="evaluation",
        user_prompt="A quiet disappointment.",
        response_schema=StoryEvaluationResponse,
        config=AIRequestConfig(extra={"scenario": "uncertain"}),
    )
    parsed = StoryEvaluationResponse.model_validate_json(response.content)
    assert parsed.overall_classification == FourPlusClassification.UNCERTAIN_NEEDS_REVIEW


@pytest.mark.asyncio
async def test_mock_evaluation_includes_valid_narrator_gender() -> None:
    provider = MockAIProvider()
    response = await provider.complete_structured(
        system_prompt="evaluation",
        user_prompt="A story without explicit gender clues.",
        response_schema=StoryEvaluationResponse,
    )
    parsed = StoryEvaluationResponse.model_validate_json(response.content)
    assert parsed.narrator_gender.value == "unknown"


@pytest.mark.parametrize("gender", ["male", "female", "unknown"])
@pytest.mark.asyncio
async def test_evaluation_schema_accepts_supported_narrator_genders(gender: str) -> None:
    provider = MockAIProvider()
    response = await provider.complete_structured(
        system_prompt="evaluation",
        user_prompt="A story for schema validation.",
        response_schema=StoryEvaluationResponse,
    )
    payload = json.loads(response.content)
    payload["narrator_gender"] = gender
    parsed = StoryEvaluationResponse.model_validate(payload)
    assert parsed.narrator_gender.value == gender


@pytest.mark.asyncio
async def test_mock_invalid_response_rejected() -> None:
    provider = MockAIProvider()
    with pytest.raises(AISchemaValidationError):
        await provider.complete_structured(
            system_prompt="evaluation",
            user_prompt="invalid mock response",
            response_schema=StoryEvaluationResponse,
            config=AIRequestConfig(extra={"scenario": "malformed"}),
        )


def test_anthropic_strict_schema_disallows_additional_properties_on_all_objects() -> None:
    schema = AnthropicProvider._apply_strict_schema_constraints(
        StoryEvaluationResponse.model_json_schema()
    )

    def assert_no_additional_properties_for_objects(value: object) -> None:
        if isinstance(value, dict):
            if value.get("type") == "object":
                assert value.get("additionalProperties") is False
            for nested_value in value.values():
                assert_no_additional_properties_for_objects(nested_value)
        elif isinstance(value, list):
            for nested_value in value:
                assert_no_additional_properties_for_objects(nested_value)

    assert_no_additional_properties_for_objects(schema)


def test_anthropic_schema_cleaning_removes_unsupported_constraints_recursively() -> None:
    schema = {
        "type": "object",
        "properties": {
            "count": {
                "type": "integer",
                "minimum": 1,
                "maximum": 10,
                "exclusiveMinimum": 0,
                "exclusiveMaximum": 11,
                "multipleOf": 1,
            },
            "text": {
                "type": "string",
                "minLength": 1,
                "maxLength": 20,
                "pattern": "^[a-z]+$",
            },
            "nested": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"minimum": {"type": "string", "pattern": ".*"}},
                },
            },
        },
        "$defs": {
            "NestedDefinition": {
                "type": "object",
                "properties": {"value": {"type": "integer", "minimum": 0}},
            }
        },
    }

    cleaned = AnthropicProvider._apply_strict_schema_constraints(schema)

    assert cleaned["additionalProperties"] is False
    assert "minimum" not in cleaned["properties"]["count"]
    assert "maximum" not in cleaned["properties"]["count"]
    assert "exclusiveMinimum" not in cleaned["properties"]["count"]
    assert "exclusiveMaximum" not in cleaned["properties"]["count"]
    assert "multipleOf" not in cleaned["properties"]["count"]
    assert "minLength" not in cleaned["properties"]["text"]
    assert "maxLength" not in cleaned["properties"]["text"]
    assert "pattern" not in cleaned["properties"]["text"]
    nested_item = cleaned["properties"]["nested"]["items"]
    assert nested_item["additionalProperties"] is False
    assert "minimum" in nested_item["properties"]
    assert "pattern" not in nested_item["properties"]["minimum"]
    assert cleaned["$defs"]["NestedDefinition"]["additionalProperties"] is False
    assert "minimum" not in cleaned["$defs"]["NestedDefinition"]["properties"]["value"]


@pytest.mark.asyncio
async def test_anthropic_retries_oversized_tool_grammar_with_validated_json() -> None:
    class GrammarTooLargeError(Exception):
        status_code = 400

    class FakeMessages:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        async def create(self, **kwargs: object) -> SimpleNamespace:
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                raise GrammarTooLargeError("The compiled grammar is too large")
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="text",
                        text='{"has_candidates": false, "candidates": []}',
                    )
                ],
                usage=SimpleNamespace(input_tokens=10, output_tokens=5),
            )

    provider = AnthropicProvider(api_key="test-key")
    messages = FakeMessages()
    provider._client = SimpleNamespace(messages=messages)

    response = await provider.complete_structured(
        system_prompt="Return a boundary extraction response.",
        user_prompt="No story here.",
        response_schema=StoryBoundaryExtractionResponse,
    )

    assert len(messages.calls) == 2
    assert "tools" in messages.calls[0]
    assert "tools" not in messages.calls[1]
    assert "JSON Schema:" in str(messages.calls[1]["system"])
    parsed = StoryBoundaryExtractionResponse.model_validate_json(response.content)
    assert parsed.has_candidates is False


@pytest.mark.asyncio
async def test_manager_uses_primary_provider_without_fallback() -> None:
    manager = AIServiceManager(primary_provider="mock", fallback_providers=[])
    response = await manager.complete_structured(
        system_prompt="boundary detection",
        user_prompt="Some story text",
        response_schema=StoryBoundaryExtractionResponse,
    )
    assert response.usage.provider_name == "mock"
    assert response.usage.model_name == "mock-v1"


def test_gemini_classifies_rate_limits_as_non_retryable_and_transients_as_retryable() -> None:
    provider = GeminiProvider(api_key="test-key")

    class RateLimitError(Exception):
        status_code = 429

    unavailable = provider._classify_error(Exception("503 Service Unavailable"))
    rate_limited = provider._classify_error(RateLimitError("too many requests"))
    resource_exhausted = provider._classify_error(Exception("RESOURCE_EXHAUSTED"))
    timeout = provider._classify_error(TimeoutError())
    connection = provider._classify_error(ConnectionError("connection reset"))

    assert unavailable.retryable is True
    assert rate_limited.retryable is False
    assert rate_limited.status_code == 429
    assert resource_exhausted.retryable is False
    assert timeout.retryable is True
    assert connection.retryable is True


@pytest.mark.asyncio
async def test_gemini_structured_request_enforces_configured_timeout() -> None:
    class HangingModels:
        async def generate_content(self, **_kwargs: object) -> None:
            await asyncio.Event().wait()

    provider = GeminiProvider(api_key="test-key", model="test-model")
    provider._client = SimpleNamespace(aio=SimpleNamespace(models=HangingModels()))

    with pytest.raises(AIProviderError) as error:
        await provider.complete_structured(
            system_prompt="test",
            user_prompt="story",
            response_schema=StoryBoundaryExtractionResponse,
            config=AIRequestConfig(timeout_seconds=0.01),
        )

    assert error.value.retryable is True


@pytest.mark.asyncio
async def test_manager_retries_transient_failures_before_succeeding() -> None:
    class FlakyProvider(BaseAIProvider):
        def __init__(self) -> None:
            self.calls = 0

        @property
        def provider_name(self) -> str:
            return "flaky"

        @property
        def default_model(self) -> str:
            return "flaky-v1"

        async def initialize(self) -> None:
            return None

        async def close(self) -> None:
            return None

        async def complete(self, system_prompt: str, user_prompt: str, config: Optional[AIRequestConfig] = None) -> AIResponse:
            return AIResponse(content="ok", usage=AIUsageStats(provider_name=self.provider_name, model_name=self.default_model))

        async def complete_structured(
            self,
            system_prompt: str,
            user_prompt: str,
            response_schema: Type,
            config: Optional[AIRequestConfig] = None,
        ) -> AIResponse:
            self.calls += 1
            if self.calls == 1:
                raise AIProviderError("transient failure", provider=self.provider_name, status_code=503, retryable=True)
            payload = {"has_candidates": True, "candidates": []}
            return AIResponse(content=json.dumps(payload), usage=AIUsageStats(provider_name=self.provider_name, model_name=self.default_model))

    provider = FlakyProvider()
    manager = AIServiceManager(primary_provider="flaky", fallback_providers=[], providers={"flaky": provider})
    http = await manager.complete_structured(
        system_prompt="boundary detection",
        user_prompt="story",
        response_schema=StoryBoundaryExtractionResponse,
    )
    assert provider.calls == 2
    assert http.usage.provider_name == "flaky"


@pytest.mark.asyncio
async def test_manager_falls_back_after_exhausted_transient_failure() -> None:
    class FailingProvider(BaseAIProvider):
        @property
        def provider_name(self) -> str:
            return "primary"

        @property
        def default_model(self) -> str:
            return "primary-v1"

        async def initialize(self) -> None:
            return None

        async def close(self) -> None:
            return None

        async def complete(self, system_prompt: str, user_prompt: str, config: Optional[AIRequestConfig] = None) -> AIResponse:
            raise AIProviderError("transient", provider=self.provider_name, status_code=503, retryable=True)

        async def complete_structured(
            self,
            system_prompt: str,
            user_prompt: str,
            response_schema: Type,
            config: Optional[AIRequestConfig] = None,
        ) -> AIResponse:
            raise AIProviderError("transient", provider=self.provider_name, status_code=503, retryable=True)

    manager = AIServiceManager(
        primary_provider="primary",
        fallback_providers=["mock"],
        providers={
            "primary": FailingProvider(),
            "mock": MockAIProvider(),
        },
    )
    response = await manager.complete_structured(
        system_prompt="boundary detection",
        user_prompt="story",
        response_schema=StoryBoundaryExtractionResponse,
    )
    assert response.usage.provider_name == "mock"
    assert StoryBoundaryExtractionResponse.model_validate_json(response.content).has_candidates is True


@pytest.mark.asyncio
async def test_manager_does_not_fallback_for_permanent_errors() -> None:
    class PermanentFailureProvider(BaseAIProvider):
        @property
        def provider_name(self) -> str:
            return "permanent"

        @property
        def default_model(self) -> str:
            return "permanent-v1"

        async def initialize(self) -> None:
            return None

        async def close(self) -> None:
            return None

        async def complete(self, system_prompt: str, user_prompt: str, config: Optional[AIRequestConfig] = None) -> AIResponse:
            raise AIProviderError("bad credentials", provider=self.provider_name, status_code=401, retryable=False)

        async def complete_structured(
            self,
            system_prompt: str,
            user_prompt: str,
            response_schema: Type,
            config: Optional[AIRequestConfig] = None,
        ) -> AIResponse:
            raise AIProviderError("bad credentials", provider=self.provider_name, status_code=401, retryable=False)

    manager = AIServiceManager(
        primary_provider="permanent",
        fallback_providers=["mock"],
        providers={
            "permanent": PermanentFailureProvider(),
            "mock": MockAIProvider(),
        },
    )
    with pytest.raises(AIProviderError):
        await manager.complete_structured(
            system_prompt="boundary detection",
            user_prompt="story",
            response_schema=StoryBoundaryExtractionResponse,
        )


@pytest.mark.asyncio
async def test_mock_provider_health_check_is_true() -> None:
    provider = MockAIProvider()
    assert await provider.health_check() is True
