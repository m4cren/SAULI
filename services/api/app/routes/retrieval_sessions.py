"""Claimant QR lifecycle, kiosk simulation, and administrator retrieval logs."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request

from app.auth.dependencies import get_admin_user, get_current_user
from app.auth.kiosk import get_kiosk_session
from app.core.errors import ServiceError
from app.schemas.auth import UserResponse
from app.schemas.retrieval_sessions import (
    CreateRetrievalRequest,
    IssuedRetrievalResponse,
    RetrievalLogResponse,
    RetrievalStatusResponse,
    SimulatedRetrievalResponse,
    ValidatedRetrievalResponse,
    ValidateQrRequest,
)
from app.services.retrieval_sessions import checked, issue, replace, simulate, validate

router = APIRouter(prefix="/api/retrieval-sessions", tags=["retrieval-sessions"])
log = logging.getLogger(__name__)


async def with_unit(repo, row: dict, user_id: UUID) -> dict:
    if row.get("error") or not hasattr(repo, "retrieval_unit"):
        return row
    try:
        return {**row, "unit": await repo.retrieval_unit(UUID(row["id"]), user_id)}
    except Exception:
        # QR issuance and status must remain usable if only the public station
        # address lookup is temporarily unavailable.
        log.warning("Retrieval station location lookup unavailable", exc_info=True)
        return {**row, "unit": None}


@router.post("", response_model=IssuedRetrievalResponse)
async def create_session(
    request: Request,
    payload: CreateRetrievalRequest,
    user: Annotated[UserResponse, Depends(get_current_user)],
):
    row = await issue(
        request.app.state.items,
        request.app.state.settings,
        payload.match_candidate_id,
        UUID(user.id),
        user.name or user.email,
    )
    return await with_unit(request.app.state.items, row, UUID(user.id))


@router.post("/validate", response_model=ValidatedRetrievalResponse)
async def validate_qr(request: Request, payload: ValidateQrRequest,
                      kiosk: Annotated[dict, Depends(get_kiosk_session)]):
    result = await validate(
        request.app.state.items, request.app.state.settings, payload.qr_payload, UUID(kiosk["unit_id"])
    )
    try:
        await request.app.state.kiosks.enqueue_workflow_unlock(
            kiosk, session_id=str(result["id"]))
        return {**result, "unlock_status": "queued"}
    except Exception:
        log.warning("Validated retrieval unlock unavailable", extra={"session_id": str(result["id"])})
        return {**result, "unlock_status": "unavailable"}


@router.post("/{session_id}/request-unlock")
async def retry_retrieval_unlock(
    request: Request, session_id: UUID,
    kiosk: Annotated[dict, Depends(get_kiosk_session)],
):
    result = await request.app.state.kiosks.enqueue_workflow_unlock(
        kiosk, session_id=str(session_id))
    return {"status": result["status"]}


@router.get("/admin/logs", response_model=list[RetrievalLogResponse])
async def admin_logs(
    request: Request, _admin: Annotated[UserResponse, Depends(get_admin_user)]
):
    return await request.app.state.items.retrieval_logs()


@router.get("/history", response_model=list[RetrievalLogResponse])
async def claimant_history(
    request: Request, user: Annotated[UserResponse, Depends(get_current_user)]
):
    return await request.app.state.items.claimant_retrieval_logs(UUID(user.id))


@router.get("/{session_id}", response_model=RetrievalStatusResponse)
async def get_session(
    request: Request,
    session_id: UUID,
    user: Annotated[UserResponse, Depends(get_current_user)],
):
    row = checked(
        await request.app.state.items.retrieval_status(session_id, UUID(user.id))
    )
    return await with_unit(request.app.state.items, row, UUID(user.id))


@router.post("/{session_id}/replace", response_model=IssuedRetrievalResponse)
async def replace_session(
    request: Request,
    session_id: UUID,
    user: Annotated[UserResponse, Depends(get_current_user)],
):
    row = await replace(
        request.app.state.items, request.app.state.settings, session_id, UUID(user.id)
    )
    return await with_unit(request.app.state.items, row, UUID(user.id))


async def simulation(
    request: Request, session_id: UUID, action_token: str | None, event: str, kiosk: dict
):
    return await simulate(
        request.app.state.items,
        request.app.state.settings,
        session_id,
        action_token or "",
        event,
        UUID(kiosk["unit_id"]),
    )


@router.post(
    "/{session_id}/simulate-completion", response_model=SimulatedRetrievalResponse
)
async def simulate_completion(
    request: Request, session_id: UUID, kiosk: Annotated[dict, Depends(get_kiosk_session)], x_retrieval_action: str | None = Header(None)
):
    return await simulation(
        request, session_id, x_retrieval_action, "correct_item_lifted", kiosk
    )


@router.post(
    "/{session_id}/simulate-wrong-item", response_model=SimulatedRetrievalResponse
)
async def simulate_wrong_item(
    request: Request, session_id: UUID, kiosk: Annotated[dict, Depends(get_kiosk_session)], x_retrieval_action: str | None = Header(None)
):
    return await simulation(
        request, session_id, x_retrieval_action, "wrong_item_lifted", kiosk
    )


@router.post(
    "/{session_id}/simulate-item-returned", response_model=SimulatedRetrievalResponse
)
async def simulate_item_returned(
    request: Request, session_id: UUID, kiosk: Annotated[dict, Depends(get_kiosk_session)], x_retrieval_action: str | None = Header(None)
):
    return await simulation(request, session_id, x_retrieval_action, "item_returned", kiosk)
