"""Resolve kiosk identities from opaque server-held credentials."""

from typing import Annotated

from fastapi import Depends, Header, Request

from app.core.errors import ServiceError


async def get_kiosk_session(
    request: Request, x_kiosk_session: Annotated[str | None, Header()] = None
) -> dict:
    device = await request.app.state.kiosks.browser_session(x_kiosk_session)
    if device is None:
        raise ServiceError("KIOSK_ACCESS_DENIED", "This kiosk is not registered or its session has expired.", 403)
    return device


async def get_device(
    request: Request, authorization: Annotated[str | None, Header()] = None
) -> dict:
    credential = authorization.removeprefix("Device ") if authorization and authorization.startswith("Device ") else None
    device = await request.app.state.kiosks.device_from_credential(credential)
    if device is None:
        raise ServiceError("DEVICE_ACCESS_DENIED", "Device access was denied.", 403)
    return device
