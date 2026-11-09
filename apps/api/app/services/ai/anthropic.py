"""
Anthropic Claude adapter for the provider-independent AI service layer.

Implements BaseAIProvider using the official Anthropic Python SDK.
Structured output is enforced via Anthropic's tool_use API (forced tool_choice),
which is the most reliable way to get validated JSON from Claude models.

Required environment variables:
    ANTHROPIC_API_KEY   — Anthropic API key
    ANTHROPIC_MODEL     — Model name (default: claude-3-5-sonnet-20241022)

SDK documentation: https://docs.anthropic.com/en/api/messages
"""

from __future__ import annotations

import json
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


class AnthropicProvider(BaseAIProvider):
    """
    Anthropic Claude adapter.

    Uses tool_use with forced single-tool selection to obtain structured JSON.
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
                temperature=cfg.temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                timeout=cfg.timeout_seconds,
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
        Use Anthropic tool_use with forced single-tool selection to obtain structured JSON.

        The Pydantic model's JSON schema is passed as the tool input_schema.
        Claude is forced to call the tool, ensuring structured JSON output.
        """
        import anthropic
        import pydantic

        client = self._ensure_initialized()
        cfg = self._resolve_config(config)

        # Build tool definition from Pydantic schema
        json_schema = response_schema.model_json_schema()
        tool_name = "structured_response"
        tools = [
            {
                "name": tool_name,
                "description": f"Return a valid {response_schema.__name__} JSON object.",
                "input_schema": json_schema,
            }
        ]

        t0 = time.monotonic()
        try:
            message = await client.messages.create(
                model=cfg.model_name,
                max_tokens=cfg.max_tokens,
                temperature=cfg.temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                tools=tools,
                tool_choice={"type": "tool", "name": tool_name},
                timeout=cfg.timeout_seconds,
            )
        except Exception as exc:
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

