"""Authenticated missing-report and candidate review contracts."""

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.schemas.search import SearchResult


class ReportModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateMissingReportRequest(ReportModel):
    search_request_id: UUID
    notification_email: str = Field(min_length=3, max_length=254)
    email_notifications_enabled: bool = True

    @field_validator("notification_email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
            raise ValueError("Enter a valid email address")
        return normalized


class MissingReportResponse(ReportModel):
    id: UUID
    search_request_id: UUID
    summary: str
    notification_email: str
    email_notifications_enabled: bool
    status: Literal["active", "matched", "resolved", "cancelled"]
    created_at: AwareDatetime


class MissingReportDetailResponse(MissingReportResponse):
    candidate: SearchResult | None = None
    candidate_decision: Literal["pending", "accepted", "rejected"] | None = None
    monitored_at: datetime | None = None
