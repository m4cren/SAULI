"""Versioned, opaque retrieval capabilities; raw values never enter database rows."""

import hashlib
import hmac
import re
import secrets

from app.core.errors import ServiceError

QR_PREFIX = "SAULI:RETRIEVAL:v1:"
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(raw: str, pepper: str) -> str:
    return hmac.new(
        pepper.encode("utf-8"), raw.encode("ascii"), hashlib.sha256
    ).hexdigest()


def qr_payload(raw: str) -> str:
    return f"{QR_PREFIX}{raw}"


def parse_qr_payload(value: str) -> str:
    if not value.startswith(QR_PREFIX):
        raise ServiceError(
            "INVALID_QR_FORMAT", "This is not a SAULI retrieval QR.", 400
        )
    raw = value[len(QR_PREFIX) :]
    if not TOKEN_PATTERN.fullmatch(raw):
        raise ServiceError("INVALID_QR_FORMAT", "This retrieval QR is malformed.", 400)
    return raw
