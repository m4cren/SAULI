"""Loopback diagnostics and outbound device telemetry, separate from browser launch."""

import argparse
import asyncio
import base64
import binascii
import hashlib
import hmac
import json
import logging
import os
import re
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sauli_pi.communication.backend_client import DeviceApiError, request_json
from sauli_pi.communication.esp32_serial import EspLink
from sauli_pi.config import Config, read_credential
from sauli_pi.hardware.controller import GPIOController
from sauli_pi.workflows.door import DoorWorkflow

LOG = logging.getLogger("sauli.hardware")
PRESENCE_SLOTS = {f"P-{number:02d}" for number in range(1, 9)} | {
    f"M-{number:02d}" for number in range(1, 5)}


class ExpectedSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^(P-0[1-8]|M-0[1-4])$")
    present: bool


class SimulatedPresence(BaseModel):
    """Operator-only logical switch change; no physical GPIO or ESP writes."""
    model_config = ConfigDict(extra="forbid")
    workflow_id: UUID
    assigned_slot: str = Field(pattern=r"^(P-0[1-8]|M-0[1-4])$")
    slot: str = Field(pattern=r"^(P-0[1-8]|M-0[1-4])$")
    action: Literal["target", "disturb", "restore", "undo_target"]


class DirectCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    device_id: UUID
    action: Literal["pulse_pocket", "pulse_medium", "capture_light_on", "capture_light_off"]
    expires_at: datetime
    transport: Literal["direct"]
    assigned_slot: str | None = Field(default=None, pattern=r"^(P-0[1-8]|M-0[1-4])$")
    expected_slots: list[ExpectedSlot] | None = Field(default=None, max_length=12)
    # Unlocks require this signed capability. Authenticated capture-light
    # commands are not door operations and remain backward compatible.
    grant: str | None = Field(default=None, min_length=80, max_length=8192)


def configure_logging() -> None:
    """Send controller events to stderr, which systemd captures in the journal."""
    LOG.setLevel(logging.INFO)
    if not LOG.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        LOG.addHandler(handler)
    LOG.propagate = False


def log_event(event: str, **fields: object) -> None:
    """Only call with explicitly selected, non-secret fields."""
    LOG.info("%s", json.dumps({"event": event, **fields}, sort_keys=True, separators=(",", ":")))


def valid_presence_event(event: dict) -> bool:
    """Match FastAPI's presence contract before an event enters the retry queue."""
    event_id = event.get("event_id")
    boot_id = event.get("boot_id")
    kind = event.get("kind")
    present = event.get("present")
    return (
        isinstance(event_id, str) and re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", event_id) is not None
        and isinstance(boot_id, str) and re.fullmatch(r"[a-zA-Z0-9_-]{1,40}", boot_id) is not None
        and type(event.get("seq")) is int and event["seq"] >= 1
        and isinstance(event.get("slot"), str) and event["slot"] in PRESENCE_SLOTS
        and isinstance(kind, str) and kind in {"SENSOR_SNAPSHOT", "ITEM_PRESENT", "ITEM_REMOVED"}
        and isinstance(present, bool)
        and (kind == "SENSOR_SNAPSHOT" or present == (kind == "ITEM_PRESENT"))
    )


def load_hardware(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("mode") not in ("real", "simulation"):
        raise ValueError("Hardware mode must be explicitly real or simulation")
    value["sensor_simulation_enabled"] = value.get("sensor_simulation_enabled", False)
    if type(value["sensor_simulation_enabled"]) is not bool:
        raise ValueError("sensor_simulation_enabled must be true or false")
    if value["sensor_simulation_enabled"] and (value["mode"] != "real"
                                                or value.get("command_transport", "direct") != "direct"):
        raise ValueError("Sensor simulation requires real hardware in direct transport mode")
    value["command_transport"] = value.get("command_transport", "direct")
    if value["command_transport"] not in {"direct", "legacy"}:
        raise ValueError("command_transport must be direct or legacy")
    if value.get("enable_actuators") and not value.get("output_polarity_verified"):
        raise ValueError("Verify output polarity before enabling actuators")
    test_channel = value.get("solenoid_led_test_channel")
    if test_channel not in (None, "pocket", "medium"):
        raise ValueError("solenoid_led_test_channel must be pocket, medium, or null")
    for key, default, minimum, maximum in (
        ("gpio_sample_seconds", 0.05, 0.02, 0.2),
        ("telemetry_interval_seconds", 0.5, 0.25, 30),
        ("telemetry_min_gap_seconds", 0.15, 0.1, 5),
        ("capture_light_max_seconds", 12, 3, 30),
        ("solenoid_max_hold_seconds", 300, 10, 900),
        ("door_open_timeout_seconds", 60, 5, 300),
        ("door_close_timeout_seconds", 120, 5, 600),
    ):
        try:
            number = float(value.get(key, default))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid {key}") from exc
        if not minimum <= number <= maximum:
            raise ValueError(f"{key} must be between {minimum} and {maximum}")
        value[key] = number
    for key in ("door_open_timeout_policy", "door_close_timeout_policy"):
        value[key] = value.get(key, "continue_waiting")
        if value[key] not in {"continue_waiting", "abort"}:
            raise ValueError(f"{key} must be continue_waiting or abort")
    if value["telemetry_min_gap_seconds"] > value["telemetry_interval_seconds"]:
        raise ValueError("telemetry_min_gap_seconds cannot exceed telemetry_interval_seconds")
    if value.get("mode") == "real":
        try:
            value["device_id"] = str(UUID(value["device_id"]))
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError("Real hardware requires the enrolled device UUID") from exc
        active_high = value.get("output_active_high") or {}
        if (active_high.get("pocket_solenoid") is not True
                or active_high.get("medium_solenoid") is not True):
            raise ValueError("Pocket and medium solenoids must be configured active-HIGH")
        if value["command_transport"] == "direct":
            token = value.get("direct_api_token")
            if not isinstance(token, str) or len(token) < 32:
                raise ValueError("Direct hardware transport requires a 32+ character API token")
            value.setdefault("direct_bind_host", "127.0.0.1")
            value.setdefault("direct_port", 8765)
            value.setdefault("direct_replay_file", "/var/lib/sauli/hardware-command-replay.json")
            value.setdefault("direct_incident_queue_file",
                             "/var/lib/sauli/hardware-incident-queue.json")
            value.setdefault("direct_completion_queue_file",
                             "/var/lib/sauli/hardware-completion-queue.json")
    return value


class HardwareService:
    def __init__(self, config: Config, settings: dict):
        self.config = config
        self.settings = settings
        self.gpio = GPIOController(
            simulation=settings["mode"] == "simulation",
            closed_level=settings["reed_closed_level"],
            active_high=settings["output_active_high"],
            max_hold_seconds=float(settings.get("solenoid_max_hold_seconds", 300)),
            allow_outputs=bool(settings.get("output_polarity_verified", False)))
        self.esp = EspLink(settings.get("esp_port", "/dev/serial0"),
                           int(settings.get("esp_baud", 115200)))
        self.backend = "unknown"
        self.events: list[dict] = []
        self._seen: set[str] = set()
        self._recent_commands: deque[str] = deque(maxlen=256)
        self._command_lock = asyncio.Lock()
        replay_name = settings.get("direct_replay_file")
        self._replay_file = Path(replay_name) if replay_name else None
        self._command_results: dict[str, dict] = {}
        self._load_replay_results()
        self.credential: str | None = None
        self.ready = False
        self.fault: str | None = None
        self._ping_seq = 0
        self._last_door_states: dict[str, str] = {}
        self._last_raw_levels: dict[str, int | None] = {}
        self._door_state_dirty = True
        self._last_door_state_sent = 0.0
        self._sequence = 0
        self._observed_at: str | None = None
        self._publish_signal = asyncio.Event()
        self._pending_acks: deque[dict] = deque()
        self._pending_presence: dict[str, dict] = {}
        self._direct_events: deque[dict] = deque(maxlen=128)
        self._security_events: deque[dict] = deque(maxlen=64)
        self._direct_event_signal = asyncio.Event()
        self._completion_snapshot_pending = False
        self._boot_recovery_snapshot_pending = (
            settings.get("command_transport", "legacy") == "direct")
        self._presence_upload_failed = False
        self._last_unlock: dict | None = None
        incident_name = settings.get("direct_incident_queue_file")
        self._incident_queue_file = Path(incident_name) if incident_name else None
        completion_name = settings.get("direct_completion_queue_file")
        self._completion_queue_file = Path(completion_name) if completion_name else None
        self._local_operation: dict | None = None
        self._local_present: dict[str, bool] = {}
        # An explicit operator test overlay. Never active without a config opt-in.
        # Cleared at every new/synchronized workflow; does not touch ESP inputs.
        self._simulated_presence: dict[str, bool] = {}
        # Test-only wrong-lift incidents for empty alternative compartments.
        # These are warnings, NOT fabricated item-presence readings.
        self._simulated_wrong_lifts: set[str] = set()
        self._local_violations: dict[str, str] = {}
        self._local_provisional_ever = False
        self._local_provisional = False
        self._awaiting_backend_finalization = False
        self._finalization_error: str | None = None
        self._load_security_events()
        self._backend_guidance: dict[str, str] | None = None
        self._backend_buzzer = False
        self._last_guidance: dict | None = None
        self._last_guidance_sent = 0.0
        self._last_esp_connection = False
        self._esp_online = False
        self._logged_presence_ids: deque[str] = deque(maxlen=256)
        self._logged_presence_set: set[str] = set()
        self._buzzer_started: float | None = None
        self._capture_light_deadline: float | None = None
        self._sample_seconds = float(settings.get("gpio_sample_seconds", 0.05))
        self._telemetry_seconds = float(settings.get("telemetry_interval_seconds", 0.5))
        self._min_gap_seconds = float(settings.get("telemetry_min_gap_seconds", 0.15))
        self.door_workflow = DoorWorkflow(
            open_timeout_seconds=float(settings.get("door_open_timeout_seconds", 60)),
            close_timeout_seconds=float(settings.get("door_close_timeout_seconds", 120)),
            open_timeout_policy=settings.get("door_open_timeout_policy", "continue_waiting"),
            close_timeout_policy=settings.get("door_close_timeout_policy", "continue_waiting"))
        self._load_direct_events()
        self.task: asyncio.Task | None = None

    @property
    def direct_mode(self) -> bool:
        return self.settings.get("command_transport", "legacy") == "direct"

    def _load_replay_results(self) -> None:
        if self._replay_file is None:
            return
        try:
            value = json.loads(self._replay_file.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                return
            for command_id, result in list(value.items())[-256:]:
                UUID(command_id)
                if isinstance(result, dict) and result.get("id") == command_id:
                    self._command_results[command_id] = result
        except (OSError, ValueError, TypeError):
            # A missing or invalid cache fails closed only for commands that the
            # current process has seen; command expiry remains the outer bound.
            self._command_results = {}

    def _save_replay_results(self) -> bool:
        if self._replay_file is None:
            return True
        try:
            self._replay_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            pending = self._replay_file.with_suffix(self._replay_file.suffix + ".pending")
            pending.write_text(json.dumps(self._command_results, separators=(",", ":")),
                               encoding="utf-8")
            os.chmod(pending, 0o600)
            os.replace(pending, self._replay_file)
            return True
        except OSError:
            LOG.exception("Could not persist direct-command replay cache")
            return False

    def _load_security_events(self) -> None:
        if self._incident_queue_file is None:
            return
        try:
            rows = json.loads(self._incident_queue_file.read_text(encoding="utf-8"))
            if isinstance(rows, list):
                for row in rows[-64:]:
                    if isinstance(row, dict) and isinstance(row.get("snapshot"), dict):
                        self._security_events.append(row)
                if self._security_events:
                    self._direct_event_signal.set()
        except (OSError, ValueError, TypeError):
            self._security_events.clear()

    def _save_security_events(self) -> bool:
        if self._incident_queue_file is None:
            return True
        try:
            self._incident_queue_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            pending = self._incident_queue_file.with_suffix(
                self._incident_queue_file.suffix + ".pending")
            pending.write_text(json.dumps(list(self._security_events),
                                          separators=(",", ":")), encoding="utf-8")
            os.chmod(pending, 0o600)
            os.replace(pending, self._incident_queue_file)
            return True
        except OSError:
            LOG.exception("Could not persist direct security-event queue")
            return False

    def _load_direct_events(self) -> None:
        if self._completion_queue_file is None:
            return
        try:
            rows = json.loads(self._completion_queue_file.read_text(encoding="utf-8"))
            if not isinstance(rows, list):
                return
            # A command has at most one immutable physical completion. Historical
            # queue files can contain duplicates from repeated reed transitions.
            seen_commands: set[str] = set()
            for row in rows[-32:]:
                snapshot = row.get("snapshot") if isinstance(row, dict) else None
                completion = snapshot.get("local_completion") if isinstance(snapshot, dict) else None
                if (isinstance(completion, dict) and completion.get("verified") is True
                        and isinstance(completion.get("command_id"), str)):
                    command_id = completion["command_id"]
                    if command_id in seen_commands:
                        LOG.warning("Ignoring duplicate persisted completion for command %s", command_id)
                        continue
                    seen_commands.add(command_id)
                    self._direct_events.append({"presence": None, "snapshot": snapshot,
                                                "durable": True})
            if self._direct_events:
                latest = self._direct_events[-1]["snapshot"]
                completion = latest["local_completion"]
                operation = completion.get("operation")
                expected = completion.get("expected_slots")
                present = completion.get("observed_slots")
                if (operation in {"deposit", "retrieval"}
                        and isinstance(expected, dict) and set(expected) == PRESENCE_SLOTS
                        and isinstance(present, dict) and set(present) == PRESENCE_SLOTS):
                    self._local_operation = {
                        "command_id": completion["command_id"],
                        "workflow_id": completion.get("workflow_id"),
                        "assigned_slot": completion.get("assigned_slot"),
                        "kind": operation,
                        "expected": expected,
                        "target_present": operation == "deposit",
                        "door": completion.get("door"),
                        "phase": "locally_completed",
                        "opened_at": completion.get("opened_at"),
                        "closed_at": completion.get("closed_at"),
                        "close_seq": completion.get("telemetry_sequence"),
                        "close_boot_id": completion.get("esp_boot_id"),
                    }
                    self._local_present = present
                    self._awaiting_backend_finalization = True
                    self._finalization_error = "SYNCHRONIZATION_PENDING"
                    self._last_unlock = latest.get("last_unlock")
                self._direct_event_signal.set()
        except (OSError, ValueError, TypeError, KeyError):
            self._direct_events.clear()

    def _save_direct_events(self) -> bool:
        if self._completion_queue_file is None:
            return True
        durable = [row for row in self._direct_events if row.get("durable") is True]
        try:
            self._completion_queue_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            pending = self._completion_queue_file.with_suffix(
                self._completion_queue_file.suffix + ".pending")
            pending.write_text(json.dumps(durable[-32:], separators=(",", ":")),
                               encoding="utf-8")
            os.chmod(pending, 0o600)
            os.replace(pending, self._completion_queue_file)
            return True
        except OSError:
            LOG.exception("Could not persist direct completion-event queue")
            return False

    def _queue_direct_event(self, snapshot: dict, *, durable: bool = False) -> bool:
        if durable:
            completion = snapshot.get("local_completion") or {}
            command_id = completion.get("command_id")
            if not isinstance(command_id, str):
                return False
            # Never create a second completion for the same physical operation.
            if any((entry.get("snapshot", {}).get("local_completion") or {}).get(
                    "command_id") == command_id for entry in self._direct_events
                    if entry.get("durable") is True):
                return True
        if len(self._direct_events) == self._direct_events.maxlen:
            if not durable:
                self.fault = "workflow_event_queue_full"
                return False
            # A verified completion must not be discarded behind transient
            # open/close snapshots; the completion itself contains their proof.
            removable = next((index for index, row in enumerate(self._direct_events)
                              if row.get("durable") is not True), None)
            if removable is None:
                self.fault = "completion_event_queue_full"
                return False
            del self._direct_events[removable]
        self._direct_events.append({"presence": None, "snapshot": snapshot,
                                    "durable": durable})
        if durable and not self._save_direct_events():
            self._direct_events.pop()
            self.fault = "completion_event_storage_unavailable"
            return False
        self._direct_event_signal.set()
        return True

    async def execute_direct_command(self, row: dict) -> dict:
        command_id = str(row.get("id", ""))
        async with self._command_lock:
            cached = self._command_results.get(command_id)
            if cached is not None:
                log_event("command_replayed", command_id=command_id,
                          status=cached.get("status"))
                return cached.copy()
            # Persist a fail-closed reservation before touching an output. A
            # process/power loss during the pulse can then never replay it.
            reservation = {"id": command_id, "status": "failed",
                           "code": "replay_state_unknown"}
            self._command_results[command_id] = reservation
            if not self._save_replay_results():
                result = {"id": command_id, "status": "failed",
                          "code": "replay_storage_unavailable"}
                self._command_results[command_id] = result
                return result
            result = await self.handle_command(row)
            self._command_results[command_id] = result.copy()
            while len(self._command_results) > 256:
                self._command_results.pop(next(iter(self._command_results)))
            self._save_replay_results()
            return result

    @staticmethod
    def _grant_decode(value: str) -> bytes:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

    def _validate_unlock_grant(self, row: dict, door: str) -> dict:
        try:
            payload, supplied = row["grant"].split(".", 1)
            expected = base64.urlsafe_b64encode(hmac.new(
                self.settings["direct_api_token"].encode("utf-8"),
                payload.encode("ascii"), hashlib.sha256).digest()
            ).rstrip(b"=").decode("ascii")
            if not hmac.compare_digest(supplied, expected):
                raise ValueError("invalid_unlock_grant")
            claims = json.loads(self._grant_decode(payload))
            UUID(claims["jti"])
            UUID(claims["device_id"])
            UUID(claims["unit_id"])
            UUID(claims["workflow_id"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, binascii.Error) as exc:
            raise ValueError("invalid_unlock_grant") from exc
        now = int(datetime.now(UTC).timestamp())
        if (claims.get("v") != 1 or type(claims.get("iat")) is not int
                or type(claims.get("exp")) is not int):
            raise ValueError("invalid_unlock_grant")
        if claims["exp"] <= now or claims["iat"] > now + 5:
            raise ValueError("unlock_grant_expired")
        expected_rows = row.get("expected_slots")
        assigned = row.get("assigned_slot")
        operation = "retrieval" if next(
            (entry["present"] for entry in expected_rows or []
             if entry.get("code") == assigned), False) else "deposit"
        expires = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
        if (claims["jti"] != str(row.get("id"))
                or claims["device_id"] != str(self.settings.get("device_id"))
                or claims.get("door") != door
                or claims.get("slot") != assigned
                or claims.get("operation") != operation
                or claims.get("expected_slots") != expected_rows
                or abs(expires.timestamp() - claims["exp"]) > 1):
            raise ValueError("unlock_grant_claim_mismatch")
        return claims

    def _validate_direct_unlock(self, row: dict, door: str) -> None:
        if not self.ready:
            raise ValueError("hardware_not_ready")
        expected_rows = row.get("expected_slots")
        assigned_slot = row.get("assigned_slot")
        if (not isinstance(assigned_slot, str)
                or (door == "pocket" and not assigned_slot.startswith("P-"))
                or (door == "medium" and not assigned_slot.startswith("M-"))):
            raise ValueError("hardware_not_ready")
        if not isinstance(expected_rows, list) or len(expected_rows) != 12:
            raise ValueError("hardware_not_ready")
        expected = {entry.get("code"): entry.get("present") for entry in expected_rows
                    if isinstance(entry, dict)}
        if set(expected) != PRESENCE_SLOTS or any(type(value) is not bool
                                                   for value in expected.values()):
            raise ValueError("hardware_not_ready")
        esp = self.esp.snapshot()
        telemetry = esp.get("telemetry") or {}
        readings = telemetry.get("slots")
        try:
            observed_at = datetime.fromisoformat(
                str(esp["telemetry_at"]).replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError):
            raise ValueError("hardware_not_ready") from None
        if (esp.get("connection") != "online" or not esp.get("boot_id")
                or abs((datetime.now(UTC) - observed_at).total_seconds()) > 5
                or not isinstance(readings, list) or len(readings) != 12):
            raise ValueError("hardware_not_ready")
        observed = {entry.get("code"): entry for entry in readings if isinstance(entry, dict)}
        if set(observed) != PRESENCE_SLOTS:
            raise ValueError("hardware_not_ready")
        for code, entry in observed.items():
            if (entry.get("ready") is not True or entry.get("fault") not in {None, ""}
                    or type(entry.get("present")) is not bool):
                raise ValueError("hardware_not_ready")
            if (not self.settings.get("sensor_simulation_enabled", False)
                    and entry["present"] is not expected[code]):
                raise ValueError("sensor_state_mismatch")
        door_state = self.gpio.doors[door].snapshot()
        if door_state["door"] != "closed" or door_state["raw_level"] is None:
            raise ValueError("door_not_closed")
        if any(self.gpio.outputs[f"{name}_solenoid"] for name in ("pocket", "medium")):
            raise ValueError("hardware_not_ready")
        if self.door_workflow.phase not in {"idle", "completed", "fault"}:
            raise ValueError("door_workflow_busy")

    def _start_local_operation(self, row: dict, claims: dict | None = None) -> None:
        expected = {entry["code"]: entry["present"] for entry in row["expected_slots"]}
        assigned = row["assigned_slot"]
        initial_present = expected[assigned]
        self._local_operation = {
            "command_id": str(row["id"]),
            "workflow_id": claims.get("workflow_id") if claims else None,
            "assigned_slot": assigned,
            "kind": "retrieval" if initial_present else "deposit",
            "expected": expected,
            "target_present": not initial_present,
            "door": "pocket" if assigned.startswith("P-") else "medium",
            "phase": "authorized",
            "opened_at": None,
            "closed_at": None,
            "close_seq": None,
            "close_boot_id": None,
        }
        self._local_present = expected.copy()
        self._simulated_presence = (expected.copy()
            if self.settings.get("sensor_simulation_enabled", False) else {})
        self._simulated_wrong_lifts.clear()
        self._local_violations = {}
        self._local_provisional_ever = False
        self._local_provisional = False
        self._awaiting_backend_finalization = False
        self._finalization_error = None
        self._changed()

    def _local_warning_snapshot(self) -> dict:
        operation = self._local_operation
        return {
            "monitoring": operation is not None,
            "active": bool(self._local_violations),
            "command_id": operation["command_id"] if operation else None,
            "assigned_slot": operation["assigned_slot"] if operation else None,
            "operation": operation["kind"] if operation else None,
            "workflow_id": operation.get("workflow_id") if operation else None,
            "local_phase": operation.get("phase") if operation else "idle",
            "locally_completed": bool(
                operation and operation.get("phase") in {"locally_completed", "synced"}),
            "sync_pending": bool(
                operation and operation.get("phase") == "locally_completed"),
            "provisional_success": self._local_provisional,
            "assigned_present": self._local_present.get(operation["assigned_slot"])
                if operation else None,
            "expected_present": operation["target_present"] if operation else None,
            "awaiting_finalization": self._awaiting_backend_finalization,
            "finalization_error": self._finalization_error,
            "violations": [
                {"slot": slot, "kind": kind}
                for slot, kind in sorted(self._local_violations.items())
            ],
        }

    def _queue_security_updates(self, updates: list[dict]) -> None:
        if not updates:
            return
        snapshot = self._direct_event_snapshot()
        snapshot["local_incident_updates"] = updates
        if len(self._security_events) == self._security_events.maxlen:
            # Never silently discard a durable correction/violation transition.
            self.fault = "security_event_queue_full"
            LOG.error("Direct security-event queue is full")
            return
        self._security_events.append({"presence": None, "snapshot": snapshot})
        self._save_security_events()
        self._direct_event_signal.set()

    def _recompute_local_security(self) -> bool:
        operation = self._local_operation
        if operation is None:
            return False
        previous = self._local_violations
        previous_provisional = self._local_provisional
        previous_phase = operation.get("phase")
        current: dict[str, str] = {}
        assigned = operation["assigned_slot"]
        target = operation["target_present"]
        assigned_present = self._local_present.get(assigned)
        if assigned_present is target:
            self._local_provisional = True
            self._local_provisional_ever = True
        else:
            self._local_provisional = False
            if self._local_provisional_ever and assigned_present is not None:
                current[assigned] = (
                    "wrong_removal" if operation["kind"] == "deposit"
                    else "wrong_placement")
        for slot, expected in operation["expected"].items():
            if slot == assigned or slot not in self._local_present:
                continue
            present = self._local_present[slot]
            if present != expected:
                current[slot] = "wrong_placement" if present else "wrong_removal"
        # Operator-only demo: an empty alternative slot cannot physically
        # produce a removal edge. Keep a synthetic incident until Restore so
        # Pi buzzer/SOS and backend warnings use the existing security path.
        # Never change expected occupancy or completion evidence for this test.
        if (self.settings.get("sensor_simulation_enabled", False)
                and operation["kind"] == "retrieval"):
            for slot in self._simulated_wrong_lifts:
                if slot != assigned and slot in operation["expected"]:
                    current[slot] = "wrong_removal"
        updates = [
            {"slot": slot, "kind": kind, "active": False}
            for slot, kind in previous.items()
            if current.get(slot) != kind
        ]
        updates.extend(
            {"slot": slot, "kind": kind, "active": True}
            for slot, kind in current.items()
            if previous.get(slot) != kind
        )
        violation_changed = current != previous
        self._local_violations = current
        door_open = operation["door"] in self.gpio.doors and (
            self.gpio.doors[operation["door"]].snapshot()["door"] == "open")
        if operation.get("phase") not in {"door_closed", "locally_completed", "synced"}:
            if self._local_provisional and not current and door_open:
                operation["phase"] = "item_verified"
            elif door_open:
                operation["phase"] = "door_open"
        changed = (violation_changed or self._local_provisional != previous_provisional
                   or operation.get("phase") != previous_phase)
        if changed:
            self._changed()
        if violation_changed:
            self._queue_security_updates(updates)
        return changed

    async def simulate_presence(self, payload: SimulatedPresence) -> dict:
        """Inject a test-only logical reading into the existing local workflow.

        An actual reed-open transition is mandatory. This cannot unlock a door,
        bypass warnings, close a door or directly finalize a transaction.
        """
        if not self.settings.get("sensor_simulation_enabled", False) or not self.direct_mode:
            raise HTTPException(status_code=404, detail="Sensor simulation disabled")
        operation = self._local_operation
        if (not self.ready or operation is None or
                operation.get("workflow_id") != str(payload.workflow_id) or
                operation["assigned_slot"] != payload.assigned_slot or
                operation.get("phase") in {"authorized", "unlocked", "door_closed",
                                           "locally_completed", "synced", "fault"} or
                self.gpio.doors[operation["door"]].snapshot()["door"] != "open"):
            raise HTTPException(status_code=409, detail="No matching open-door workflow")
        if (payload.slot not in operation["expected"] or
                payload.slot.startswith("P-") != operation["assigned_slot"].startswith("P-")):
            raise HTTPException(status_code=409, detail="Slot is outside the authorized door bank")
        if payload.action in {"target", "undo_target"}:
            if payload.slot != operation["assigned_slot"]:
                raise HTTPException(status_code=409, detail="Only the assigned slot may be targeted")
            present = (operation["target_present"] if payload.action == "target"
                       else operation["expected"][payload.slot])
        else:
            if payload.slot == operation["assigned_slot"]:
                raise HTTPException(status_code=409, detail="Select another slot for the incident")
            if payload.action == "disturb":
                existing = operation["expected"][payload.slot]
                if operation["kind"] == "deposit" and existing:
                    raise HTTPException(status_code=409,
                        detail="For wrong placement select an empty compartment")
                if operation["kind"] == "retrieval" and not existing:
                    # An empty cabinet can still demonstrate a wrong lift:
                    # trigger a test-only incident, never fake an occupied item.
                    self._simulated_wrong_lifts.add(payload.slot)
            else:  # Restore clears the demo-only incident, if any.
                self._simulated_wrong_lifts.discard(payload.slot)
            present = (not operation["expected"][payload.slot]
                       if payload.action == "disturb" and payload.slot not in self._simulated_wrong_lifts
                       else operation["expected"][payload.slot])
        self._simulated_presence[payload.slot] = present
        await self._observe_local_presence(payload.slot, present)
        # Always log each operator action distinctly, including no-op repeats.
        log_event("sensor_simulation", slot=payload.slot, action=payload.action,
                  present=present, workflow_id=str(payload.workflow_id),
                  source="operator_simulation")
        return {"ok": True, "slot": payload.slot, "present": present,
                "source": "operator_simulation",
                "warning": self._local_warning_snapshot()}

    def _simulated_telemetry(self, telemetry: dict) -> dict:
        if not self.settings.get("sensor_simulation_enabled", False) or not self._simulated_presence:
            return telemetry
        # Only the boolean decisions are simulated. ESP connection, sampling
        # freshness, boot ID, faults and the Pi reed remain genuine.
        copy = json.loads(json.dumps(telemetry))
        for entry in copy.get("slots", []):
            code = entry.get("code")
            if code in self._simulated_presence:
                entry["present"] = self._simulated_presence[code]
        return copy

    async def _observe_local_presence(self, slot: str, present: bool) -> None:
        if self._local_operation is None or slot not in self._local_operation["expected"]:
            return
        self._local_present[slot] = present
        changed = self._recompute_local_security()
        if changed:
            await self._refresh_guidance()

    async def _observe_local_telemetry(self, telemetry: dict) -> None:
        if self._local_operation is None:
            return
        readings = self._simulated_telemetry(telemetry).get("slots")
        if not isinstance(readings, list):
            return
        for reading in readings:
            if (isinstance(reading, dict) and reading.get("ready") is True
                    and type(reading.get("present")) is bool
                    and reading.get("code") in self._local_operation["expected"]):
                self._local_present[reading["code"]] = reading["present"]
        changed = self._recompute_local_security()
        if changed:
            await self._refresh_guidance()

    def _local_completion_evidence(self, telemetry: dict) -> tuple[dict | None, str | None]:
        operation = self._local_operation
        if operation is None or operation.get("phase") != "door_closed":
            return None, "LOCAL_WORKFLOW_NOT_CLOSED"
        door = operation["door"]
        door_state = self.gpio.doors[door].snapshot()
        if door_state["door"] != "closed" or door_state["raw_level"] is None:
            return None, "DOOR_NOT_CLOSED"
        boot_id = self.esp.boot_id
        sequence = telemetry.get("seq")
        if not isinstance(boot_id, str) or not boot_id or type(sequence) is not int:
            return None, "ESP_IDENTITY_REQUIRED"
        if (boot_id == operation.get("close_boot_id")
                and type(operation.get("close_seq")) is int
                and sequence <= operation["close_seq"]):
            return None, "POST_CLOSE_SEQUENCE_REQUIRED"
        readings = self._simulated_telemetry(telemetry).get("slots")
        if not isinstance(readings, list) or len(readings) != 12:
            return None, "SENSOR_DATA_INCOMPLETE"
        observed = {row.get("code"): row for row in readings if isinstance(row, dict)}
        if set(observed) != PRESENCE_SLOTS:
            return None, "SENSOR_DATA_INCOMPLETE"
        present: dict[str, bool] = {}
        for code, reading in observed.items():
            if (reading.get("ready") is not True or reading.get("fault") not in {None, ""}
                    or type(reading.get("present")) is not bool):
                return None, "SENSOR_DATA_INCOMPLETE"
            present[code] = reading["present"]
        self._local_present = present
        self._recompute_local_security()
        expected = operation["expected"].copy()
        expected[operation["assigned_slot"]] = operation["target_present"]
        if present != expected or self._local_violations or not self._local_provisional:
            return None, "LOCAL_SENSOR_STATE_INVALID"
        return {
            "verified": True,
            "command_id": operation["command_id"],
            "workflow_id": operation.get("workflow_id"),
            "operation": operation["kind"],
            "door": door,
            "assigned_slot": operation["assigned_slot"],
            "expected_slots": operation["expected"].copy(),
            "observed_slots": present.copy(),
            "opened_at": operation.get("opened_at"),
            "closed_at": operation.get("closed_at"),
            "verified_at": datetime.now(UTC).isoformat(),
            "esp_boot_id": boot_id,
            "telemetry_sequence": sequence,
            "sensor_source": ("operator_simulation"
                if self.settings.get("sensor_simulation_enabled", False) else "esp32_switch"),
        }, None

    async def _try_local_completion(self, telemetry: dict) -> bool:
        evidence, error = self._local_completion_evidence(telemetry)
        if evidence is None:
            self._finalization_error = error
            self._changed()
            await self._refresh_guidance(force=True)
            return False
        operation = self._local_operation
        assert operation is not None
        self._deactivate_workflow_solenoid(operation["door"], "locally_verified_closed")
        evidence["completed_at"] = datetime.now(UTC).isoformat()
        operation["phase"] = "locally_completed"
        self._awaiting_backend_finalization = True
        self._finalization_error = "SYNCHRONIZATION_PENDING"
        self._completion_snapshot_pending = False
        self._boot_recovery_snapshot_pending = False
        self._changed()
        snapshot = self._direct_event_snapshot()
        snapshot["local_completion"] = evidence
        # Supersede non-durable open/close progress snapshots: they can no
        # longer change an operation whose physical completion is immutable.
        self._direct_events = deque((row for row in self._direct_events
                                     if row.get("durable") is True), maxlen=128)
        if not self._queue_direct_event(snapshot, durable=True):
            self._finalization_error = "COMPLETION_PERSISTENCE_FAILED"
            self._changed()
            return False
        await self._refresh_guidance(force=True)
        return True

    async def _finish_local_operation(self) -> None:
        door = (self._local_operation or {}).get("door") or self.door_workflow.door
        if door:
            self._deactivate_workflow_solenoid(door, "database_synchronized")
        if self._local_operation is not None:
            self._local_operation["phase"] = "synced"
        self._local_operation = None
        self._local_present = {}
        self._simulated_presence = {}
        self._simulated_wrong_lifts.clear()
        self._local_violations = {}
        self._local_provisional = False
        self._local_provisional_ever = False
        self._awaiting_backend_finalization = False
        self._finalization_error = None
        self._changed()
        await self._refresh_guidance()

    def _deactivate_workflow_solenoid(self, door: str, reason: str) -> None:
        if not self.gpio.deactivate_solenoid(door):
            return
        command_id = self.door_workflow.command_id
        if self._last_unlock is not None and self._last_unlock.get("command_id") == command_id:
            self._last_unlock["deactivated_at"] = datetime.now(UTC).isoformat()
        self.event("output_deactivated", command_id)
        log_event("solenoid_hold", command_id=command_id, door=door,
                  gpio=GPIOController.OUTPUTS[f"{door}_solenoid"],
                  state="deactivated", reason=reason)

    def _abort_workflow(self, code: str) -> None:
        door = self.door_workflow.door
        if door:
            self._deactivate_workflow_solenoid(door, code)
        self.door_workflow.fail(code)
        self._awaiting_backend_finalization = False
        self._finalization_error = code.upper()
        if self._local_operation is not None:
            self._local_operation["phase"] = "fault"
        self._simulated_presence = {}
        self._simulated_wrong_lifts.clear()
        if self._last_unlock is not None:
            self._last_unlock["status"] = "failed"
            self._last_unlock["last_output_error"] = "hardware_failure"
        self.event("command_failed", self.door_workflow.command_id)
        self._changed()

    def event(self, kind: str, command_id: str | None = None) -> None:
        if kind == "esp_disconnected" and self._esp_online:
            self._esp_online = False
            log_event("esp_connection", state="disconnected", reason=self.esp.error or "connection_lost")
        entry = {"at": datetime.now(UTC).isoformat(), "kind": kind}
        if command_id:
            entry["command_id"] = command_id
        self.events = ([entry] + self.events)[:64]
        operation = self._local_operation
        if operation is not None:
            door = operation["door"]
            if (kind in {f"{door}_door_open", "workflow_door_opened"}
                    and operation.get("phase") not in {"locally_completed", "synced"}):
                operation["opened_at"] = operation.get("opened_at") or entry["at"]
                operation["closed_at"] = None
                operation["phase"] = (
                    "item_verified" if self._local_provisional
                    and not self._local_violations else "door_open")
                self._completion_snapshot_pending = False
                self._awaiting_backend_finalization = False
                self._finalization_error = None
            elif (kind in {f"{door}_door_closed", "workflow_door_closed"}
                  and operation.get("opened_at") is not None
                  and operation.get("phase") not in {"locally_completed", "synced"}):
                operation["closed_at"] = entry["at"]
                operation["phase"] = "door_closed"
                telemetry = self.esp.last_telemetry or {}
                operation["close_seq"] = telemetry.get("seq")
                operation["close_boot_id"] = self.esp.boot_id
                self._completion_snapshot_pending = True
                self._awaiting_backend_finalization = False
                self._finalization_error = "LOCAL_SENSOR_VERIFICATION_PENDING"
        if self.direct_mode and kind in {
            "workflow_door_opened", "workflow_door_closed",
            "workflow_open_timeout", "workflow_close_timeout",
        }:
            # Freeze the event-time view. In particular, the close event must
            # retain the pre-close telemetry sequence so a later ESP reading is
            # provably newer when the backend finalizes the transaction.
            self._queue_direct_event(self._direct_event_snapshot())
        self._changed()

    def _changed(self) -> None:
        self._sequence += 1
        self._observed_at = datetime.now(UTC).isoformat()
        self._publish_signal.set()

    def snapshot(self) -> dict:
        esp = (self.esp.snapshot() if self.settings["mode"] == "real" else
               {"connection": "simulated", "telemetry": None})
        if isinstance(esp.get("telemetry"), dict):
            esp["telemetry"] = self._simulated_telemetry(esp["telemetry"])
        return {"schema_version": 1, "unit_code": self.config.unit_code,
                "device_code": self.config.device_code,
                "recorded_at": datetime.now(UTC).isoformat(),
                "observed_at": self._observed_at, "sequence": self._sequence,
                "backend": self.backend, "pi": self.gpio.snapshot(),
                "esp": esp,
                "events": self.events[:64],
                "pending_presence_count": 0 if self.direct_mode else len(self._pending_presence),
                "last_unlock": self._last_unlock,
                "local_warning": self._local_warning_snapshot(),
                "door_workflow": self.door_workflow.snapshot(),
                "sensor_simulation_active": bool(self._simulated_presence)}

    def _direct_event_snapshot(self) -> dict:
        """Detach queued evidence from mutable ESP/event dictionaries."""
        return json.loads(json.dumps(self.snapshot()))

    def record_door_changes(self) -> None:
        for name, door in self.gpio.doors.items():
            sample = door.snapshot()
            state = sample["door"]
            raw = sample["raw_level"]
            if name in self._last_raw_levels and raw != self._last_raw_levels[name]:
                self._changed()
            self._last_raw_levels[name] = raw
            previous = self._last_door_states.get(name)
            if previous != state:
                self._door_state_dirty = True
            if previous is not None and state != previous and state in {"open", "closed"}:
                self.event(f"{name}_door_{state}")
                log_event("reed_transition", door=name, gpio=GPIOController.INPUTS[name],
                          previous=previous, current=state)
            self._last_door_states[name] = state
        if self.door_workflow.door:
            observed = self.gpio.doors[self.door_workflow.door].snapshot()["door"]
            transition = self.door_workflow.observe(observed)
            if transition:
                self.event(transition, self.door_workflow.command_id)
                if self.door_workflow.phase == "fault":
                    self._abort_workflow(self.door_workflow.fault or "hardware_failure")

    async def _send_door_states(self) -> None:
        doors = {name: self.gpio.doors[name].snapshot()["door"]
                 for name in ("pocket", "medium")}
        await self.esp.send({
            "v": 1, "type": "command", "id": str(uuid4()),
            "action": "set_door_states", "doors": doors,
        })
        self._door_state_dirty = False
        self._last_door_state_sent = time.monotonic()
        if self.direct_mode:
            # ESP firmware discards a closed bank's cached modes. Re-send the
            # locally computed policy immediately when either reed changes.
            await self._refresh_guidance(force=True)

    async def handle_command(self, row: dict) -> dict:
        command_id = str(row.get("id", ""))
        action = row.get("action")
        log_event("command_received", command_id=command_id,
                  action=action if isinstance(action, str) and action in {
                      "capture_light_on", "capture_light_off", "pulse_pocket", "pulse_medium"
                  } else "unsupported")
        if command_id in self._seen:
            log_event("command_failed", command_id=command_id, code="duplicate")
            return {"id": command_id, "status": "failed", "code": "duplicate"}
        if len(self._recent_commands) == self._recent_commands.maxlen:
            self._seen.discard(self._recent_commands[0])
        self._recent_commands.append(command_id)
        self._seen.add(command_id)
        try:
            expiry = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
            if expiry <= datetime.now(UTC):
                raise ValueError("expired")
            if row.get("device_id") != self.settings.get("device_id"):
                raise ValueError("device_mismatch")
            if self.settings["mode"] != "real":
                raise ValueError("simulation_mode")
            if not self.settings.get("enable_actuators", False):
                raise ValueError("actuators_disabled")
            if not self.gpio.allow_outputs:
                raise ValueError("outputs_unverified")
            if action in {"capture_light_on", "capture_light_off"}:
                enabled = action == "capture_light_on"
                previous = self.gpio.outputs["main_light"]
                self.gpio.set_output("main_light", enabled)
                if previous != enabled:
                    log_event("gpio_output", output="main_light", gpio=GPIOController.OUTPUTS["main_light"],
                              previous=previous, current=enabled, command_id=command_id)
                self._capture_light_deadline = (time.monotonic() + float(self.settings.get("capture_light_max_seconds", 12))) if enabled else None
                self.event("command_completed", command_id)
                log_event("command_completed", command_id=command_id, code="light_updated")
                return {"id": command_id, "status": "acked", "code": "light_updated"}
            if action not in {"pulse_pocket", "pulse_medium"}:
                raise ValueError("unsupported_action")
            door = action.removeprefix("pulse_")
            grant_claims = None
            if row.get("transport") == "direct":
                grant_claims = self._validate_unlock_grant(row, door)
                self._validate_direct_unlock(row, door)
            self._last_unlock = {
                "command_id": command_id, "target_group": door,
                "status": "received", "accepted_at": None,
                "activated_at": None, "deactivated_at": None,
                "pulse_seconds": 0.0,
                "hold_max_seconds": self.gpio.max_hold_seconds,
                "last_output_error": None,
            }
            test_channel = self.settings.get("solenoid_led_test_channel")
            if test_channel is not None and door != test_channel:
                raise ValueError("test_channel_not_allowed")
            self.door_workflow.start(
                command_id, door, self.gpio.doors[door].snapshot()["door"])
            if row.get("transport") == "direct":
                self._start_local_operation(row, grant_claims)
            self._last_unlock["status"] = "accepted"
            self._last_unlock["accepted_at"] = datetime.now(UTC).isoformat()
            self.event("command_accepted", command_id)
            log_event("command_accepted", command_id=command_id, door=door)
            self.door_workflow.pulsing()
            self.gpio.activate_solenoid(door)
            if self._local_operation is not None:
                self._local_operation["phase"] = "unlocked"
            self._last_unlock["activated_at"] = datetime.now(UTC).isoformat()
            self.event("output_activated", command_id)
            log_event("solenoid_hold", command_id=command_id, door=door,
                      gpio=GPIOController.OUTPUTS[f"{door}_solenoid"], state="activated")
            self.door_workflow.unlock_activated()
            self._last_unlock["status"] = "completed"
            self.event("command_completed", command_id)
            log_event("command_completed", command_id=command_id, code="unlock_held")
            return {"id": command_id, "status": "acked", "code": "unlock_held"}
        except (KeyError, ValueError, TypeError) as exc:
            if self._last_unlock is not None and self._last_unlock["command_id"] == command_id:
                self._last_unlock["status"] = "rejected"
            if (self.door_workflow.command_id == command_id
                    and self.door_workflow.phase in {"requested", "pulsing"}):
                door = self.door_workflow.door
                if door:
                    self._deactivate_workflow_solenoid(door, "command_rejected")
                self.door_workflow.fail("hardware_failure")
                if (self._local_operation is not None
                        and self._local_operation["command_id"] == command_id):
                    self._local_operation = None
                    self._local_present = {}
                    self._simulated_presence = {}
                    self._simulated_wrong_lifts.clear()
                    self._local_violations = {}
            self.event("command_rejected", command_id)
            code = str(exc)
            if code not in {"expired", "device_mismatch", "simulation_mode",
                            "actuators_disabled", "outputs_unverified", "unsupported_action",
                            "test_channel_not_allowed",
                            "door_workflow_busy", "door_not_closed", "hardware_not_ready",
                            "sensor_state_mismatch", "invalid_unlock_grant",
                            "unlock_grant_expired", "unlock_grant_claim_mismatch"}:
                code = "invalid_command"
            log_event("command_failed", command_id=command_id, code=code)
            return {"id": command_id, "status": "failed", "code": code}
        except Exception as exc:
            log_event("command_failed", command_id=command_id, code="hardware_failure",
                      error_type=type(exc).__name__)
            if self._last_unlock is not None and self._last_unlock["command_id"] == command_id:
                self._last_unlock["status"] = "failed"
                self._last_unlock["last_output_error"] = "hardware_failure"
            if self.door_workflow.command_id == command_id:
                self.door_workflow.fail("hardware_failure")
                door = self.door_workflow.door
                if door:
                    self._deactivate_workflow_solenoid(door, "hardware_failure")
            if (self._local_operation is not None
                    and self._local_operation["command_id"] == command_id):
                self._local_operation = None
                self._local_present = {}
                self._simulated_presence = {}
                self._simulated_wrong_lifts.clear()
                self._local_violations = {}
            self.event("command_failed", command_id)
            return {"id": command_id, "status": "failed", "code": "hardware_failure"}

    async def _sample_loop(self) -> None:
        while True:
            if self._capture_light_deadline is not None and time.monotonic() >= self._capture_light_deadline:
                self._capture_light_deadline = None
                self._capture_light_off()
                self._changed()
            self.gpio.sample_inputs()
            self.record_door_changes()
            door = self.door_workflow.door
            if (door and self.gpio.outputs[f"{door}_solenoid"]
                    and self.gpio.hold_limit_exceeded(door)):
                self._abort_workflow("solenoid_hold_timeout")
            await asyncio.sleep(self._sample_seconds)

    async def _esp_loop(self) -> None:
        next_connect = 0.0
        next_ping = 0.0
        while True:
            if self.esp.serial is None:
                if self._esp_online:
                    self.event("esp_disconnected")
                if time.monotonic() >= next_connect:
                    next_connect = time.monotonic() + 5
                    try:
                        await asyncio.to_thread(self.esp.connect)
                        await self.esp.send({"v": 1, "type": "identify"})
                        if not self._esp_online:
                            self._esp_online = True
                            log_event("esp_connection", state="connected", port=self.esp.port)
                        self._last_esp_connection = False
                        self._changed()
                    except (OSError, ImportError):
                        if self.esp.error != "serial_unavailable":
                            self.esp.error = "serial_unavailable"
                            log_event("esp_connection", state="unavailable", port=self.esp.port)
                            self._changed()
                await asyncio.sleep(0.25)
                continue
            messages = await self.esp.read()
            if self.esp.serial is None:
                self.event("esp_disconnected")
                continue
            for message in messages:
                if message["type"] == "hello":
                    self.event("esp_hello")
                    self._door_state_dirty = True
                    if self.direct_mode:
                        self._boot_recovery_snapshot_pending = True
                    if not self._esp_online:
                        self._esp_online = True
                        log_event("esp_connection", state="connected", port=self.esp.port)
                    self._last_esp_connection = False
                    try:
                        await self.esp.send({"v": 1, "type": "snapshot"})
                    except ConnectionError:
                        self.event("esp_disconnected")
                elif message["type"] == "event":
                    event = {key: message.get(key) for key in
                             ("event_id", "boot_id", "seq", "slot", "kind", "present")}
                    if valid_presence_event(event):
                        if self.direct_mode:
                            await self._observe_local_presence(
                                event["slot"], self._simulated_presence.get(
                                    event["slot"], event["present"]))
                            # The local monitor has already consumed the event.
                            # Only genuine incident transitions enter the durable
                            # backend queue; routine sensor changes stay local.
                            try:
                                await self.esp.send({"v": 1, "type": "event_ack",
                                                     "event_id": event["event_id"]})
                            except ConnectionError:
                                self.event("esp_disconnected")
                            continue
                        if len(self._pending_presence) < 128 or event["event_id"] in self._pending_presence:
                            self._pending_presence[event["event_id"]] = event
                            self._publish_signal.set()
                            if (event["kind"] != "SENSOR_SNAPSHOT" and
                                    event["event_id"] not in self._logged_presence_set):
                                if len(self._logged_presence_ids) == self._logged_presence_ids.maxlen:
                                    self._logged_presence_set.discard(self._logged_presence_ids[0])
                                self._logged_presence_ids.append(event["event_id"])
                                self._logged_presence_set.add(event["event_id"])
                                log_event("presence_change", slot=event["slot"],
                                          previous=not event["present"], current=event["present"],
                                          event_id=event["event_id"])
                    else:
                        # An API 422 would otherwise block all later events and heartbeats.
                        # Discard the bad frame and ask the ESP for a fresh baseline.
                        self.esp.error = "invalid_presence_event"
                        self._changed()
                        event_id = event.get("event_id")
                        if isinstance(event_id, str) and 0 < len(event_id) <= 80:
                            try:
                                await self.esp.send({"v": 1, "type": "event_ack", "event_id": event_id})
                                await self.esp.send({"v": 1, "type": "snapshot"})
                            except ConnectionError:
                                self.event("esp_disconnected")
                else:
                    self._changed()
                    if self.direct_mode and message["type"] == "telemetry":
                        await self._observe_local_telemetry(message)
                        if self._completion_snapshot_pending:
                            await self._try_local_completion(message)
                    if (self.direct_mode and message["type"] == "telemetry"
                            and self._boot_recovery_snapshot_pending
                            and not self._completion_snapshot_pending):
                        self._boot_recovery_snapshot_pending = False
                        self._queue_direct_event(self._direct_event_snapshot())
                if message["type"] == "ping":
                    try:
                        await self.esp.send({"v": 1, "type": "pong", "seq": message.get("seq", 0),
                                             "uptime_ms": int(time.monotonic() * 1000)})
                    except ConnectionError:
                        self.event("esp_disconnected")
            if self.esp.serial is not None and (
                    self._door_state_dirty
                    or time.monotonic() - self._last_door_state_sent >= 3):
                try:
                    await self._send_door_states()
                except ConnectionError:
                    self.event("esp_disconnected")
            if self.esp.serial is not None and time.monotonic() >= next_ping:
                next_ping = time.monotonic() + 3
                self._ping_seq += 1
                try:
                    await self.esp.send({"v": 1, "type": "ping", "seq": self._ping_seq,
                                         "uptime_ms": int(time.monotonic() * 1000)})
                    if self.esp.boot_id is None:
                        await self.esp.send({"v": 1, "type": "identify"})
                except ConnectionError:
                    self.event("esp_disconnected")
            if (self.esp.last_seen and time.monotonic() - self.esp.last_seen > 10
                    and self.esp.error != "telemetry_stale"):
                self.esp.error = "telemetry_stale"
                self._changed()
            if not messages:
                await asyncio.sleep(0.05)

    async def _direct_event_loop(self) -> None:
        """Publish only transaction/security transitions, never routine telemetry."""
        backoff = 1.0
        while True:
            operation = self._local_operation
            if operation is not None and operation.get("phase") not in {
                    "locally_completed", "synced"} and self.gpio.outputs.get(
                        f"{operation.get('door')}_solenoid", False):
                # Physical control is entirely local. Do not introduce a
                # backend/database dependency while a gate output is active.
                await asyncio.sleep(0.1)
                continue
            if not self._security_events and not self._direct_events:
                await self._direct_event_signal.wait()
                self._direct_event_signal.clear()
                continue
            security_event = bool(self._security_events)
            queued = (self._security_events if security_event else self._direct_events)[0]
            durable_completion = queued.get("durable") is True
            payload = {"snapshot": queued.get("snapshot") or self.snapshot(),
                       "presence": queued.get("presence")}
            try:
                result = await asyncio.to_thread(
                    request_json, self.config.backend_url, "/api/hardware/workflow-event",
                    payload, self.credential,
                )
                finalized = (not security_event and (
                    result.get("finalized") is True or result.get("phase") == "completed"))
                if not security_event:
                    if finalized:
                        await self._finish_local_operation()
                    elif result.get("phase") == "requires_review":
                        reason = result.get("reason") or "REVIEW_REQUIRED"
                        if ((self._local_operation or {}).get("phase")
                                == "locally_completed"):
                            # Record synchronization failure is NOT a physical
                            # hardware failure. Preserve immutable completion
                            # and keep the MOSFET output inactive.
                            self._finalization_error = reason
                            self._changed()
                        else:
                            self._abort_workflow("hardware_failure")
                            self._finalization_error = reason
                    elif self._awaiting_backend_finalization:
                        self._finalization_error = (
                            result.get("reason") or "SYNCHRONIZATION_PENDING")
                        self._changed()
                if (not security_event and result.get("needs_fresh_snapshot")
                        and (self._local_operation or {}).get("phase")
                        not in {"locally_completed", "synced"}):
                    self._completion_snapshot_pending = True
                    if self.esp.serial is not None:
                        try:
                            await self.esp.send({"v": 1, "type": "snapshot"})
                        except ConnectionError:
                            pass
                presence = queued.get("presence")
                if presence and self.esp.serial is not None:
                    try:
                        await self.esp.send({"v": 1, "type": "event_ack",
                                             "event_id": presence["event_id"]})
                    except ConnectionError:
                        pass
                if security_event:
                    self._security_events.popleft()
                    self._save_security_events()
                elif not durable_completion or finalized:
                    self._direct_events.popleft()
                    self._save_direct_events()
                if durable_completion and not finalized:
                    # Back off terminal/review responses rather than retrying
                    # the same immutable record twice per second forever.
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 60.0)
                else:
                    backoff = 1.0
            except Exception:
                if self._awaiting_backend_finalization:
                    self._finalization_error = "BACKEND_UNAVAILABLE"
                    self._changed()
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    async def _local_guidance_loop(self) -> None:
        """Refresh the ESP watchdog from cached guidance without a DB poll."""
        while True:
            await asyncio.sleep(1)
            await self._refresh_guidance()

    async def _publish_loop(self) -> None:
        last_attempt = 0.0
        last_success = 0.0
        published_sequence = -1
        retry_at = 0.0
        backoff = 1.0
        while True:
            now = time.monotonic()
            dirty = self._sequence != published_sequence
            next_due = min(last_success + self._telemetry_seconds,
                           last_attempt + self._min_gap_seconds if dirty else float("inf"))
            next_due = max(next_due, retry_at)
            if now < next_due:
                try:
                    await asyncio.wait_for(self._publish_signal.wait(), timeout=next_due - now)
                except TimeoutError:
                    pass
                self._publish_signal.clear()
                continue
            last_attempt = now
            operation = "heartbeat"
            operation_command_id: str | None = None
            operation_slot: str | None = None
            try:
                # A claimed command's acknowledgement is retried before claiming more work.
                while self._pending_acks:
                    operation = "command_ack"
                    operation_command_id = self._pending_acks[0]["id"]
                    result = await asyncio.to_thread(request_json, self.config.backend_url,
                                                     "/api/hardware/ack", self._pending_acks[0], self.credential)
                    log_event("command_acknowledgment", command_id=operation_command_id,
                              status=self._pending_acks[0]["status"],
                              accepted=isinstance(result, dict) and result.get("ok") is True)
                    self._pending_acks.popleft()
                while self._pending_presence:
                    event_id, event = next(iter(self._pending_presence.items()))
                    operation = "presence"
                    operation_command_id = None
                    operation_slot = event["slot"]
                    try:
                        await asyncio.to_thread(request_json, self.config.backend_url,
                                                "/api/hardware/presence", event, self.credential)
                    except DeviceApiError as exc:
                        # Keep the event queued, but still send a heartbeat so
                        # the backend can observe the Pi and return guidance.
                        if not self._presence_upload_failed:
                            log_event("backend_communication_error", operation="presence",
                                      slot=operation_slot, status_code=exc.status_code)
                        self._presence_upload_failed = True
                        break
                    if self._presence_upload_failed:
                        log_event("presence_upload_recovered", slot=operation_slot)
                        self._presence_upload_failed = False
                    self._pending_presence.pop(event_id, None)
                    if self.esp.serial is not None:
                        try:
                            await self.esp.send({"v": 1, "type": "event_ack", "event_id": event_id})
                        except ConnectionError:
                            pass  # ESP resends; the backend deduplicates the event ID.
                sent_sequence = self._sequence
                operation = "heartbeat"
                operation_slot = None
                result = await asyncio.to_thread(
                    request_json, self.config.backend_url, "/api/hardware/heartbeat",
                    {"snapshot": self.snapshot()}, self.credential)
                if self.backend != "online":
                    self.backend = "online"
                    self._changed()
                    log_event("backend_connection", state="online")
                published_sequence = sent_sequence
                last_success = time.monotonic()
                backoff = 1.0
                retry_at = 0.0
                await self._apply_guidance(result.get("guidance") or {})
                # UPDATE ... RETURNING in the backend claim RPC does not preserve
                # creation order. Apply queued light transitions in request order.
                for row in sorted(result.get("commands", []),
                                  key=lambda command: (command.get("created_at") or "",
                                                       command.get("id") or "")):
                    ack = await self.handle_command(row)
                    self._pending_acks.append(ack)
                while self._pending_acks:
                    operation = "command_ack"
                    operation_command_id = self._pending_acks[0]["id"]
                    result = await asyncio.to_thread(request_json, self.config.backend_url,
                                                     "/api/hardware/ack", self._pending_acks[0], self.credential)
                    log_event("command_acknowledgment", command_id=operation_command_id,
                              status=self._pending_acks[0]["status"],
                              accepted=isinstance(result, dict) and result.get("ok") is True)
                    self._pending_acks.popleft()
            except DeviceApiError as exc:
                self._set_buzzer(False)
                self._capture_light_deadline = None
                self._capture_light_off()
                await self._clear_guidance()
                if self.backend != "offline":
                    self.backend = "offline"
                    self.event("backend_unavailable")
                    log_event("backend_communication_error", operation=operation,
                              command_id=operation_command_id, slot=operation_slot,
                              status_code=exc.status_code)
                retry_at = time.monotonic() + backoff
                backoff = min(backoff * 2, 30)
            except Exception as exc:
                self._set_buzzer(False)
                self._capture_light_deadline = None
                self._capture_light_off()
                await self._clear_guidance()
                if self.backend != "offline":
                    self.backend = "offline"
                    self.event("backend_unavailable")
                    log_event("backend_communication_error", operation=operation,
                              command_id=operation_command_id, slot=operation_slot,
                              error_type=type(exc).__name__)
                retry_at = time.monotonic() + backoff
                backoff = min(backoff * 2, 30)

    def _capture_light_off(self) -> None:
        self._capture_light_deadline = None
        if self.gpio.allow_outputs and self.gpio.outputs["main_light"]:
            self.gpio.set_output("main_light", False)
            log_event("gpio_output", output="main_light", gpio=GPIOController.OUTPUTS["main_light"],
                      previous=True, current=False, reason="automatic_off")
            self._changed()

    def _set_buzzer(self, requested: bool) -> None:
        if not self.settings.get("enable_actuators", False) or not self.gpio.allow_outputs:
            return
        now = time.monotonic()
        maximum = float(self.settings.get("buzzer_max_seconds", 10))
        if requested and self._buzzer_started is None:
            self._buzzer_started = now
        enabled = requested and self._buzzer_started is not None and now - self._buzzer_started < maximum
        if not requested:
            self._buzzer_started = None
        if self.gpio.outputs["buzzer"] != enabled:
            previous = self.gpio.outputs["buzzer"]
            self.gpio.set_output("buzzer", enabled)
            log_event("gpio_output", output="buzzer", gpio=GPIOController.OUTPUTS["buzzer"],
                      previous=previous, current=enabled)
            self._changed()

    async def _clear_guidance(self) -> None:
        self._backend_guidance = None
        self._backend_buzzer = False
        await self._refresh_guidance(force=True)

    async def _refresh_guidance(self, *, force: bool = False) -> None:
        slots = {f"P-{number:02d}" for number in range(1, 9)}
        slots.update(f"M-{number:02d}" for number in range(1, 5))
        if self.direct_mode:
            modes = {slot: "OFF" for slot in slots}
            operation = self._local_operation
            if operation is not None:
                for slot, expected in operation["expected"].items():
                    if expected:
                        modes[slot] = "STEADY_ON"
                assigned = operation["assigned_slot"]
                assigned_present = self._local_present.get(assigned)
                if assigned_present is operation["target_present"]:
                    modes[assigned] = "STEADY_ON" if assigned_present else "OFF"
                else:
                    modes[assigned] = "NORMAL_BLINK"
        else:
            modes = (self._backend_guidance.copy() if self._backend_guidance is not None
                     else {slot: "OFF" for slot in slots})
        for slot in self._local_violations:
            modes[slot] = "SOS_BLINK"
        self._set_buzzer((self._backend_buzzer and not self.direct_mode)
                         or bool(self._local_violations))
        if self.esp.serial is not None and (
                force or modes != self._last_guidance or not self._last_esp_connection or
                time.monotonic() - self._last_guidance_sent >= 5):
            try:
                await self.esp.send({"v": 1, "type": "command", "id": str(uuid4()),
                                     "action": "set_all_lights", "modes": modes})
                self._last_guidance = modes.copy()
                self._last_esp_connection = True
                self._last_guidance_sent = time.monotonic()
            except ConnectionError:
                self._last_esp_connection = False

    async def _apply_guidance(self, guidance: dict) -> None:
        modes = guidance.get("modes")
        expected_slots = {f"P-{number:02d}" for number in range(1, 9)}
        expected_slots.update(f"M-{number:02d}" for number in range(1, 5))
        if not isinstance(modes, dict) or set(modes) != expected_slots or any(
                mode not in {"OFF", "STEADY_ON", "NORMAL_BLINK", "SOS_BLINK"}
                for mode in modes.values()):
            await self._clear_guidance()
            return
        self._backend_guidance = modes.copy()
        self._backend_buzzer = bool(guidance.get("buzzer"))
        await self._refresh_guidance()

    async def run(self) -> None:
        if self.settings["mode"] == "real":
            try:
                self.credential = read_credential(self.config.credential_file)
            except (OSError, PermissionError):
                self.fault = "device_credential_unavailable"
                LOG.exception("Hardware device credential unavailable")
                return
        try:
            self.gpio.open()
            self.gpio.sample_inputs()
            self.record_door_changes()
            self.ready = True
        except Exception:
            self.fault = "gpio_start_failed"
            LOG.exception("Hardware GPIO startup failed")
            return
        try:
            async with asyncio.TaskGroup() as tasks:
                tasks.create_task(self._sample_loop())
                if self.settings["mode"] == "real":
                    tasks.create_task(self._esp_loop())
                    if self.direct_mode:
                        tasks.create_task(self._direct_event_loop())
                        tasks.create_task(self._local_guidance_loop())
                    else:
                        tasks.create_task(self._publish_loop())
        except Exception:
            self.fault = "hardware_loop_failed"
            LOG.exception("Hardware monitoring stopped")
        finally:
            self.ready = False
            self._set_buzzer(False)
            self._capture_light_off()
            await self._clear_guidance()
            self.esp.close()
            self.gpio.close()


def create_app(config: Config, settings: dict) -> FastAPI:
    service = HardwareService(config, settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        task = asyncio.create_task(service.run())
        service.task = task
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    app = FastAPI(title="SAULI Pi local hardware", lifespan=lifespan)

    def authenticate_direct(authorization: str | None) -> None:
        if not service.direct_mode:
            raise HTTPException(status_code=404, detail="Direct transport is disabled")
        expected = settings.get("direct_api_token", "")
        supplied = authorization.removeprefix("Bearer ") if authorization else ""
        if not expected or not hmac.compare_digest(supplied, expected):
            raise HTTPException(status_code=403, detail="Direct hardware authentication failed")

    @app.get("/health")
    def health():
        return {"ok": service.ready and service.task is not None and not service.task.done(),
                "mode": settings["mode"], "fault": service.fault}

    @app.get("/state")
    def state():
        return service.snapshot()

    @app.get("/v1/state")
    def direct_state(authorization: str | None = Header(default=None)):
        authenticate_direct(authorization)
        return service.snapshot()

    @app.post("/v1/sensor-simulation")
    async def sensor_simulation(payload: SimulatedPresence,
                                authorization: str | None = Header(default=None)):
        authenticate_direct(authorization)
        return await service.simulate_presence(payload)

    @app.post("/v1/commands")
    async def direct_command(command: DirectCommand,
                             authorization: str | None = Header(default=None)):
        authenticate_direct(authorization)
        result = await service.execute_direct_command(command.model_dump(mode="json"))
        return {**result, "snapshot": service.snapshot()}

    return app


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("/etc/sauli/controller.json"))
    parser.add_argument("--hardware", type=Path, default=Path("/etc/sauli/hardware.json"))
    args = parser.parse_args()
    import uvicorn
    settings = load_hardware(args.hardware)
    uvicorn.run(create_app(Config.load(args.config), settings),
                host=settings.get("direct_bind_host", "127.0.0.1"),
                port=int(settings.get("direct_port", 8765)), workers=1, reload=False)


if __name__ == "__main__":
    main()
