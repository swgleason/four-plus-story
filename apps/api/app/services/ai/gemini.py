from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Optional

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


class GeminiProvider(BaseAIProvider):
    """Google Gemini adapter using the official GenAI client."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.gemini_api_key
        self._model = model or settings.gemini_model
        self._client: Optional[Any] = None

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def default_model(self) -> str:
        return self._model

    async def initialize(self) -> None:
        if not self._api_key:
            raise AIProviderError(
                "GEMINI_API_KEY is not set. Set it in environment variables or use the mock provider for development.",
                provider=self.provider_name,
                retryable=False,
            )
        try:
            try:
                from google import genai as google_genai_client

                self._client = google_genai_client.Client(api_key=self._api_key)
            except ImportError:  # pragma: no cover - fallback for older SDK
                import google.generativeai as google_generative_ai

                google_generative_ai.configure(api_key=self._api_key)
                self._client = google_generative_ai
        except ImportError as exc:
            raise AIProviderError(
                "google-genai package is not installed. Run: pip install google-genai>=1.0.0",
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
                "GeminiProvider is not initialized. Call initialize() first.",
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
        prompt_tokens = 0
        completion_tokens = 0
        extra: dict[str, Any] = {}
        if raw_usage is not None:
            prompt_tokens = getattr(raw_usage, "prompt_token_count", 0) or getattr(raw_usage, "prompt_tokens", 0) or 0
            completion_tokens = getattr(raw_usage, "candidate_token_count", 0) or getattr(raw_usage, "completion_tokens", 0) or 0
            extra = {
                "raw_usage": raw_usage,
            }
        return AIUsageStats(
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            model_name=model_name,
            provider_name=self.provider_name,
            latency_ms=latency_ms,
            extra=extra,
        )

    def _classify_error(self, exc: Exception) -> AIProviderError:
        response = getattr(exc, "response", None)
        status_code = (
            getattr(exc, "status_code", None)
            or getattr(exc, "code", None)
            or getattr(exc, "status", None)
            or getattr(response, "status_code", None)
        )
        try:
            numeric_status = int(str(status_code))
        except (TypeError, ValueError):
            numeric_status = None
        error_text = f"{type(exc).__name__} {exc}".lower()
        transient_text = any(
            marker in error_text
            for marker in (
                "timeout",
                "timed out",
                "connection",
                "connecterror",
                "network",
                "service unavailable",
                "unavailable",
            )
        )
        rate_limited = numeric_status == 429 or "resource_exhausted" in error_text
        retryable = not rate_limited and (
            numeric_status in (408, 500, 502, 503, 504)
            or isinstance(exc, (TimeoutError, ConnectionError))
            or transient_text
        )
        return AIProviderError(
            message=str(exc),
            provider=self.provider_name,
            status_code=numeric_status,
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
            if hasattr(client, "aio") and hasattr(client.aio, "models"):
                from google.genai import types

                result = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=cfg.model_name,
                        contents=user_prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_prompt,
                            temperature=cfg.temperature,
                            max_output_tokens=cfg.max_tokens,
                            response_mime_type="application/json",
                        ),
                    ),
                    timeout=cfg.timeout_seconds,
                )
                content = getattr(result, "text", "") or ""
            else:
                generation_config = client.types.GenerationConfig(
                    temperature=cfg.temperature,
                    max_output_tokens=cfg.max_tokens,
                    response_mime_type="application/json",
                )
                model = client.GenerativeModel(
                    model_name=cfg.model_name,
                    system_instruction=system_prompt,
                    generation_config=generation_config,
                )
                result = await asyncio.wait_for(
                    model.generate_content_async(user_prompt),
                    timeout=cfg.timeout_seconds,
                )
                content = getattr(result, "text", "") or ""
        except Exception as exc:
            raise self._classify_error(exc) from exc

        latency_ms = (time.monotonic() - t0) * 1000
        return AIResponse(
            content=content,
            usage=self._make_usage(getattr(result, "usage_metadata", None), cfg.model_name, latency_ms),
            raw_response=result,
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
        t0 = time.monotonic()
        try:
            if hasattr(client, "aio") and hasattr(client.aio, "models"):
                from google.genai import types

                result = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=cfg.model_name,
                        contents=user_prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_prompt,
                            temperature=cfg.temperature,
                            max_output_tokens=cfg.max_tokens,
                            response_mime_type="application/json",
                            response_schema=schema,
                        ),
                    ),
                    timeout=cfg.timeout_seconds,
                )
                content = getattr(result, "text", "") or ""
            else:
                generation_config = client.types.GenerationConfig(
                    temperature=cfg.temperature,
                    max_output_tokens=cfg.max_tokens,
                    response_mime_type="application/json",
                )
                model = client.GenerativeModel(
                    model_name=cfg.model_name,
                    system_instruction=system_prompt,
                    generation_config=generation_config,
                )
                result = await asyncio.wait_for(
                    model.generate_content_async(
                        user_prompt
                        + "\n\nReturn valid JSON matching this schema: "
                        + json.dumps(schema)
                    ),
                    timeout=cfg.timeout_seconds,
                )
                content = getattr(result, "text", "") or ""
        except Exception as exc:
            raise self._classify_error(exc) from exc

        if not content:
            raise AISchemaValidationError(
                message="Gemini returned an empty structured response",
                raw_content="",
                schema_name=response_schema.__name__,
            )

        try:
            response_schema.model_validate_json(content)
        except Exception as exc:
            raise AISchemaValidationError(
                message=f"Gemini response failed validation: {exc}",
                raw_content=content,
                schema_name=response_schema.__name__,
            ) from exc

        latency_ms = (time.monotonic() - t0) * 1000
        return AIResponse(
            content=content,
            usage=self._make_usage(getattr(result, "usage_metadata", None), cfg.model_name, latency_ms),
            raw_response=result,
        )

    async def health_check(self) -> bool:
        return self._client is not None and bool(self._api_key)
