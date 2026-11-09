"""Extract searchable text and layout metadata from supported source documents."""

from __future__ import annotations

from typing import Any

import pymupdf

from app.schemas.document import DocumentPageBase
from app.schemas.enums import DocumentType


class DocumentParseError(ValueError):
    """Raised when an uploaded document cannot be parsed safely."""


class DocumentParser:
    """Parse PDFs and UTF-8 text files into 1-based page records."""

    def parse(
        self, content: bytes, filename: str, document_type: DocumentType
    ) -> list[DocumentPageBase]:
        self.validate_file_type(filename, document_type)
        if document_type in (DocumentType.PDF_BOOK, DocumentType.PDF_ARTICLE):
            return self.parse_pdf(content)
        return self.parse_text(content)

    @staticmethod
    def validate_file_type(filename: str, document_type: DocumentType) -> None:
        suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if document_type in (DocumentType.PDF_BOOK, DocumentType.PDF_ARTICLE):
            if suffix != "pdf":
                raise DocumentParseError("PDF document types require a .pdf file.")
        elif document_type in (DocumentType.TXT_TRANSCRIPT, DocumentType.TXT_STORY_NOTE):
            if suffix != "txt":
                raise DocumentParseError("Text document types require a .txt file.")
        else:
            raise DocumentParseError("Unsupported document type.")

    def parse_pdf(self, content: bytes) -> list[DocumentPageBase]:
        if not content:
            raise DocumentParseError("The PDF file is empty.")
        try:
            document: Any = pymupdf.open(  # type: ignore[no-untyped-call]
                stream=content,
                filetype="pdf",
            )
        except (pymupdf.FileDataError, RuntimeError, ValueError) as exc:
            raise DocumentParseError("The uploaded file is not a readable PDF.") from exc

        pages: list[DocumentPageBase] = []
        try:
            if document.is_encrypted:
                raise DocumentParseError("Password-protected PDF files are not supported.")
            for page_index, page in enumerate(document, start=1):
                text = page.get_text("text", sort=True)
                layout = page.get_text("dict", sort=True)
                blocks = [
                    {
                        "block_index": block_index,
                        "bbox": [round(float(value), 2) for value in block["bbox"]],
                        "line_count": len(block.get("lines", [])),
                        "span_count": sum(
                            len(line.get("spans", [])) for line in block.get("lines", [])
                        ),
                    }
                    for block_index, block in enumerate(layout.get("blocks", []))
                    if block.get("type") == 0
                ]
                pages.append(
                    DocumentPageBase(
                        page_number=page_index,
                        extracted_text=text,
                        char_count=len(text),
                        metadata={
                            "width": round(float(page.rect.width), 2),
                            "height": round(float(page.rect.height), 2),
                            "rotation": page.rotation,
                            "text_block_count": len(blocks),
                            "text_blocks": blocks,
                        },
                    )
                )
        finally:
            document.close()

        if not pages:
            raise DocumentParseError("The PDF contains no pages.")
        if not any(page.extracted_text.strip() for page in pages):
            raise DocumentParseError("The PDF contains no extractable text.")
        return pages

    def parse_text(self, content: bytes) -> list[DocumentPageBase]:
        if not content:
            raise DocumentParseError("The text file is empty.")
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise DocumentParseError("Text files must use UTF-8 encoding.") from exc

        page_texts = text.split("\f")
        if not any(page.strip() for page in page_texts):
            raise DocumentParseError("The text file contains no extractable text.")

        return [
            DocumentPageBase(
                page_number=page_number,
                extracted_text=page_text,
                char_count=len(page_text),
                metadata={"source_format": "text"},
            )
            for page_number, page_text in enumerate(page_texts, start=1)
        ]
