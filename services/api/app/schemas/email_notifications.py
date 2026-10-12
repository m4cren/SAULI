"""The six values consumed by the saved EmailJS dashboard template."""

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EmailJSTemplateParams(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    to_email: str = Field(min_length=3, max_length=254)
    recipient_name: str = Field(min_length=1)
    item_summary: str = Field(min_length=1)
    found_location: str = Field(min_length=1)
    found_date: str = Field(min_length=1)
    match_url: str = Field(min_length=1)

    @field_validator("to_email")
    @classmethod
    def valid_recipient(cls, value: str) -> str:
        normalized = value.lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
            raise ValueError("Invalid notification email")
        return normalized
