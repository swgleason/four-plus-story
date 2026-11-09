# Four Plus Story Library - Backend API

FastAPI backend service responsible for:
- Document ingestion & text extraction (PyMuPDF for PDF, utf-8 TXT normalization).
- Chunking and boundary extraction.
- AI pipeline orchestration (discovery, five 4+ criteria evaluation, four variant classification, STEP extraction).
- Vector embedding generation and pgvector storage.
- Hybrid search (PostgreSQL full-text search combined with pgvector cosine similarity).
- Administrative curation endpoints and mobile consumption endpoints.

## Tech Stack
- Python 3.13 / 3.11+
- FastAPI & Uvicorn
- Pydantic v2
- PyMuPDF (`fitz`)
- Supabase Python Client (PostgreSQL + pgvector)
- Provider-independent AI layer (Anthropic / OpenAI / Gemini / Ollama)

## Document Ingestion

The authenticated upload endpoint is `POST /api/v1/documents/upload`. It accepts a
PDF book/article or UTF-8 `.txt` transcript/story note and requires a Supabase
access token for a curator or administrator. Original files are stored in the
configured Supabase Storage bucket (`RAW_DOCUMENTS_BUCKET`, default
`raw-documents`). SHA-256 deduplication runs before storage; duplicate uploads
return HTTP 409 with the existing document ID.

Uploads create a `document_ingestion` processing job. FastAPI background processing
extracts PDF pages with PyMuPDF (including page dimensions and text-block layout
metadata), or text pages split at form feeds, then creates overlapping chunks using
`tiktoken`'s `cl100k_base` encoding. Chunk offsets refer to the extracted document
text formed by joining page text with a newline. Configure the token window and
overlap with `DOCUMENT_CHUNK_MAX_TOKENS` and `DOCUMENT_CHUNK_OVERLAP_TOKENS`.

Curators can poll `GET /api/v1/documents/jobs/{job_id}` and retrieve
`GET /api/v1/documents/{document_id}/pages` or `/chunks` with `limit` and `offset`.
Job events record stages and counts only; extracted document contents are not
written to logs or event details.

Run ingestion tests from `apps/api` with:

```sh
.venv/bin/python -m pytest tests/test_ingest.py -q
```
