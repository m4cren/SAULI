"""Public location discovery and administrator fleet controls."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from app.auth.dependencies import get_admin_user
from app.core.errors import ServiceError
from app.schemas.auth import UserResponse

router = APIRouter(prefix="/api/units", tags=["units"])
Admin = Annotated[UserResponse, Depends(get_admin_user)]


class UnitInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    unit_code: str = Field(pattern=r"^SAULI-[A-Z0-9-]+$", max_length=80)
    display_name: str = Field(min_length=1, max_length=120)
    campus_code: str = Field(min_length=1, max_length=80)
    campus_name: str = Field(min_length=1, max_length=160)
    building_name: str = Field(min_length=1, max_length=160)
    floor: str | None = Field(default=None, max_length=80)
    location_description: str | None = Field(default=None, max_length=300)


class UnitStatusInput(BaseModel):
    status: Literal["provisioning", "active", "maintenance", "inactive", "retired"]


class UnitEditInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=1, max_length=120)
    campus_code: str = Field(min_length=1, max_length=80)
    campus_name: str = Field(min_length=1, max_length=160)
    building_name: str = Field(min_length=1, max_length=160)
    floor: str | None = Field(default=None, max_length=80)
    location_description: str | None = Field(default=None, max_length=300)


class DeviceInput(BaseModel):
    device_code: str = Field(pattern=r"^[A-Z0-9-]+$", max_length=100)
    hostname: str | None = Field(default=None, max_length=160)
    hardware_type: str = Field(min_length=1, max_length=160)


@router.get("/locations")
async def locations(request: Request):
    return await request.app.state.kiosks.locations()


@router.get("/admin/fleet")
async def fleet(request: Request, _admin: Admin):
    units = await request.app.state.kiosks.units()
    devices = await request.app.state.kiosks.devices()
    slots = await request.app.state.items.list_slots()
    for unit in units:
        own = [slot for slot in slots if slot.get("unit_id") == unit["id"] and slot.get("is_active")]
        unit["capacity"] = {"total": len(own), "available": sum(s["status"] == "available" for s in own),
            "reserved": sum(s["status"] == "reserved" for s in own),
            "occupied": sum(s["status"] == "occupied" for s in own),
            "out_of_service": sum(s["status"] == "out_of_service" for s in own)}
        unit["devices"] = [device for device in devices if device["unit_id"] == unit["id"]]
    return units


@router.post("/admin", status_code=201)
async def create_unit(request: Request, payload: UnitInput, _admin: Admin):
    return await request.app.state.kiosks.register_unit(payload.model_dump(mode="json"))


@router.put("/admin/{unit_id}")
async def edit_unit(request: Request, unit_id: UUID, payload: UnitEditInput, _admin: Admin):
    row = await request.app.state.kiosks.edit_unit(unit_id, payload.model_dump(mode="json"))
    if row is None:
        raise ServiceError("UNIT_NOT_FOUND", "Unit not found.", 404)
    return row


@router.patch("/admin/{unit_id}/status")
async def set_unit_status(request: Request, unit_id: UUID, payload: UnitStatusInput, _admin: Admin):
    row = await request.app.state.kiosks.set_unit_status(unit_id, payload.status)
    if row is None:
        raise ServiceError("UNIT_NOT_FOUND", "Unit not found.", 404)
    return row


@router.post("/admin/{unit_id}/devices", status_code=201)
async def add_device(request: Request, unit_id: UUID, payload: DeviceInput, _admin: Admin):
    if not any(unit["id"] == str(unit_id) for unit in await request.app.state.kiosks.units()):
        raise ServiceError("UNIT_NOT_FOUND", "Unit not found.", 404)
    return await request.app.state.kiosks.register_device(unit_id, payload.device_code,
        payload.hostname, payload.hardware_type)


@router.post("/admin/devices/{device_id}/approve-pairing")
async def approve_pairing(request: Request, device_id: UUID, admin: Admin):
    # Admin sees this one-time code only in this response, then transfers it to the Pi.
    return await request.app.state.kiosks.approve_pairing(device_id, UUID(admin.id))


@router.post("/admin/devices/{device_id}/revoke")
async def revoke_device(request: Request, device_id: UUID, admin: Admin):
    if not await request.app.state.kiosks.revoke(device_id, UUID(admin.id)):
        raise ServiceError("DEVICE_NOT_FOUND", "Device not found.", 404)
    return {"revoked": True}
