"""Verify AI-proposed boundaries against ingested source pages and map source spans."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from app.schemas.ai import CandidateStoryBoundary, CandidateStorySegment
from app.schemas.document import DocumentChunkInDB, DocumentPageInDB
from app.schemas.story import StorySourceSpanCreate


@dataclass(frozen=True)
class VerifiedStoryBoundary:
    """Source-verified story text and ordered page-local source spans."""

    text: str
    document_char_start: int
    document_char_end: int
    source_spans: list[StorySourceSpanCreate]


@dataclass(frozen=True)
class _VerifiedSegment:
    start: int
    end: int
    text: str


class BoundaryReconciler:
    """Resolve approximate AI markers to exact source offsets without generating text."""

    def reconcile(
        self,
        candidate: CandidateStoryBoundary,
        source_chunk: DocumentChunkInDB,
        pages: Sequence[DocumentPageInDB],
        chunks: Sequence[DocumentChunkInDB],
    ) -> VerifiedStoryBoundary | None:
        ordered_pages = sorted(pages, key=lambda page: page.page_number)
        document_text, page_ranges = self._join_pages(ordered_pages)
        if not document_text or not candidate.evidence_quote.strip():
            return None

        if candidate.source_segments:
            if (
                candidate.source_segments[0].first_sentence != candidate.first_sentence
                or candidate.source_segments[-1].last_sentence != candidate.last_sentence
            ):
                return None
            proposed_segments = candidate.source_segments
        else:
            proposed_segments = [
                CandidateStorySegment(
                    first_sentence=candidate.first_sentence,
                    last_sentence=candidate.last_sentence,
                    approx_char_start=candidate.approx_char_start,
                    approx_char_end=candidate.approx_char_end,
                )
            ]
        segments: list[_VerifiedSegment] = []
        for proposed in proposed_segments:
            segment = self._verify_segment(
                proposed,
                source_chunk,
                document_text,
            )
            if segment is None:
                return None
            if segments and segment.start <= segments[-1].end:
                return None
            segments.append(segment)

        spans: list[StorySourceSpanCreate] = []
        for segment in segments:
            segment_spans = self._page_spans(segment, page_ranges, chunks)
            if not segment_spans:
                return None
            spans.extend(segment_spans)

        story_text = "\n".join(segment.text for segment in segments)
        if not story_text or candidate.evidence_quote not in story_text:
            return None

        return VerifiedStoryBoundary(
            text=story_text,
            document_char_start=segments[0].start,
            document_char_end=segments[-1].end,
            source_spans=[
                span.model_copy(update={"span_order": index})
                for index, span in enumerate(spans, start=1)
            ],
        )

    @staticmethod
    def _join_pages(
        pages: Sequence[DocumentPageInDB],
    ) -> tuple[str, list[tuple[DocumentPageInDB, int, int]]]:
        parts: list[str] = []
        ranges: list[tuple[DocumentPageInDB, int, int]] = []
        offset = 0
        for index, page in enumerate(pages):
            if index:
                parts.append("\n")
                offset += 1
            start = offset
            parts.append(page.extracted_text)
            offset += len(page.extracted_text)
            ranges.append((page, start, offset))
        return "".join(parts), ranges

    @classmethod
    def _verify_segment(
        cls,
        proposed: CandidateStorySegment,
        source_chunk: DocumentChunkInDB,
        document_text: str,
    ) -> _VerifiedSegment | None:
        if not proposed.first_sentence or not proposed.last_sentence:
            return None

        start_hint = source_chunk.char_start + proposed.approx_char_start
        end_hint = source_chunk.char_start + proposed.approx_char_end
        starts = cls._find_all(document_text, proposed.first_sentence)
        choices: list[tuple[int, _VerifiedSegment]] = []

        for start in starts:
            search_from = start + len(proposed.first_sentence)
            end_starts = (
                [start]
                if proposed.first_sentence == proposed.last_sentence
                else cls._find_all(document_text, proposed.last_sentence, search_from)
            )
            for end_start in end_starts:
                end = end_start + len(proposed.last_sentence)
                text = document_text[start:end]
                segment = _VerifiedSegment(start=start, end=end, text=text)
                distance = abs(start - start_hint) + abs(end - end_hint)
                choices.append((distance, segment))

        return min(choices, key=lambda choice: choice[0])[1] if choices else None

    @staticmethod
    def _find_all(text: str, needle: str, start: int = 0) -> list[int]:
        positions: list[int] = []
        cursor = start
        while True:
            position = text.find(needle, cursor)
            if position < 0:
                return positions
            positions.append(position)
            cursor = position + 1

    @staticmethod
    def _page_spans(
        segment: _VerifiedSegment,
        page_ranges: Sequence[tuple[DocumentPageInDB, int, int]],
        chunks: Sequence[DocumentChunkInDB],
    ) -> list[StorySourceSpanCreate]:
        spans: list[StorySourceSpanCreate] = []
        for page, page_start, page_end in page_ranges:
            start = max(segment.start, page_start)
            end = min(segment.end, page_end)
            if start >= end:
                continue
            chunk = max(
                (item for item in chunks if item.char_start < end and item.char_end > start),
                key=lambda item: min(end, item.char_end) - max(start, item.char_start),
                default=None,
            )
            spans.append(
                StorySourceSpanCreate(
                    document_page_id=UUID(str(page.id)),
                    chunk_id=UUID(str(chunk.id)) if chunk else None,
                    span_order=len(spans) + 1,
                    page_number=page.page_number,
                    char_start=start - page_start,
                    char_end=end - page_start,
                    verbatim_text=page.extracted_text[start - page_start : end - page_start],
                )
            )
        return spans
