"""Retrieval business operations; database transitions are single RPC transactions."""

from uuid import UUID

from app.core.errors import ServiceError
from app.services.retrieval_tokens import (
    TOKEN_PATTERN,
    new_token,
    parse_qr_payload,
    qr_payload,
    token_hash,
)

ERRORS = {
    "MATCH_NOT_FOUND": (404, "This match does not belong to your search."),
    "RETRIEVAL_NOT_FOUND": (404, "Retrieval session not found."),
    "RETRIEVAL_SESSION_EXISTS": (409, "This item already has an active retrieval."),
    "INVALID_RETRIEVAL_TOKEN": (404, "This retrieval QR is not valid."),
    "RETRIEVAL_QR_EXPIRED": (410, "This retrieval QR has expired."),
    "RETRIEVAL_QR_ALREADY_USED": (409, "This retrieval QR has already been used."),
    "RETRIEVAL_CANCELLED": (410, "This retrieval QR was cancelled."),
    "ITEM_NOT_AVAILABLE": (409, "This item is no longer available for retrieval."),
    "STORAGE_POSITION_MISMATCH": (409, "The item's storage position has changed."),
    "WRONG_ITEM_NOT_RETURNED": (409, "Return the wrong item before continuing."),
    "INVALID_RETRIEVAL_ACTION": (403, "This kiosk retrieval action is not authorized."),
    "INVALID_REQUEST": (422, "Check the retrieval request and try again."),
}


def checked(row: dict) -> dict:
    code = row.get("error")
    if code:
        status, message = ERRORS.get(
            code, (503, "Retrieval is unavailable. Please try again.")
        )
        raise ServiceError(code, message, status)
    return row


def pepper(settings) -> str:
    # A dev server can work without a real secret; all its QR tokens expire on restart.
    return settings.retrieval_token_pepper or settings._ephemeral_retrieval_pepper


async def issue(
    repo, settings, candidate_id: UUID, user_id: UUID, display_name: str | None
) -> dict:
    raw = new_token()
    row = checked(
        await repo.issue_retrieval(
            candidate_id,
            user_id,
            token_hash(raw, pepper(settings)),
            settings.retrieval_qr_ttl_minutes,
            display_name or "Claimant",
        )
    )
    return {**row, "raw_token": raw, "qr_payload": qr_payload(raw)}


async def replace(repo, settings, session_id: UUID, user_id: UUID) -> dict:
    raw = new_token()
    row = checked(
        await repo.replace_retrieval(
            session_id,
            user_id,
            token_hash(raw, pepper(settings)),
            settings.retrieval_qr_ttl_minutes,
        )
    )
    return {**row, "raw_token": raw, "qr_payload": qr_payload(raw)}


async def validate(repo, settings, payload: str) -> dict:
    raw = parse_qr_payload(payload)
    action = new_token()
    row = checked(
        await repo.validate_retrieval(
            token_hash(raw, pepper(settings)), token_hash(action, pepper(settings))
        )
    )
    return {**row, "action_token": action}


async def simulate(
    repo, settings, session_id: UUID, action_token: str, event: str
) -> dict:
    if not TOKEN_PATTERN.fullmatch(action_token):
        raise ServiceError(
            "INVALID_RETRIEVAL_ACTION",
            "This kiosk retrieval action is not authorized.",
            403,
        )
    return checked(
        await repo.simulate_retrieval(
            session_id, token_hash(action_token, pepper(settings)), event
        )
    )
