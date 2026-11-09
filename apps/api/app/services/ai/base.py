"""
Abstract base interface for provider-independent AI service layer.

All AI provider adapters (Anthropic, OpenAI, Gemini, Mock) MUST implement
this interface. Business logic interacts ONLY with BaseAIProvider; it never
imports or instantiates vendor-specific clients directly.

Design principles:
- Provider-agnostic: swap Anthropic for Gemini with zero changes to callers.
- Strictly typed: all inputs and outputs go through Pydantic v2 schemas.
- Anti-hallucination: methods are scoped to prevent full verbatim text reproduction.
- Two-stage pipeline: boundary extraction first, full evaluation second.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Type

from pydantic import BaseModel


@dataclass
class AIRequestConfig:
    """
    Runtime configuration passed to each AI call.
    Callers may override per-request; defaults come from AIServiceManager.
    """
    model_name: str = ""                        # Provider-specific model identifier
    temperature: float = 0.0                    # 0.0 for deterministic structured output
    max_tokens: int = 4096                      # Sufficient for JSON evaluation payloads
    timeout_seconds: float = 60.0              # Network call timeout
    extra: Dict[str, Any] = field(default_factory=dict)  # Provider-specific overrides


@dataclass
class AIUsageStats:
    """Token usage statistics returned alongside AI responses."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    model_name: str = ""
    provider_name: str = ""
    latency_ms: float = 0.0
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AIResponse:
    """
    Generic wrapper returned by all AI provider calls.
    Callers parse `content` into the appropriate Pydantic schema.
    """
    content: str                              # Raw JSON string from provider
    usage: AIUsageStats = field(default_factory=AIUsageStats)
    raw_response: Optional[Any] = None        # Provider-specific raw response object (for debugging)


class BaseAIProvider(abc.ABC):
    """
    Abstract base class for all AI provider adapters.

    Subclasses implement `complete()` for raw text generation and
    `complete_structured()` for validated structured JSON output.

    Provider-specific clients (httpx sessions, SDK instances) must be
    initialized in `initialize()` and released in `close()`.
    """

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider identifier (e.g. 'anthropic', 'openai', 'gemini', 'mock')."""
        ...

    @property
    @abc.abstractmethod
    def default_model(self) -> str:
        """Default model identifier for this provider."""
        ...

    @abc.abstractmethod
    async def initialize(self) -> None:
        """
        Establish provider connections or warm up SDK clients.
        Called once by AIServiceManager during startup.
        """
        ...

    @abc.abstractmethod
    async def close(self) -> None:
        """
        Release provider connections and free resources.
        Called by AIServiceManager during shutdown.
        """
        ...

    @abc.abstractmethod
    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        config: Optional[AIRequestConfig] = None,
    ) -> AIResponse:
        """
        Send a prompt to the provider and return a raw text/JSON response.

        Args:
            system_prompt: The system/instruction context.
            user_prompt:   The user/document chunk content.
            config:        Optional per-request overrides.

        Returns:
            AIResponse with content as raw string.

        Raises:
            AIProviderError: on API errors, timeout, or rate limiting.
        """
        ...

    @abc.abstractmethod
    async def complete_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[BaseModel],
        config: Optional[AIRequestConfig] = None,
    ) -> AIResponse:
        """
        Send a prompt requesting validated structured JSON output.

        The provider MUST enforce structured/JSON output mode where available
        (Anthropic tool_choice, OpenAI response_format, Gemini response_schema).

        Args:
            system_prompt:   The system/instruction context.
            user_prompt:     The user/document chunk content.
            response_schema: Pydantic v2 model class whose JSON schema constrains output.
            config:          Optional per-request overrides.

        Returns:
            AIResponse with content as validated JSON string.

        Raises:
            AIProviderError: on API errors.
            AISchemaValidationError: if response does not conform to schema.
        """
        ...

    async def health_check(self) -> bool:
        """
        Perform a lightweight health check against the provider.
        Returns True if the provider is reachable and responding.
        Default implementation returns True; override for real HTTP ping.
        """
        return True


class AIProviderError(Exception):
    """
    Raised when an AI provider returns an error, times out, or hits rate limits.
    Wraps provider-specific error details for uniform upstream handling.
    """
    def __init__(
        self,
        message: str,
        provider: str = "",
        status_code: Optional[int] = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code
        self.retryable = retryable

    def __repr__(self) -> str:
        return (
            f"AIProviderError(provider={self.provider!r}, "
            f"status_code={self.status_code}, "
            f"retryable={self.retryable}, "
            f"message={str(self)!r})"
        )


class AISchemaValidationError(Exception):
    """
    Raised when the AI provider's structured output does not parse into
    the requested Pydantic v2 response schema.
    """
    def __init__(
        self,
        message: str,
        raw_content: str = "",
        schema_name: str = "",
    ) -> None:
        super().__init__(message)
        self.raw_content = raw_content
        self.schema_name = schema_name

