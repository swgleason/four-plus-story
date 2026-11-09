"""Provider-independent embedding clients for story and search-query vectors."""

from __future__ import annotations

import abc
import hashlib
import math
import re
from dataclasses import dataclass
from typing import Any

from app.core.config import get_settings
from app.services.ai.base import AIProviderError


@dataclass(frozen=True)
class EmbeddingResponse:
    vector: list[float]
    model_name: str
    model_version: str


class EmbeddingProvider(abc.ABC):
    """Interface implemented by configured embedding vendors."""

    @abc.abstractmethod
    async def initialize(self) -> None: ...

    @abc.abstractmethod
    async def close(self) -> None: ...

    @abc.abstractmethod
    async def embed(
        self, text: str, model_name: str, dimension: int
    ) -> EmbeddingResponse: ...


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI embeddings API adapter."""

    def __init__(self) -> None:
        self.api_key = get_settings().openai_api_key
        self._client: Any = None

    async def initialize(self) -> None:
        if not self.api_key:
            raise AIProviderError(
                "OPENAI_API_KEY is required for the configured embedding provider.",
                provider="openai",
                retryable=False,
            )
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise AIProviderError(
                "The openai package is required for OpenAI embeddings.",
                provider="openai",
                retryable=False,
            ) from exc
        self._client = AsyncOpenAI(api_key=self.api_key)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def embed(self, text: str, model_name: str, dimension: int) -> EmbeddingResponse:
        if self._client is None:
            raise AIProviderError("OpenAI embedding client is not initialized.", provider="openai")
        try:
            result = await self._client.embeddings.create(
                model=model_name,
                input=text,
                dimensions=dimension,
            )
        except Exception as exc:
            raise AIProviderError(
                "OpenAI embedding request failed.",
                provider="openai",
                status_code=getattr(exc, "status_code", None),
                retryable=getattr(exc, "status_code", None) in {408, 429, 500, 502, 503, 504},
            ) from exc
        if not result.data:
            raise AIProviderError("OpenAI returned no embedding vector.", provider="openai")
        return EmbeddingResponse(
            vector=list(result.data[0].embedding),
            model_name=model_name,
            model_version=getattr(result, "model", None) or model_name,
        )


class GeminiEmbeddingProvider(EmbeddingProvider):
    """Google GenAI embeddings API adapter."""

    def __init__(self) -> None:
        self.api_key = get_settings().gemini_api_key
        self._client: Any = None

    async def initialize(self) -> None:
        if not self.api_key:
            raise AIProviderError(
                "GEMINI_API_KEY is required for the configured embedding provider.",
                provider="gemini",
                retryable=False,
            )
        try:
            from google import genai
        except ImportError as exc:
            raise AIProviderError(
                "The google-genai package is required for Gemini embeddings.",
                provider="gemini",
                retryable=False,
            ) from exc
        self._client = genai.Client(api_key=self.api_key)

    async def close(self) -> None:
        if self._client is not None:
            async_client = getattr(self._client, "aio", None)
            close = getattr(async_client, "aclose", None)
            if callable(close):
                await close()
            else:
                close = getattr(self._client, "close", None)
                if callable(close):
                    close()
            self._client = None

    async def embed(self, text: str, model_name: str, dimension: int) -> EmbeddingResponse:
        if self._client is None:
            raise AIProviderError("Gemini embedding client is not initialized.", provider="gemini")
        try:
            from google.genai import types

            result = await self._client.aio.models.embed_content(
                model=model_name,
                contents=text,
                config=types.EmbedContentConfig(output_dimensionality=dimension),
            )
        except Exception as exc:
            raise AIProviderError(
                "Gemini embedding request failed.",
                provider="gemini",
                status_code=getattr(exc, "status_code", None),
                retryable=getattr(exc, "status_code", None) in {408, 429, 500, 502, 503, 504},
            ) from exc
        embeddings = getattr(result, "embeddings", None) or []
        values = getattr(embeddings[0], "values", None) if embeddings else None
        if values is None:
            raise AIProviderError("Gemini returned no embedding vector.", provider="gemini")
        return EmbeddingResponse(
            vector=list(values),
            model_name=model_name,
            model_version=model_name,
        )


class MockEmbeddingProvider(EmbeddingProvider):
    """Deterministic feature-hashed embedding provider for tests and local development."""

    async def initialize(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def embed(self, text: str, model_name: str, dimension: int) -> EmbeddingResponse:
        vector = [0.0] * dimension
        tokens = re.findall(r"[a-z0-9']+", text.casefold())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % dimension
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        return EmbeddingResponse(vector, model_name, model_name)


def create_embedding_provider(provider_name: str | None = None) -> EmbeddingProvider:
    """Create the configured embedding adapter."""
    settings = get_settings()
    name = provider_name or settings.embedding_provider
    providers: dict[str, type[EmbeddingProvider]] = {
        "openai": OpenAIEmbeddingProvider,
        "gemini": GeminiEmbeddingProvider,
        "mock": MockEmbeddingProvider,
    }
    provider_class = providers.get(name)
    if provider_class is None:
        raise ValueError(f"Unsupported embedding provider '{name}'.")
    return provider_class()
