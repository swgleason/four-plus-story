"""
Pydantic v2 Schemas for Hybrid Search (Full-Text Search + pgvector Semantic Search).
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.enums import EmotionType, StoryVariant


class HybridSearchRequest(BaseModel):
    """Search request parameter contract."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    query: str = Field(min_length=1, description="Natural language search query")
    filter_variant: StoryVariant | None = Field(
        default=None,
        description="Filter results by one of the authoritative 4 variants",
    )
    filter_emotion: EmotionType | None = Field(
        default=None,
        description="Filter results by specific Big 6 or connective emotion",
    )
    limit: int = Field(default=20, ge=1, le=50, description="Max results to return")
    offset: int = Field(default=0, ge=0, description="Offset for pagination")

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Search query must not be blank.")
        return normalized


class HybridSearchResultItem(BaseModel):
    """Individual item in search result set."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    story_id: UUID = Field(description="Story UUID")
    title: str = Field(description="Story title")
    original_text_preview: str = Field(description="Preview excerpt of story text")
    original_word_count: int = Field(ge=0, description="Story word count")
    estimated_spoken_duration_seconds: int = Field(ge=0, description="Estimated duration")
    length_advisory_exceeds_800_words: bool = Field(description="True if word count > 800")
    rrf_score: float = Field(description="Reciprocal Rank Fusion relevance score")


class HybridSearchResponse(BaseModel):
    """Composite hybrid search response payload."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    query: str = Field(description="Executed query string")
    total_matched: int = Field(ge=0, description="Total matching stories found")
    results: list[HybridSearchResultItem] = Field(
        default_factory=list,
        description="Ranked list of search results",
    )
