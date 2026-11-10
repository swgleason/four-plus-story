"""Supabase client and curator authorization dependencies."""

# FastAPI uses Depends() in parameter defaults for dependency injection.
# ruff: noqa: B008

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import acreate_client

from app.core.config import get_settings

bearer_scheme = HTTPBearer(auto_error=False)


def _is_unconfigured(value: str) -> bool:
    normalized = value.strip().lower()
    return (
        not normalized
        or normalized.startswith(("your_", "your-"))
        or "placeholder" in normalized
    )


async def get_supabase_client(request: Request) -> Any:
    client = getattr(request.app.state, "supabase", None)
    if client is not None:
        return client

    settings = get_settings()
    if _is_unconfigured(settings.supabase_url) or _is_unconfigured(
        settings.supabase_service_role_key
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Supabase service configuration is unavailable. Set SUPABASE_URL and "
                "SUPABASE_SERVICE_ROLE_KEY to valid values for this project."
            ),
        )

    client = await acreate_client(settings.supabase_url, settings.supabase_service_role_key)
    request.app.state.supabase = client
    return client


async def require_curator(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    supabase: Any = Depends(get_supabase_client),
) -> str:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid curator access token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        user_response = await supabase.auth.get_user(credentials.credentials)
        user = getattr(user_response, "user", None)
        user_id = getattr(user, "id", None)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The access token is invalid or expired.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The access token does not identify a user.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    profile_result = await (
        supabase.table("user_profiles").select("role").eq("id", user_id).maybe_single().execute()
    )
    profile = getattr(profile_result, "data", None)
    role = profile.get("role") if isinstance(profile, dict) else None
    if role not in {"super_admin", "curator"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Curator or administrator access is required.",
        )
    return str(user_id)
