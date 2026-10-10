"""Strict two-view analysis and public found-item contracts."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1500)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=250)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=250)]
Summary = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1500)]
TextList = Annotated[list[Text], Field(max_length=60)]
Confidence = Literal["high", "medium", "low"]
DocumentKind = Literal["none", "school ID", "driver's license", "government ID", "passport", "bank card", "identification card", "sensitive document"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ComponentCount(StrictModel):
    component: Name
    count: int = Field(ge=0, le=1000)
    count_is_estimate: bool


class SurfaceAssessment(StrictModel):
    component: Name
    status: Literal["visible_damage", "no_visible_damage", "not_assessable"]
    damage_types: TextList
    location: Text
    severity: Literal["minor", "moderate", "severe"] | None
    certainty: Literal["confirmed", "probable", "uncertain"]
    evidence: Text


class ViewObservation(StrictModel):
    image_index: Literal[1, 2]
    visible_region: Text
    image_quality: Text
    damage_observations: TextList
    notes: TextList


class FoundItemAnalysis(StrictModel):
    views_consistent: bool
    generic_name: Name
    object_name: Name
    alternative_names: TextList
    object_count: int = Field(ge=1, le=1000)
    component_counts: list[ComponentCount] = Field(max_length=60)
    count_is_estimate: bool
    count_confidence: Confidence
    counting_notes: TextList
    category: ShortText
    subcategory: ShortText
    document_kind: DocumentKind
    document_owner_name: ShortText | None
    colors: TextList
    material: TextList
    brand: ShortText | None
    model_or_variant: ShortText | None
    visible_markings: TextList
    functional_components: TextList
    condition: Literal["new", "good", "fair", "poor", "unknown"]
    condition_visibility: Text
    condition_confidence: Confidence
    surface_assessments: list[SurfaceAssessment] = Field(max_length=60)
    condition_details: TextList
    patterns: TextList
    distinctive_features: TextList
    likely_use: Text
    short_description: Text
    confidence: Confidence
    needs_review: bool
    uncertainty_notes: TextList
    extraction_summary: Summary
    received_view_count: int = Field(ge=0, le=2)
    view_observations: list[ViewObservation] = Field(max_length=2)

    @model_validator(mode="after")
    def flag_uncertain_views(self):
        if not self.views_consistent or self.received_view_count != 2 or {view.image_index for view in self.view_observations} != {1, 2} or self.confidence == "low":
            self.needs_review = True
        return self


class AnalysisResponse(StrictModel):
    analysis: FoundItemAnalysis
    found_location: str
    notes: str | None
    summary: str
    model: str


class ReconcileRequest(StrictModel):
    analysis: FoundItemAnalysis
    found_location: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] | None = None
    correction_notes: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=1500)]


class ConfirmedItemResponse(StrictModel):
    item_id: UUID
    status: Literal["available"] = "available"
    summary: str
    found_location: str
    found_at: AwareDatetime


class FoundItemDetailsResponse(StrictModel):
    item_id: UUID
    status: Literal["available", "claimed", "retrieved", "archived"]
    name: str
    summary: str
    category: str
    colors: list[str]
    visible_markings: list[str]
    condition: str
    found_location: str
    found_at: AwareDatetime
    front_image_url: str | None
    back_image_url: str | None


def normalize_location_notes(location: str, notes: str | None) -> tuple[str, str | None]:
    location = location.strip()
    notes = notes.strip() if notes is not None else None
    if not 1 <= len(location) <= 200:
        raise ValueError("Location must be between 1 and 200 characters")
    if notes and len(notes) > 1000:
        raise ValueError("Notes must be at most 1000 characters")
    return location, notes or None


def strict_analysis_json(value: str) -> FoundItemAnalysis:
    import json
    data = json.loads(value)
    if not isinstance(data, dict) or set(data) != set(FoundItemAnalysis.model_fields):
        raise ValueError("Analysis must contain every expected field and no extras")
    return FoundItemAnalysis.model_validate(data, strict=True)
