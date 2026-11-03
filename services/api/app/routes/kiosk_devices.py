"""Device enrollment and short-lived browser handoff endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from app.auth.kiosk import get_device, get_kiosk_session

router = APIRouter(prefix="/api/kiosk-devices", tags=["kiosk-devices"])
Device = Annotated[dict, Depends(get_device)]
Kiosk = Annotated[dict, Depends(get_kiosk_session)]


class Enrollment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_code: str = Field(min_length=1, max_length=100)
    pairing_code: str = Field(min_length=50, max_length=128)


class Bootstrap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bootstrap_code: str = Field(min_length=50, max_length=128)


class Heartbeat(BaseModel):
    controller_version: str | None = Field(default=None, max_length=80)


@router.post("/enroll")
async def enroll(request: Request, payload: Enrollment):
    client_host = request.client.host if request.client else "unknown"
    await request.app.state.kiosks.check_rate_limit("enroll_ip", client_host, 20)
    await request.app.state.kiosks.check_rate_limit("enroll_device", payload.device_code, 5)
    return await request.app.state.kiosks.enroll(payload.device_code, payload.pairing_code)


@router.post("/browser-bootstrap")
async def browser_bootstrap(request: Request, device: Device):
    return await request.app.state.kiosks.bootstrap(device["id"])


@router.post("/browser-redeem")
async def browser_redeem(request: Request, payload: Bootstrap):
    client_host = request.client.host if request.client else "unknown"
    await request.app.state.kiosks.check_rate_limit("redeem_ip", client_host, 30)
    return await request.app.state.kiosks.redeem_bootstrap(payload.bootstrap_code)


@router.get("/session")
async def session(kiosk: Kiosk):
    return {"device_id": kiosk["id"], "unit_id": kiosk["unit_id"],
            "unit_code": kiosk["unit"]["unit_code"], "unit_name": kiosk["unit"]["display_name"]}


@router.post("/heartbeat")
async def heartbeat(request: Request, payload: Heartbeat, device: Device):
    await request.app.state.kiosks.heartbeat(device, payload.controller_version)
    return {"ok": True}


@router.post("/rotate")
async def rotate(request: Request, device: Device):
    credential = request.headers["Authorization"].removeprefix("Device ")
    return await request.app.state.kiosks.rotate(device, credential)
