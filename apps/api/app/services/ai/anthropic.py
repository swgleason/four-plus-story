"""
Anthropic Claude adapter for the provider-independent AI service layer.

Implements BaseAIProvider using the official Anthropic Python SDK.
Structured output uses Anthropic's tool_use API with automatic tool selection
and strict input-schema validation.

Required environment variables:
    ANTHROPIC_API_KEY   — Anthropic API key
    ANTHROPIC_MODEL     — Model name (default: claude-3-5-sonnet-20241022)

SDK documentation: https://docs.anthropic.com/en/api/messages
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional, Type

from pydantic import BaseModel

from app.core.config import get_settings
from app.services.ai.base import (
    AIProviderError,
    AIRequestConfig,
    AIResponse,
    AISchemaValidationError,
    AIUsageStats,
    BaseAIProvider,
)

_UNSUPPORTED_SCHEMA_KEYWORDS = {
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minLength",
    "maxLength",
    "pattern",
}
_SCHEMA_METADATA_KEYWORDS = {
    "$comment",
    "default",
    "deprecated",
    "description",
    "examples",
    "readOnly",
    "title",
    "writeOnly",
}
_SCHEMA_MAP_KEYWORDS = {
    "$defs",
    "definitions",
    "dependencies",
    "dependentSchemas",
    "patternProperties",
    "properties",
}
_SCHEMA_LIST_KEYWORDS = {"allOf", "anyOf", "oneOf", "prefixItems"}
_SCHEMA_SINGLE_KEYWORDS = {
    "additionalItems",
    "additionalProperties",
    "contains",
    "contentSchema",
    "else",
    "if",
    "items",
    "not",
    "propertyNames",
    "then",
    "unevaluatedItems",
    "unevaluatedProperties",
}

logger = logging.getLogger(__name__)


class AnthropicProvider(BaseAIProvider):
    """
    Anthropic Claude adapter.

    Uses tool_use with strict schema validation to obtain structured JSON.
    This avoids the unreliability of parsing JSON from prose responses.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.anthropic_api_key
        self._model = model or settings.anthropic_model
        self._client: Optional[Any] = None  # anthropic.AsyncAnthropic

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def default_model(self) -> str:
        return self._model

    async def initialize(self) -> None:
        """Instantiate the Anthropic async client."""
        if not self._api_key:
            raise AIProviderError(
                "ANTHROPIC_API_KEY is not set. "
                "Set it in environment variables or use the mock provider for development.",
                provider=self.provider_name,
                status_code=None,
                retryable=False,
            )
        try:
            import anthropic  # deferred import — only required when provider is active
            self._client = anthropic.AsyncAnthropic(api_key=self._api_key)
        except ImportError as exc:
            raise AIProviderError(
                "anthropic package is not installed. "
                "Run: pip install anthropic>=0.40.0",
                provider=self.provider_name,
                retryable=False,
            ) from exc

    async def close(self) -> None:
        """Release the Anthropic client."""
        if self._client is not None:
            await self._client.close()
            self._client = None

    def _ensure_initialized(self) -> Any:
        if self._client is None:
            raise AIProviderError(
                "AnthropicProvider is not initialized. Call initialize() first.",
                provider=self.provider_name,
                retryable=False,
            )
        return self._client

    def _resolve_config(self, config: Optional[AIRequestConfig]) -> AIRequestConfig:
        settings = get_settings()
        cfg = config or AIRequestConfig()
        if not cfg.model_name:
            cfg.model_name = self._model
        if cfg.temperature == 0.0:
            cfg.temperature = settings.ai_temperature
        if cfg.max_tokens == 4096:
            cfg.max_tokens = settings.ai_max_tokens
        if cfg.timeout_seconds == 60.0:
            cfg.timeout_seconds = settings.ai_timeout_seconds
        return cfg

    def _sampling_parameters(self, config: AIRequestConfig) -> dict[str, Any]:
        if config.temperature == 0.0:
            return {}
        return {"extra_body": {"temperature": config.temperature}}

    @staticmethod
    def _apply_strict_schema_constraints(schema: Any) -> Any:
        if isinstance(schema, list):
            for value in schema:
                AnthropicProvider._apply_strict_schema_constraints(value)
            return schema
        if not isinstance(schema, dict):
            return schema

        for keyword in _UNSUPPORTED_SCHEMA_KEYWORDS | _SCHEMA_METADATA_KEYWORDS:
            schema.pop(keyword, None)

        schema_type = schema.get("type")
        if schema_type == "object" or (
            isinstance(schema_type, list) and "object" in schema_type
        ):
            schema["additionalProperties"] = False

        for keyword in _SCHEMA_MAP_KEYWORDS:
            value = schema.get(keyword)
            if isinstance(value, dict):
                for nested_schema in value.values():
                    AnthropicProvider._apply_strict_schema_constraints(nested_schema)
        for keyword in _SCHEMA_LIST_KEYWORDS:
            value = schema.get(keyword)
            if isinstance(value, list):
                AnthropicProvider._apply_strict_schema_constraints(value)
        for keyword in _SCHEMA_SINGLE_KEYWORDS:
            value = schema.get(keyword)
            if isinstance(value, (dict, list)):
                AnthropicProvider._apply_strict_schema_constraints(value)
        return schema

    @staticmethod
    def _is_compiled_grammar_too_large_error(exc: Exception) -> bool:
        return (
            getattr(exc, "status_code", None) == 400
            and "compiled grammar is too large" in str(exc).lower()
        )

    async def _complete_structured_json_fallback(
        self,
        client: Any,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[BaseModel],
        config: AIRequestConfig,
    ) -> AIResponse:
        import pydantic

        schema = self._apply_strict_schema_constraints(response_schema.model_json_schema())
        fallback_system_prompt = (
            f"{system_prompt}\n\n"
            "Return exactly one valid JSON object matching this JSON Schema. "
            "Do not include Markdown fences or explanatory text.\n"
            f"JSON Schema:\n{json.dumps(schema, separators=(',', ':'))}"
        )
        started_at = time.monotonic()
        try:
            message = await client.messages.create(
                model=config.model_name,
                max_tokens=config.max_tokens,
                system=fallback_system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                timeout=config.timeout_seconds,
                **self._sampling_parameters(config),
            )
        except Exception as exc:
            raise self._classify_error(exc) from exc

        content = "\n".join(
            block.text
            for block in message.content
            if getattr(block, "type", None) == "text"
        )
        try:
            validated = response_schema.model_validate_json(content)
        except pydantic.ValidationError as exc:
            raise AISchemaValidationError(
                message=f"Anthropic JSON fallback failed schema validation: {exc}",
                raw_content=content,
                schema_name=response_schema.__name__,
            ) from exc

        return AIResponse(
            content=validated.model_dump_json(),
            usage=self._make_usage(
                message.usage,
                config.model_name,
                (time.monotonic() - started_at) * 1000,
            ),
            raw_response=message,
        )

    def _make_usage(
        self, raw_usage: Any, model_name: str, latency_ms: float
    ) -> AIUsageStats:
        return AIUsageStats(
            input_tokens=getattr(raw_usage, "input_tokens", 0),
            output_tokens=getattr(raw_usage, "output_tokens", 0),
            total_tokens=(
                getattr(raw_usage, "input_tokens", 0)
                + getattr(raw_usage, "output_tokens", 0)
            ),
            model_name=model_name,
            provider_name=self.provider_name,
            latency_ms=latency_ms,
        )

    def _classify_error(self, exc: Exception) -> AIProviderError:
        """Map Anthropic SDK exceptions to normalized AIProviderError."""
        try:
            import anthropic
            if isinstance(exc, anthropic.APIStatusError):
                sc = exc.status_code
                retryable = sc in (429, 500, 502, 503, 529)
                return AIProviderError(
                    str(exc), provider=self.provider_name, status_code=sc, retryable=retryable
                )
            if isinstance(exc, anthropic.APIConnectionError):
                return AIProviderError(
                    str(exc), provider=self.provider_name, retryable=True
                )
            if isinstance(exc, anthropic.APITimeoutError):
                return AIProviderError(
                    str(exc), provider=self.provider_name, retryable=True
                )
        except ImportError:
            pass
        return AIProviderError(
            f"Unexpected error from Anthropic: {exc}",
            provider=self.provider_name,
            retryable=False,
        )

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        config: Optional[AIRequestConfig] = None,
    ) -> AIResponse:
        """Send a standard text completion request to Claude."""
        import anthropic

        client = self._ensure_initialized()
        cfg = self._resolve_config(config)

        t0 = time.monotonic()
        try:
            message = await client.messages.create(
                model=cfg.model_name,
                max_tokens=cfg.max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                timeout=cfg.timeout_seconds,
                **self._sampling_parameters(cfg),
            )
        except Exception as exc:
            raise self._classify_error(exc) from exc

        latency_ms = (time.monotonic() - t0) * 1000
        content = message.content[0].text if message.content else ""
        return AIResponse(
            content=content,
            usage=self._make_usage(message.usage, cfg.model_name, latency_ms),
            raw_response=message,
        )

    async def complete_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[BaseModel],
        config: Optional[AIRequestConfig] = None,
    ) -> AIResponse:
        """
        Use Anthropic tool_use with strict schema validation to obtain structured JSON.

        The Pydantic model's JSON schema is passed as the tool input_schema.
        The tool is available with automatic selection and strict input validation.
        """
        import pydantic

        client = self._ensure_initialized()
        cfg = self._resolve_config(config)

        # Build tool definition from Pydantic schema
        json_schema = self._apply_strict_schema_constraints(
            response_schema.model_json_schema()
        )
        tool_name = "structured_response"
        tools = [
            {
                "name": tool_name,
                "description": f"Return a valid {response_schema.__name__} JSON object.",
                "input_schema": json_schema,
                "strict": True,
            }
        ]

        t0 = time.monotonic()
        try:
            message = await client.messages.create(
                model=cfg.model_name,
                max_tokens=cfg.max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                tools=tools,
                tool_choice={"type": "auto"},
                timeout=cfg.timeout_seconds,
                **self._sampling_parameters(cfg),
            )
        except Exception as exc:
            if self._is_compiled_grammar_too_large_error(exc):
                logger.warning(
                    "Anthropic tool grammar exceeded the model limit; retrying "
                    "structured request with JSON prompt validation (model=%s, schema=%s).",
                    cfg.model_name,
                    response_schema.__name__,
                )
                return await self._complete_structured_json_fallback(
                    client,
                    system_prompt,
                    user_prompt,
                    response_schema,
                    cfg,
                )
            raise self._classify_error(exc) from exc

        latency_ms = (time.monotonic() - t0) * 1000

        # Extract tool input from response
        tool_use_block = next(
            (b for b in message.content if getattr(b, "type", None) == "tool_use"),
            None,
        )
        if tool_use_block is None:
            raise AISchemaValidationError(
                message="Anthropic response did not contain a tool_use block",
                raw_content=str(message.content),
                schema_name=response_schema.__name__,
            )

        raw_input: Dict[str, Any] = tool_use_block.input  # already a dict from SDK

        # Validate against Pydantic schema
        try:
            response_schema.model_validate(raw_input)
        except pydantic.ValidationError as exc:
            raise AISchemaValidationError(
                message=f"Anthropic response failed schema validation: {exc}",
                raw_content=json.dumps(raw_input),
                schema_name=response_schema.__name__,
            ) from exc

        content = json.dumps(raw_input)
        return AIResponse(
            content=content,
            usage=self._make_usage(message.usage, cfg.model_name, latency_ms),
            raw_response=message,
        )

    async def health_check(self) -> bool:
        """Verify API key is set and client is initialized."""
        return self._client is not None and bool(self._api_key)
