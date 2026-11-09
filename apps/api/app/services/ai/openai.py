from __future__ import annotations

import json
import time
from typing import Any, Optional, Type

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


class OpenAIProvider(BaseAIProvider):
    """OpenAI chat-completions adapter for structured JSON generation."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.openai_api_key
        self._model = model or settings.openai_model
        self._client: Optional[Any] = None

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def default_model(self) -> str:
        return self._model

    async def initialize(self) -> None:
        if not self._api_key:
            raise AIProviderError(
                "OPENAI_API_KEY is not set. Set it in environment variables or use the mock provider for development.",
                provider=self.provider_name,
                retryable=False,
            )
        try:
            import openai

            self._client = openai.AsyncOpenAI(api_key=self._api_key)
        except ImportError as exc:
            raise AIProviderError(
                "openai package is not installed. Run: pip install openai>=1.60.0",
                provider=self.provider_name,
                retryable=False,
            ) from exc

    async def close(self) -> None:
        if self._client is not None:
            close_method = getattr(self._client, "close", None)
            if callable(close_method):
                result = close_method()
                if hasattr(result, "__await__"):
                    await result
            self._client = None

    def _ensure_initialized(self) -> Any:
        if self._client is None:
            raise AIProviderError(
                "OpenAIProvider is not initialized. Call initialize() first.",
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

    def _make_usage(self, raw_usage: Any, model_name: str, latency_ms: float) -> AIUsageStats:
        prompt_tokens = getattr(raw_usage, "prompt_tokens", 0) or 0
        completion_tokens = getattr(raw_usage, "completion_tokens", 0) or 0
        return AIUsageStats(
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            model_name=model_name,
            provider_name=self.provider_name,
            latency_ms=latency_ms,
            extra={
                "completion_tokens_details": getattr(raw_usage, "completion_tokens_details", None),
                "prompt_tokens_details": getattr(raw_usage, "prompt_tokens_details", None),
            },
        )

    def _classify_error(self, exc: Exception) -> AIProviderError:
        status_code = getattr(exc, "status_code", None)
        if hasattr(exc, "response"):
            status_code = getattr(exc.response, "status_code", status_code)
        retryable = status_code in (408, 409, 429, 500, 502, 503, 504)
        message = str(exc)
        if status_code is None and hasattr(exc, "body"):
            message = json.dumps(getattr(exc, "body", {}), default=str)
        return AIProviderError(
            message=message,
            provider=self.provider_name,
            status_code=status_code,
            retryable=retryable,
        )

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        config: Optional[AIRequestConfig] = None,
    ) -> AIResponse:
        client = self._ensure_initialized()
        cfg = self._resolve_config(config)
        t0 = time.monotonic()
        try:
            response = await client.chat.completions.create(
                model=cfg.model_name,
                temperature=cfg.temperature,
                max_tokens=cfg.max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                timeout=cfg.timeout_seconds,
            )
        except Exception as exc:  # pragma: no cover - exercised by manager tests via mocked client
            raise self._classify_error(exc) from exc

        latency_ms = (time.monotonic() - t0) * 1000
        content = response.choices[0].message.content if response.choices else ""
        return AIResponse(
            content=content or "",
            usage=self._make_usage(getattr(response, "usage", None), cfg.model_name, latency_ms),
            raw_response=response,
        )

    async def complete_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[BaseModel],
        config: Optional[AIRequestConfig] = None,
    ) -> AIResponse:
        client = self._ensure_initialized()
        cfg = self._resolve_config(config)
        schema = response_schema.model_json_schema()
        request_body = {
            "name": response_schema.__name__,
            "schema": schema,
            "strict": True,
        }

        t0 = time.monotonic()
        try:
            response = await client.chat.completions.create(
                model=cfg.model_name,
                temperature=cfg.temperature,
                max_tokens=cfg.max_tokens,
                response_format={"type": "json_schema", "json_schema": request_body},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                timeout=cfg.timeout_seconds,
            )
        except Exception as exc:
            raise self._classify_error(exc) from exc

        latency_ms = (time.monotonic() - t0) * 1000
        content = response.choices[0].message.content if response.choices else ""
        if not content:
            raise AISchemaValidationError(
                message="OpenAI returned an empty structured response",
                raw_content="",
                schema_name=response_schema.__name__,
            )

        try:
            response_schema.model_validate_json(content)
        except Exception as exc:  # pragma: no cover - validation handled in manager tests
            raise AISchemaValidationError(
                message=f"OpenAI response failed schema validation: {exc}",
                raw_content=content,
                schema_name=response_schema.__name__,
            ) from exc

        return AIResponse(
            content=content,
            usage=self._make_usage(getattr(response, "usage", None), cfg.model_name, latency_ms),
            raw_response=response,
        )

    async def health_check(self) -> bool:
        return self._client is not None and bool(self._api_key)
