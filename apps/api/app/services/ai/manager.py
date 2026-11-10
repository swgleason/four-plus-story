from __future__ import annotations

import asyncio
import random
from typing import Any, Callable, Dict, Iterable, List, Optional

from pydantic import BaseModel

from app.core.config import get_settings
from app.services.ai.anthropic import AnthropicProvider
from app.services.ai.base import (
    AIProviderError,
    AIRequestConfig,
    AIResponse,
    AISchemaValidationError,
    BaseAIProvider,
)
from app.services.ai.gemini import GeminiProvider
from app.services.ai.mock import MockAIProvider
from app.services.ai.openai import OpenAIProvider


class AIServiceManager:
    """Central coordinator for provider selection, retries, fallback, and validation."""

    def __init__(
        self,
        primary_provider: Optional[str] = None,
        fallback_providers: Optional[Iterable[str]] = None,
        providers: Optional[Dict[str, BaseAIProvider]] = None,
    ) -> None:
        settings = get_settings()
        self.primary_provider = primary_provider or settings.ai_primary_provider
        self.fallback_providers = list(fallback_providers or settings.get_fallback_provider_list())
        self.settings = settings
        self.max_retries = settings.ai_max_retries
        self.retry_base_delay = settings.ai_retry_base_delay_seconds
        self.retry_max_delay = settings.ai_retry_max_delay_seconds
        self.retry_jitter = settings.ai_retry_jitter
        self._providers: Dict[str, BaseAIProvider] = {}

        if providers:
            self._providers.update(providers)

        for provider_name in self.provider_order:
            if provider_name in self._providers:
                continue
            if provider_name in {"anthropic", "openai", "gemini", "mock"}:
                self._providers.setdefault(provider_name, self._instantiate_provider(provider_name))

    @property
    def provider_order(self) -> List[str]:
        provider_names: List[str] = []
        seen: set[str] = set()
        for provider_name in [self.primary_provider, *self.fallback_providers]:
            if provider_name and provider_name not in seen:
                seen.add(provider_name)
                provider_names.append(provider_name)
        return provider_names

    def _instantiate_provider(self, provider_name: str) -> BaseAIProvider:
        factory_map: Dict[str, type[BaseAIProvider]] = {
            "anthropic": AnthropicProvider,
            "openai": OpenAIProvider,
            "gemini": GeminiProvider,
            "mock": MockAIProvider,
        }
        factory = factory_map.get(provider_name)
        if factory is None:
            raise ValueError(f"Unsupported AI provider '{provider_name}'")
        return factory()

    def _provider_for_name(self, provider_name: str) -> BaseAIProvider:
        provider = self._providers.get(provider_name)
        if provider is None:
            provider = self._instantiate_provider(provider_name)
            self._providers[provider_name] = provider
        return provider

    async def initialize(self) -> None:
        for provider_name in self.provider_order:
            provider = self._provider_for_name(provider_name)
            try:
                await provider.initialize()
            except AIProviderError:
                continue

    async def close(self) -> None:
        for provider in self._providers.values():
            try:
                await provider.close()
            except Exception:
                continue

    def _sleep_for_backoff(self, attempt_index: int) -> Any:
        delay = min(
            self.retry_base_delay * (2**attempt_index),
            self.retry_max_delay,
        )
        if self.retry_jitter:
            delay = max(0.0, delay * (0.5 + random.random()))
        return asyncio.sleep(delay)

    def _is_retryable_error(self, exc: Exception) -> bool:
        if isinstance(exc, AIProviderError):
            return exc.retryable
        return isinstance(exc, AISchemaValidationError)

    async def complete_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[BaseModel],
        config: Optional[AIRequestConfig] = None,
        retry_callback: Callable[[int, AIProviderError], None] | None = None,
    ) -> AIResponse:
        last_error: Optional[Exception] = None

        for provider_name in self.provider_order:
            provider = self._provider_for_name(provider_name)
            for attempt in range(self.max_retries + 1):
                try:
                    response = await provider.complete_structured(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        response_schema=response_schema,
                        config=config,
                    )
                    response.usage.provider_name = provider.provider_name
                    response.usage.model_name = response.usage.model_name or provider.default_model
                    return response
                except (AIProviderError, AISchemaValidationError) as exc:
                    last_error = exc
                    if isinstance(exc, AIProviderError) and not exc.retryable:
                        raise exc
                    if attempt < self.max_retries and self._is_retryable_error(exc):
                        if isinstance(exc, AIProviderError) and retry_callback is not None:
                            retry_callback(attempt + 1, exc)
                        await self._sleep_for_backoff(attempt)
                        continue
                    break

            if last_error is not None and isinstance(last_error, AIProviderError) and not last_error.retryable:
                raise last_error

        if last_error is not None:
            raise last_error

        raise AIProviderError(
            "AIServiceManager could not produce a validated response from any configured provider.",
            provider=self.primary_provider,
            retryable=False,
        )

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        config: Optional[AIRequestConfig] = None,
    ) -> AIResponse:
        last_error: Optional[Exception] = None
        for provider_name in self.provider_order:
            provider = self._provider_for_name(provider_name)
            for attempt in range(self.max_retries + 1):
                try:
                    response = await provider.complete(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        config=config,
                    )
                    response.usage.provider_name = provider.provider_name
                    response.usage.model_name = response.usage.model_name or provider.default_model
                    return response
                except (AIProviderError, AISchemaValidationError) as exc:
                    last_error = exc
                    if isinstance(exc, AIProviderError) and not exc.retryable:
                        raise exc
                    if attempt < self.max_retries and self._is_retryable_error(exc):
                        await self._sleep_for_backoff(attempt)
                        continue
                    break
            if last_error is not None and isinstance(last_error, AIProviderError) and not last_error.retryable:
                raise last_error

        if last_error is not None:
            raise last_error

        raise AIProviderError(
            "AIServiceManager completed no successful raw responses from any configured provider.",
            provider=self.primary_provider,
            retryable=False,
        )


async def create_default_manager() -> AIServiceManager:
    settings = get_settings()
    return AIServiceManager(
        primary_provider=settings.ai_primary_provider,
        fallback_providers=settings.get_fallback_provider_list(),
    )
