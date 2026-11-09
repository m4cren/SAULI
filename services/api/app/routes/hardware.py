"""Device-scoped hardware telemetry and a public, sanitized read-only view."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.auth.dependencies import get_admin_user
from app.auth.kiosk import get_device, get_kiosk_session
from app.core.errors import ServiceError
from app.schemas.auth import UserResponse

router = APIRouter(prefix="/api/hardware", tags=["hardware"])
Device = Annotated[dict, Depends(get_device)]
Kiosk = Annotated[dict, Depends(get_kiosk_session)]
Admin = Annotated[UserResponse, Depends(get_admin_user)]


class DoorState(BaseModel):
    model_config = ConfigDict(extra="ignore")
    raw_level: Literal[0, 1] | None = None
    door: Literal["open", "closed", "unknown"] = "unknown"


class PiState(BaseModel):
    model_config = ConfigDict(extra="ignore")
    mode: Literal["real"]
    doors: dict[Literal["medium", "pocket"], DoorState]
    outputs: dict[Literal["main_light", "buzzer", "medium_solenoid", "pocket_solenoid", "pocket_light_gate", "medium_light_gate"], bool]
    lock_feedback: Literal["unavailable"] = "unavailable"


class SlotReading(BaseModel):
    model_config = ConfigDict(extra="ignore")
    code: str = Field(pattern=r"^(P-0[1-8]|M-0[1-4])$")
    ready: bool = False
    raw: int | None = None
    grams: float | None = None
    present: bool | None = None
    calibrated: bool = False
    light_command: bool = False
    fault: str | None = Field(default=None, max_length=40)


class Telemetry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    v: Literal[1]
    type: Literal["telemetry"]
    seq: int = Field(ge=0)
    uptime_ms: int = Field(ge=0)
    slots: list[SlotReading] = Field(max_length=12)


class EspState(BaseModel):
    model_config = ConfigDict(extra="ignore")
    connection: Literal["online", "stale", "offline"]
    frame_errors: int = Field(default=0, ge=0)
    error: str | None = Field(default=None, max_length=40)
    telemetry: Telemetry | None = None


class HardwareEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    at: datetime
    kind: Literal[
        "esp_hello", "esp_disconnected", "backend_unavailable",
        "command_accepted", "command_completed", "command_rejected", "command_failed",
        "output_activated", "output_deactivated", "workflow_door_opened",
        "workflow_door_closed", "workflow_open_timeout", "workflow_close_timeout",
        "medium_door_open", "medium_door_closed",
        "pocket_door_open", "pocket_door_closed",
    ]
    command_id: UUID | None = None


class DoorWorkflowState(BaseModel):
    model_config = ConfigDict(extra="ignore")
    command_id: UUID | None = None
    door: Literal["medium", "pocket"] | None = None
    phase: Literal["idle", "requested", "pulsing", "awaiting_open",
                   "awaiting_close", "completed", "fault"] = "idle"
    fault: Literal["door_open_timeout", "door_close_timeout", "hardware_failure"] | None = None


class HardwareSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")
    sequence: int | None = Field(default=None, ge=0)
    observed_at: datetime | None = None
    recorded_at: datetime | None = None
    pi: PiState
    esp: EspState
    events: list[HardwareEvent] = Field(default_factory=list, max_length=64)
    door_workflow: DoorWorkflowState = Field(default_factory=DoorWorkflowState)


class Heartbeat(BaseModel):
    model_config = ConfigDict(extra="forbid")
    snapshot: HardwareSnapshot


class Ack(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    status: Literal["acked", "failed"]
    code: str = Field(pattern=r"^[a-z0-9_]{1,40}$")


class TestCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_id: UUID
    action: Literal["pulse_pocket", "pulse_medium"]


class PresenceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    boot_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,40}$")
    seq: int = Field(ge=1)
    slot: str = Field(pattern=r"^(P-0[1-8]|M-0[1-4])$")
    kind: Literal["SENSOR_SNAPSHOT", "ITEM_PRESENT", "ITEM_REMOVED"]
    present: bool


class CaptureLightRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


@router.post("/heartbeat")
async def heartbeat(request: Request, payload: Heartbeat, device: Device):
    await request.app.state.kiosks.hardware_heartbeat(
        device, payload.snapshot.model_dump(mode="json"))
    commands = await request.app.state.kiosks.claim_hardware_commands(device)
    guidance = await request.app.state.kiosks.hardware_guidance(device)
    return {"device_id": device["id"], "commands": commands, "guidance": guidance}


@router.post("/presence")
async def presence(request: Request, payload: PresenceEvent, device: Device):
    if payload.kind == "ITEM_PRESENT" and not payload.present or payload.kind == "ITEM_REMOVED" and payload.present:
        raise ServiceError("INVALID_SENSOR_EVENT", "The sensor event is inconsistent.", 422)
    result = await request.app.state.kiosks.apply_hardware_presence(device, payload.model_dump())
    if result.get("error"):
        raise ServiceError("SENSOR_EVENT_REJECTED", "The sensor event could not be recorded.", 422)
    return result


@router.get("/workflow")
async def workflow(request: Request, kiosk: Kiosk, item_id: UUID | None = None,
                   session_id: UUID | None = None):
    if (item_id is None) == (session_id is None):
        raise ServiceError("INVALID_WORKFLOW", "Select one active workflow.", 422)
    return await request.app.state.kiosks.hardware_workflow(
        kiosk, item_id=str(item_id) if item_id else None,
        session_id=str(session_id) if session_id else None)


@router.post("/capture-light", status_code=202)
async def capture_light(request: Request, payload: CaptureLightRequest, kiosk: Kiosk):
    return await request.app.state.kiosks.enqueue_capture_light(kiosk, payload.enabled)


@router.post("/ack")
async def acknowledge(request: Request, payload: Ack, device: Device):
    return {"ok": await request.app.state.kiosks.ack_hardware_command(
        device, str(payload.id), payload.status, payload.code)}


@router.get("/public")
async def public_status(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return await request.app.state.kiosks.public_hardware_status()


@router.post("/admin/test-command", status_code=201)
async def test_command(request: Request, payload: TestCommand, _admin: Admin):
    if not request.app.state.settings.hardware_test_enabled:
        raise ServiceError("HARDWARE_TEST_DISABLED", "Hardware test commands are disabled.", 403)
    return await request.app.state.kiosks.enqueue_hardware_test(
        str(payload.device_id), payload.action)
