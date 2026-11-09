"""Public and registered-user rights-filtered story search endpoint."""

# FastAPI uses Depends() in parameter defaults for request handling.
# ruff: noqa: B008

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from app.core.config import get_settings
from app.core.supabase import bearer_scheme, get_supabase_client
from app.schemas.enums import UserRole
from app.schemas.search import HybridSearchRequest, HybridSearchResponse
from app.services.search.embeddings import create_embedding_provider
from app.services.search.engine import HybridSearchEngine

router = APIRouter(prefix="/stories", tags=["story search"])


async def get_search_user_role(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    supabase: Any = Depends(get_supabase_client),
) -> UserRole:
    """Resolve the caller's trusted profile role; absent credentials mean public access."""
    if credentials is None:
        return UserRole.PUBLIC_GUEST
    try:
        response = await supabase.auth.get_user(credentials.credentials)
        user = getattr(response, "user", None)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The access token is invalid or expired.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    user_id = getattr(user, "id", None)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The access token does not identify a user.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    profile_result = await (
        supabase.table("user_profiles")
        .select("role")
        .eq("id", str(user_id))
        .maybe_single()
        .execute()
    )
    profile = getattr(profile_result, "data", None)
    role_value = profile.get("role") if isinstance(profile, dict) else None
    try:
        return UserRole(role_value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A valid reader profile is required for story search.",
        ) from exc


def get_search_engine(supabase: Any = Depends(get_supabase_client)) -> HybridSearchEngine:
    settings = get_settings()
    return HybridSearchEngine(
        supabase,
        create_embedding_provider(settings.embedding_provider),
    )


@router.post("/search", response_model=HybridSearchResponse)
async def search_stories(
    request: HybridSearchRequest,
    engine: HybridSearchEngine = Depends(get_search_engine),
    user_role: UserRole = Depends(get_search_user_role),
) -> HybridSearchResponse:
    try:
        return await engine.search(request, user_role)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
