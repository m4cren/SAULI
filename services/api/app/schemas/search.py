"""Search extraction, comparison and public result contracts."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, Field, StringConstraints, field_validator

from app.schemas.found_items import StrictModel, TextList


class QueryAnalysis(StrictModel):
    generic_name: str
    specific_description: str
    alternative_names: TextList
    category: str | None
    colors: TextList
    material: TextList
    brand: str | None
    model: str | None
    markings: TextList
    distinctive_features: TextList
    condition: TextList
    damage: TextList
    components: TextList
    location: str | None
    last_seen_at: str | None
    searchable_summary: str
    uncertainty: TextList


class CandidateComparison(StrictModel):
    candidate_id: UUID
    similarity: float = Field(ge=0, le=1)
    matched_attributes: TextList
    differences: TextList
    explanation: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    plausible: bool


class CandidateBatch(StrictModel):
    comparisons: list[CandidateComparison]


class SearchRequest(StrictModel):
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=2500)]
    category: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None = None
    color: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None = None
    last_seen_location: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None
    last_seen_at: AwareDatetime | None = None
    additional_filters: dict[str, str] = Field(default_factory=dict)

    @field_validator("last_seen_at", mode="before")
    @classmethod
    def parse_iso_last_seen_at(cls, value: datetime | str | None) -> datetime | None:
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value

    @field_validator("additional_filters")
    @classmethod
    def bounded_filters(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > 20 or any(len(key) > 80 or len(item) > 200 for key, item in value.items()):
            raise ValueError("Too many or oversized filters")
        return value


class ScoreBreakdown(StrictModel):
    ai_similarity: float = Field(ge=0, le=1)
    deterministic_features: float = Field(ge=0, le=1)
    location_similarity: float = Field(ge=0, le=1)
    time_proximity: float = Field(ge=0, le=1)


class SearchResult(StrictModel):
    item_id: UUID
    match_candidate_id: UUID
    rank: int = Field(ge=1)
    rank_score: float = Field(ge=0, le=100)
    name: str
    summary: str
    found_location: str
    found_at: AwareDatetime
    front_image_url: str | None
    matched_attributes: list[str]
    differences: list[str]
    explanation: str
    score_breakdown: ScoreBreakdown


class SearchResponse(StrictModel):
    search_request_id: UUID
    query: dict[str, str | None]
    results: list[SearchResult]


class ClaimDecisionResponse(StrictModel):
    match_candidate_id: UUID
    decision: Annotated[str, StringConstraints(pattern=r"^(accepted|rejected)$")]
    item_id: UUID | None = None
    slot_code: str | None = None
    section: str | None = None
