"""Small structured verdict for the two captured item views."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


Feature = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=200)]


class ViewConsistency(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    verdict: Literal["same", "different", "uncertain", "no_item"]
    image_1_features: list[Feature] = Field(max_length=8)
    image_2_features: list[Feature] = Field(max_length=8)
    matching_features: list[Feature] = Field(max_length=8)
    conflicting_features: list[Feature] = Field(max_length=8)
    reason: str = Field(max_length=500)

    @property
    def is_reliably_same(self) -> bool:
        unique_matches = {feature.casefold() for feature in self.matching_features}
        return self.verdict == "same" and len(unique_matches) >= 2 and not self.conflicting_features
