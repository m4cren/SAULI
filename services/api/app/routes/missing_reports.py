"""Authenticated missing reports and protected notification retry."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request

from app.auth.dependencies import get_admin_user, get_claimant_user
from app.core.errors import ServiceError
from app.routes.found_items import required_key
from app.schemas.auth import UserResponse
from app.schemas.missing_reports import (
    CreateMissingReportRequest,
    MissingReportDetailResponse,
    MissingReportResponse,
)
from app.services.missing_reports import report_detail

router = APIRouter(prefix="/api/missing-reports", tags=["missing-reports"])


def public_report_fields(row: dict, response_model: type[MissingReportResponse]) -> dict:
    return {name: row[name] for name in response_model.model_fields if name in row}


@router.post("", response_model=MissingReportResponse)
async def create_report(request: Request, payload: CreateMissingReportRequest,
                        user: Annotated[UserResponse, Depends(get_claimant_user)],
                        x_idempotency_key: str | None = Header(None)):
    row = await request.app.state.items.create_missing_report(
        payload.search_request_id, UUID(user.id), payload.notification_email,
        payload.email_notifications_enabled, user.name or "SAULI user",
        required_key(x_idempotency_key))
    if row.get("error"):
        status = 409 if row["error"] == "REPORT_CONFLICT" else 404
        raise ServiceError(row["error"], "The original search cannot be used for this report.", status)
    return public_report_fields(row, MissingReportResponse)


@router.post("/admin/retry-unconfigured-email")
async def retry_unconfigured_email(request: Request,
                                   _admin: Annotated[UserResponse, Depends(get_admin_user)]):
    if not request.app.state.settings.emailjs_enabled or not request.app.state.settings.emailjs_configured:
        raise ServiceError("EMAILJS_NOT_CONFIGURED", "Configure EmailJS before retrying.", 409)
    count = await request.app.state.items.retry_unconfigured_email()
    return {"queued": count}


@router.get("/{report_id}", response_model=MissingReportDetailResponse)
async def get_report(request: Request, report_id: UUID,
                     user: Annotated[UserResponse, Depends(get_claimant_user)]):
    row = await request.app.state.items.get_missing_report(report_id, UUID(user.id))
    if not row:
        raise ServiceError("REPORT_NOT_FOUND", "This missing-item report was not found.", 404)
    detail = await report_detail(request.app.state.items, row,
                                 request.app.state.settings.match_notification_min_score)
    return public_report_fields(detail, MissingReportDetailResponse)
