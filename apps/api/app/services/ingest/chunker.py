"""Token-bounded sliding-window chunks with document-relative character offsets."""

from __future__ import annotations

from bisect import bisect_left, bisect_right

import tiktoken

from app.schemas.document import DocumentChunkBase, DocumentPageBase


class SemanticChunker:
    """Create overlapping token windows while preserving exact source offsets."""

    def __init__(
        self,
        max_tokens: int = 800,
        overlap_tokens: int = 100,
        encoding_name: str = "cl100k_base",
    ) -> None:
        if max_tokens < 1:
            raise ValueError("max_tokens must be at least 1")
        if overlap_tokens < 0 or overlap_tokens >= max_tokens:
            raise ValueError("overlap_tokens must be between 0 and max_tokens - 1")
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        self.encoding = tiktoken.get_encoding(encoding_name)

    def chunk(self, pages: list[DocumentPageBase]) -> list[DocumentChunkBase]:
        if not pages:
            return []

        ordered_pages = sorted(pages, key=lambda page: page.page_number)
        text_parts: list[str] = []
        page_ranges: list[tuple[int, int, int]] = []
        document_offset = 0

        for index, page in enumerate(ordered_pages):
            if index:
                text_parts.append("\n")
                document_offset += 1
            start = document_offset
            text_parts.append(page.extracted_text)
            document_offset += len(page.extracted_text)
            page_ranges.append((page.page_number, start, document_offset))

        document_text = "".join(text_parts)
        token_ids = self.encoding.encode(document_text, disallowed_special=())
        if not token_ids:
            return []

        token_byte_boundaries = [0]
        for token_id in token_ids:
            token_byte_boundaries.append(
                token_byte_boundaries[-1] + len(self.encoding.decode_single_token_bytes(token_id))
            )

        char_byte_boundaries = [0]
        for character in document_text:
            char_byte_boundaries.append(char_byte_boundaries[-1] + len(character.encode("utf-8")))

        chunks: list[DocumentChunkBase] = []
        token_start = 0
        while token_start < len(token_ids):
            token_end = min(token_start + self.max_tokens, len(token_ids))
            start_byte = token_byte_boundaries[token_start]
            start_char = bisect_left(char_byte_boundaries, start_byte)

            while token_end > token_start:
                end_byte = token_byte_boundaries[token_end]
                end_char = bisect_right(char_byte_boundaries, end_byte) - 1
                if end_char > start_char:
                    chunk_text = document_text[start_char:end_char]
                    chunk_token_count = len(self.encoding.encode(chunk_text, disallowed_special=()))
                    if chunk_token_count <= self.max_tokens:
                        break
                token_end -= 1
            else:
                raise RuntimeError("Unable to produce a non-empty token-bounded chunk.")

            page_start, page_end = self._page_bounds(start_char, end_char, page_ranges)
            chunks.append(
                DocumentChunkBase(
                    chunk_index=len(chunks),
                    token_count=chunk_token_count,
                    text=chunk_text,
                    page_start=page_start,
                    page_end=page_end,
                    char_start=start_char,
                    char_end=end_char,
                )
            )
            if token_end >= len(token_ids):
                break
            token_start = max(token_start + 1, token_end - self.overlap_tokens)

        return chunks

    @staticmethod
    def _page_bounds(
        char_start: int,
        char_end: int,
        page_ranges: list[tuple[int, int, int]],
    ) -> tuple[int, int]:
        overlapping_pages = [
            page_number
            for page_number, page_start, page_end in page_ranges
            if page_start < char_end and page_end > char_start
        ]
        if not overlapping_pages:
            nearest_page = min(
                page_ranges,
                key=lambda page: min(abs(char_start - page[1]), abs(char_start - page[2])),
            )[0]
            return nearest_page, nearest_page
        return overlapping_pages[0], overlapping_pages[-1]
