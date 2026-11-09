"""
Application settings for the Four Plus Story Library API.

Loaded from environment variables via pydantic-settings.
Provides typed, validated configuration to all app components.

Usage:
    from app.core.config import get_settings
    settings = get_settings()
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central application settings.

    All fields load from environment variables (case-insensitive).
    See .env.example for the full list of supported variables.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # Application
    # -------------------------------------------------------------------------
    app_name: str = "Four Plus Story Library API"
    app_env: Literal["development", "staging", "production"] = "development"
    debug: bool = False

    # -------------------------------------------------------------------------
    # Supabase
    # -------------------------------------------------------------------------
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    raw_documents_bucket: str = "raw-documents"
    max_document_upload_bytes: int = Field(default=25_000_000, ge=1_000, le=500_000_000)
    document_chunk_max_tokens: int = Field(default=800, ge=1, le=8192)
    document_chunk_overlap_tokens: int = Field(default=100, ge=0, le=4096)

    # -------------------------------------------------------------------------
    # AI Provider Selection
    # -------------------------------------------------------------------------
    # Supported values: "anthropic", "openai", "gemini", "mock"
    ai_primary_provider: Literal["anthropic", "openai", "gemini", "mock"] = "mock"

    # Comma-separated ordered fallback providers.
    # Example: "openai,mock"  — tries openai, then mock if openai fails.
    ai_fallback_providers: str = "mock"

    # -------------------------------------------------------------------------
    # AI Provider API Keys
    # -------------------------------------------------------------------------
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""

    # -------------------------------------------------------------------------
    # AI Provider Model Names (configurable without code changes)
    # -------------------------------------------------------------------------
    anthropic_model: str = "claude-3-5-sonnet-20241022"
    openai_model: str = "gpt-4o-2024-11-20"
    gemini_model: str = "gemini-1.5-pro-002"

    # -------------------------------------------------------------------------
    # AI Request Defaults
    # -------------------------------------------------------------------------
    ai_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    ai_max_tokens: int = Field(default=4096, ge=256, le=16384)
    ai_timeout_seconds: float = Field(default=60.0, ge=5.0, le=300.0)

    # -------------------------------------------------------------------------
    # Retry & Backoff
    # -------------------------------------------------------------------------
    ai_max_retries: int = Field(default=3, ge=0, le=10)
    ai_retry_base_delay_seconds: float = Field(default=1.0, ge=0.1, le=30.0)
    ai_retry_max_delay_seconds: float = Field(default=30.0, ge=1.0, le=120.0)
    ai_retry_jitter: bool = True          # Add random jitter to backoff delays

    # -------------------------------------------------------------------------
    # Storage / Embedding
    # -------------------------------------------------------------------------
    embedding_provider: Literal["openai", "gemini", "mock"] = "mock"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = Field(default=1536, ge=128, le=4096)
    embedding_model_version: str = ""

    @field_validator("ai_fallback_providers", mode="before")
    @classmethod
    def _validate_fallback_providers(cls, v: str) -> str:
        """Normalize whitespace in comma-separated list."""
        return ",".join(p.strip() for p in str(v).split(",") if p.strip())

    def get_fallback_provider_list(self) -> List[str]:
        """Return ordered list of fallback provider names."""
        if not self.ai_fallback_providers:
            return []
        return [p.strip() for p in self.ai_fallback_providers.split(",") if p.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return cached Settings instance.
    Thread-safe; call anywhere in the application.
    """
    return Settings()
