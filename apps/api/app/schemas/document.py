"""
Pydantic v2 Schemas for Documents, Pages, Chunks, and Ingestion Jobs.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import (
    DocumentType,
    DocumentRightsStatus,
    JobStatus,
    JobLogLevel,
)


class DocumentBase(BaseModel):
    """Core attributes of an uploaded or registered document."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    title: str = Field(description="Title of book, article, or transcript")
    author: Optional[str] = Field(default=None, description="Author or speaker name")
    document_type: DocumentType = Field(description="Document format classification")
    source_file_path: str = Field(description="Storage bucket path or relative path")
    file_hash_sha256: str = Field(
        min_length=64,
        max_length=64,
        description="SHA-256 checksum for document immutability and deduplication"
    )
    page_count: Optional[int] = Field(default=None, ge=1, description="Total pages if PDF")
    rights_status: DocumentRightsStatus = Field(
        default=DocumentRightsStatus.RESTRICTED_INTERNAL,
        description="Copyright clearance status"
    )
    publication_restrictions: Optional[str] = Field(
        default=None,
        description="Explicit legal conditions preventing public display"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary document metadata (ISBN, publisher, year, etc.)"
    )


class DocumentCreate(DocumentBase):
    """Payload for creating a new document record."""
    pass


class DocumentUpdate(BaseModel):
    """Payload for updating document metadata or publication rights."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    title: Optional[str] = None
    author: Optional[str] = None
    rights_status: Optional[DocumentRightsStatus] = None
    publication_restrictions: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class DocumentInDB(DocumentBase):
    """Database representation of a document."""
    id: UUID = Field(description="Document unique UUID")
    created_by: Optional[UUID] = Field(default=None, description="Uploader user UUID")
    created_at: datetime = Field(description="Upload timestamp")
    updated_at: datetime = Field(description="Last update timestamp")


class DocumentPageBase(BaseModel):
    """Extracted text and metadata for a single document page."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    page_number: int = Field(ge=1, description="1-based page number")
    extracted_text: str = Field(description="Verbatim plain text extracted from page")
    char_count: int = Field(ge=0, description="Character count of extracted text")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Page layout metadata")


class DocumentPageInDB(DocumentPageBase):
    """Database representation of a document page."""
    id: UUID = Field(description="Page UUID")
    document_id: UUID = Field(description="Parent document UUID")
    created_at: datetime = Field(description="Creation timestamp")


class DocumentChunkBase(BaseModel):
    """Pre-processed text chunk for AI prompt ingestion and vector embeddings."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    chunk_index: int = Field(ge=0, description="Sequential 0-based chunk index")
    token_count: int = Field(ge=1, description="Token count using tokenizer")
    text: str = Field(description="Chunk text content")
    page_start: int = Field(ge=1, description="Starting page number")
    page_end: int = Field(ge=1, description="Ending page number")
    char_start: int = Field(ge=0, description="Starting character offset in document")
    char_end: int = Field(ge=1, description="Ending character offset in document")


class DocumentChunkInDB(DocumentChunkBase):
    """Database representation of a document chunk."""
    id: UUID = Field(description="Chunk UUID")
    document_id: UUID = Field(description="Parent document UUID")
    created_at: datetime = Field(description="Creation timestamp")


class ProcessingJobEventBase(BaseModel):
    """Log event emitted during document ingestion or AI processing."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    stage: str = Field(description="Processing stage name (e.g. 'extract', 'chunk', 'ai_eval')")
    level: JobLogLevel = Field(default=JobLogLevel.INFO, description="Log severity")
    message: str = Field(description="Human-readable event message")
    details: Dict[str, Any] = Field(default_factory=dict, description="Diagnostic payload")


class ProcessingJobEventInDB(ProcessingJobEventBase):
    """Database representation of a processing job event."""
    id: UUID = Field(description="Event UUID")
    job_id: UUID = Field(description="Parent processing job UUID")
    created_at: datetime = Field(description="Timestamp of event")


class ProcessingJobBase(BaseModel):
    """Asynchronous background processing job for a document."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    document_id: Optional[UUID] = Field(default=None, description="Target document UUID")
    job_type: str = Field(description="Job type (e.g. 'pdf_extraction', 'story_discovery')")
    status: JobStatus = Field(default=JobStatus.PENDING, description="Job execution status")
    error_message: Optional[str] = Field(default=None, description="Failure reason if failed")
    config: Dict[str, Any] = Field(default_factory=dict, description="Job parameter configuration")


class ProcessingJobCreate(ProcessingJobBase):
    """Payload to initiate a new processing job."""
    pass


class ProcessingJobInDB(ProcessingJobBase):
    """Database representation of a processing job with events."""
    id: UUID = Field(description="Job UUID")
    events: List[ProcessingJobEventInDB] = Field(
        default_factory=list,
        description="Audit log events associated with job"
    )
    created_at: datetime = Field(description="Job submission timestamp")
    updated_at: datetime = Field(description="Job last status update timestamp")

