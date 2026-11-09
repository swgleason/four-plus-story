"""FastAPI application entry point."""

from fastapi import FastAPI

from app.core.config import get_settings
from app.routers.admin import router as admin_router
from app.routers.discovery import router as discovery_router
from app.routers.documents import router as documents_router
from app.routers.search import router as search_router
from app.routers.stories import router as stories_router

app = FastAPI(title=get_settings().app_name)
app.include_router(documents_router, prefix="/api/v1")
app.include_router(discovery_router, prefix="/api/v1")
app.include_router(stories_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
