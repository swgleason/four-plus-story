"""Authenticated endpoints for document upload and ingestion results."""

# FastAPI uses Depends(), File(), and Form() in parameter defaults for request handling.
# ruff: noqa: B008

from __future__ import annotations

from typing import Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.supabase import get_supabase_client, require_curator
from app.schemas.document import (
    DocumentChunkInDB,
    DocumentPageInDB,
    ProcessingJobInDB,
)
from app.schemas.enums import DocumentRightsStatus, DocumentType
from app.services.ingest.manager import (
    DuplicateDocumentError,
    IngestionManager,
)
from app.services.ingest.parser import DocumentParseError

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentUploadResponse(BaseModel):
    document: dict[str, Any]
    job: dict[str, Any]


class DocumentJobResponse(BaseModel):
    job: ProcessingJobInDB


def get_ingestion_manager(
    supabase: Any = Depends(get_supabase_client),
) -> IngestionManager:
    return IngestionManager(supabase)


@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(..., min_length=1, max_length=500),
    document_type: DocumentType = Form(...),
    author: str | None = Form(default=None, max_length=500),
    rights_status: DocumentRightsStatus = Form(default=DocumentRightsStatus.RESTRICTED_INTERNAL),
    manager: IngestionManager = Depends(get_ingestion_manager),
    uploader_id: str = Depends(require_curator),
) -> DocumentUploadResponse:
    filename = file.filename or ""
    settings = get_settings()
    content = await file.read(settings.max_document_upload_bytes + 1)
    if len(content) > settings.max_document_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {settings.max_document_upload_bytes}-byte upload limit.",
        )
    try:
        manager.parser.validate_file_type(filename, document_type)
    except DocumentParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    try:
        document, job = await manager.create_upload(
            content=content,
            filename=filename,
            title=title.strip(),
            document_type=document_type,
            author=author.strip() if author else None,
            rights_status=rights_status,
            created_by=uploader_id,
        )
    except DuplicateDocumentError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": str(exc),
                "document_id": exc.document.get("id"),
            },
        ) from exc
    except (DocumentParseError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    background_tasks.add_task(
        manager.process_document,
        str(document["id"]),
        str(job["id"]),
        content,
        filename,
        document_type,
    )
    return DocumentUploadResponse(document=document, job=job)


@router.get("/jobs/{job_id}", response_model=DocumentJobResponse)
async def get_ingestion_job(
    job_id: str,
    manager: IngestionManager = Depends(get_ingestion_manager),
    _uploader_id: str = Depends(require_curator),
) -> DocumentJobResponse:
    job = await manager.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Processing job not found."
        )
    return DocumentJobResponse(job=ProcessingJobInDB.model_validate(job))


@router.get("/{document_id}/pages", response_model=list[DocumentPageInDB])
async def get_document_pages(
    document_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    manager: IngestionManager = Depends(get_ingestion_manager),
    _uploader_id: str = Depends(require_curator),
) -> list[DocumentPageInDB]:
    if await manager.get_document(document_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    rows = await manager.get_document_rows("document_pages", document_id, limit, offset)
    return [DocumentPageInDB.model_validate(row) for row in rows]


@router.get("/{document_id}/chunks", response_model=list[DocumentChunkInDB])
async def get_document_chunks(
    document_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    manager: IngestionManager = Depends(get_ingestion_manager),
    _uploader_id: str = Depends(require_curator),
) -> list[DocumentChunkInDB]:
    if await manager.get_document(document_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    rows = await manager.get_document_rows("document_chunks", document_id, limit, offset)
    return [DocumentChunkInDB.model_validate(row) for row in rows]
