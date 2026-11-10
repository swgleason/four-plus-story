"""FastAPI application entry point."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from supabase import acreate_client

from app.core.config import get_settings
from app.core.supabase import ensure_storage_bucket, supabase_is_configured
from app.routers.admin import router as admin_router
from app.routers.discovery import router as discovery_router
from app.routers.documents import router as documents_router
from app.routers.search import router as search_router
from app.routers.stories import router as stories_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if supabase_is_configured():
        supabase = await acreate_client(
            settings.supabase_url, settings.supabase_service_role_key
        )
        app.state.supabase = supabase
        try:
            await ensure_storage_bucket(supabase, settings.raw_documents_bucket)
        except Exception:
            logger.exception(
                "Could not ensure private Supabase Storage bucket %r exists.",
                settings.raw_documents_bucket,
            )
            raise
    yield


app = FastAPI(title=get_settings().app_name, lifespan=lifespan)
app.include_router(documents_router, prefix="/api/v1")
app.include_router(discovery_router, prefix="/api/v1")
app.include_router(stories_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
