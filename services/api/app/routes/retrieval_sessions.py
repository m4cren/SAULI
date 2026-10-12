"""Claimant QR lifecycle, kiosk simulation, and administrator retrieval logs."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request

from app.auth.dependencies import get_admin_user, get_current_user
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


@router.post("", response_model=IssuedRetrievalResponse)
async def create_session(
    request: Request,
    payload: CreateRetrievalRequest,
    user: Annotated[UserResponse, Depends(get_current_user)],
):
    return await issue(
        request.app.state.items,
        request.app.state.settings,
        payload.match_candidate_id,
        UUID(user.id),
        user.name or user.email,
    )


@router.post("/validate", response_model=ValidatedRetrievalResponse)
async def validate_qr(request: Request, payload: ValidateQrRequest):
    return await validate(
        request.app.state.items, request.app.state.settings, payload.qr_payload
    )


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
    return checked(
        await request.app.state.items.retrieval_status(session_id, UUID(user.id))
    )


@router.post("/{session_id}/replace", response_model=IssuedRetrievalResponse)
async def replace_session(
    request: Request,
    session_id: UUID,
    user: Annotated[UserResponse, Depends(get_current_user)],
):
    return await replace(
        request.app.state.items, request.app.state.settings, session_id, UUID(user.id)
    )


async def simulation(
    request: Request, session_id: UUID, action_token: str | None, event: str
):
    return await simulate(
        request.app.state.items,
        request.app.state.settings,
        session_id,
        action_token or "",
        event,
    )


@router.post(
    "/{session_id}/simulate-completion", response_model=SimulatedRetrievalResponse
)
async def simulate_completion(
    request: Request, session_id: UUID, x_retrieval_action: str | None = Header(None)
):
    return await simulation(
        request, session_id, x_retrieval_action, "correct_item_lifted"
    )


@router.post(
    "/{session_id}/simulate-wrong-item", response_model=SimulatedRetrievalResponse
)
async def simulate_wrong_item(
    request: Request, session_id: UUID, x_retrieval_action: str | None = Header(None)
):
    return await simulation(
        request, session_id, x_retrieval_action, "wrong_item_lifted"
    )


@router.post(
    "/{session_id}/simulate-item-returned", response_model=SimulatedRetrievalResponse
)
async def simulate_item_returned(
    request: Request, session_id: UUID, x_retrieval_action: str | None = Header(None)
):
    return await simulation(request, session_id, x_retrieval_action, "item_returned")
