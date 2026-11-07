"""Loopback diagnostics and outbound device telemetry, separate from browser launch."""

import argparse
import asyncio
import json
import logging
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI
from sauli_pi.communication.backend_client import DeviceApiError, request_json
from sauli_pi.communication.esp32_serial import EspLink
from sauli_pi.config import Config, read_credential
from sauli_pi.hardware.controller import GPIOController
from sauli_pi.workflows.door import DoorWorkflow

LOG = logging.getLogger("sauli.hardware")


def load_hardware(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("mode") not in ("real", "simulation"):
        raise ValueError("Hardware mode must be explicitly real or simulation")
    if value.get("enable_actuators") and not value.get("output_polarity_verified"):
        raise ValueError("Verify output polarity before enabling actuators")
    for key, default, minimum, maximum in (
        ("gpio_sample_seconds", 0.05, 0.02, 0.2),
        ("telemetry_interval_seconds", 0.5, 0.25, 30),
        ("telemetry_min_gap_seconds", 0.15, 0.1, 5),
    ):
        try:
            number = float(value.get(key, default))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid {key}") from exc
        if not minimum <= number <= maximum:
            raise ValueError(f"{key} must be between {minimum} and {maximum}")
        value[key] = number
    if value["telemetry_min_gap_seconds"] > value["telemetry_interval_seconds"]:
        raise ValueError("telemetry_min_gap_seconds cannot exceed telemetry_interval_seconds")
    if value.get("mode") == "real":
        try:
            value["device_id"] = str(UUID(value["device_id"]))
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError("Real hardware requires the enrolled device UUID") from exc
    return value


class HardwareService:
    def __init__(self, config: Config, settings: dict):
        self.config = config
        self.settings = settings
        self.gpio = GPIOController(
            simulation=settings["mode"] == "simulation",
            closed_level=settings["reed_closed_level"],
            active_high=settings["output_active_high"],
            pulse_seconds=float(settings.get("solenoid_pulse_seconds", 0.35)),
            allow_outputs=bool(settings.get("output_polarity_verified", False)))
        self.esp = EspLink(settings.get("esp_port", "/dev/serial0"),
                           int(settings.get("esp_baud", 115200)))
        self.backend = "unknown"
        self.events: list[dict] = []
        self._seen: set[str] = set()
        self._recent_commands: deque[str] = deque(maxlen=256)
        self.credential: str | None = None
        self.ready = False
        self.fault: str | None = None
        self._ping_seq = 0
        self._last_door_states: dict[str, str] = {}
        self._last_raw_levels: dict[str, int | None] = {}
        self._sequence = 0
        self._observed_at: str | None = None
        self._publish_signal = asyncio.Event()
        self._pending_acks: deque[dict] = deque()
        self._sample_seconds = float(settings.get("gpio_sample_seconds", 0.05))
        self._telemetry_seconds = float(settings.get("telemetry_interval_seconds", 0.5))
        self._min_gap_seconds = float(settings.get("telemetry_min_gap_seconds", 0.15))
        self.door_workflow = DoorWorkflow(
            open_timeout_seconds=float(settings.get("door_open_timeout_seconds", 5)),
            close_timeout_seconds=float(settings.get("door_close_timeout_seconds", 30)))
        self.task: asyncio.Task | None = None

    def event(self, kind: str, command_id: str | None = None) -> None:
        entry = {"at": datetime.now(UTC).isoformat(), "kind": kind}
        if command_id:
            entry["command_id"] = command_id
        self.events = ([entry] + self.events)[:64]
        self._changed()

    def _changed(self) -> None:
        self._sequence += 1
        self._observed_at = datetime.now(UTC).isoformat()
        self._publish_signal.set()

    def snapshot(self) -> dict:
        return {"schema_version": 1, "unit_code": self.config.unit_code,
                "device_code": self.config.device_code,
                "recorded_at": datetime.now(UTC).isoformat(),
                "observed_at": self._observed_at, "sequence": self._sequence,
                "backend": self.backend, "pi": self.gpio.snapshot(),
                "esp": self.esp.snapshot() if self.settings["mode"] == "real" else
                {"connection": "simulated", "telemetry": None},
                "events": self.events[:64],
                "door_workflow": self.door_workflow.snapshot()}

    def record_door_changes(self) -> None:
        for name, door in self.gpio.doors.items():
            sample = door.snapshot()
            state = sample["door"]
            raw = sample["raw_level"]
            if name in self._last_raw_levels and raw != self._last_raw_levels[name]:
                self._changed()
            self._last_raw_levels[name] = raw
            previous = self._last_door_states.get(name)
            if previous is not None and state != previous and state in {"open", "closed"}:
                self.event(f"{name}_door_{state}")
            self._last_door_states[name] = state
        if self.door_workflow.door:
            observed = self.gpio.doors[self.door_workflow.door].snapshot()["door"]
            transition = self.door_workflow.observe(observed)
            if transition:
                self.event(transition, self.door_workflow.command_id)

    async def handle_command(self, row: dict) -> dict:
        command_id = str(row.get("id", ""))
        if command_id in self._seen:
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
            action = row.get("action")
            if action not in {"pulse_pocket", "pulse_medium"}:
                raise ValueError("unsupported_action")
            door = action.removeprefix("pulse_")
            self.door_workflow.start(
                command_id, door, self.gpio.doors[door].snapshot()["door"])
            self.event("command_accepted", command_id)
            self.door_workflow.pulsing()
            self.event("output_activated", command_id)
            await self.gpio.pulse(door)
            self.door_workflow.pulse_finished()
            self.event("output_deactivated", command_id)
            self.event("command_completed", command_id)
            return {"id": command_id, "status": "acked", "code": "pulse_completed"}
        except (KeyError, ValueError, TypeError) as exc:
            self.event("command_rejected", command_id)
            code = str(exc)
            if code not in {"expired", "device_mismatch", "simulation_mode",
                            "actuators_disabled", "unsupported_action",
                            "door_workflow_busy", "door_not_closed"}:
                code = "invalid_command"
            return {"id": command_id, "status": "failed", "code": code}
        except Exception:
            LOG.exception("Hardware command failed (id=%s)", command_id)
            if self.door_workflow.command_id == command_id:
                self.door_workflow.fail("hardware_failure")
            self.event("command_failed", command_id)
            return {"id": command_id, "status": "failed", "code": "hardware_failure"}

    async def _sample_loop(self) -> None:
        while True:
            self.gpio.sample_inputs()
            self.record_door_changes()
            await asyncio.sleep(self._sample_seconds)

    async def _esp_loop(self) -> None:
        next_connect = 0.0
        next_ping = 0.0
        while True:
            if self.esp.serial is None:
                if time.monotonic() >= next_connect:
                    next_connect = time.monotonic() + 5
                    try:
                        await asyncio.to_thread(self.esp.connect)
                        self._changed()
                    except (OSError, ImportError):
                        if self.esp.error != "serial_unavailable":
                            self.esp.error = "serial_unavailable"
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
                else:
                    self._changed()
                if message["type"] == "ping":
                    try:
                        await self.esp.send({"v": 1, "type": "pong", "seq": message.get("seq", 0),
                                             "uptime_ms": int(time.monotonic() * 1000)})
                    except ConnectionError:
                        self.event("esp_disconnected")
            if self.esp.serial is not None and time.monotonic() >= next_ping:
                next_ping = time.monotonic() + 3
                self._ping_seq += 1
                try:
                    await self.esp.send({"v": 1, "type": "ping", "seq": self._ping_seq,
                                         "uptime_ms": int(time.monotonic() * 1000)})
                except ConnectionError:
                    self.event("esp_disconnected")
            if (self.esp.last_seen and time.monotonic() - self.esp.last_seen > 10
                    and self.esp.error != "telemetry_stale"):
                self.esp.error = "telemetry_stale"
                self._changed()
            if not messages:
                await asyncio.sleep(0.05)

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
            try:
                # A claimed command's acknowledgement is retried before claiming more work.
                while self._pending_acks:
                    await asyncio.to_thread(request_json, self.config.backend_url,
                                            "/api/hardware/ack", self._pending_acks[0], self.credential)
                    self._pending_acks.popleft()
                sent_sequence = self._sequence
                result = await asyncio.to_thread(
                    request_json, self.config.backend_url, "/api/hardware/heartbeat",
                    {"snapshot": self.snapshot()}, self.credential)
                if self.backend != "online":
                    self.backend = "online"
                    self._changed()
                published_sequence = sent_sequence
                last_success = time.monotonic()
                backoff = 1.0
                retry_at = 0.0
                for row in result.get("commands", []):
                    ack = await self.handle_command(row)
                    self._pending_acks.append(ack)
                while self._pending_acks:
                    await asyncio.to_thread(request_json, self.config.backend_url,
                                            "/api/hardware/ack", self._pending_acks[0], self.credential)
                    self._pending_acks.popleft()
            except DeviceApiError:
                if self.backend != "offline":
                    self.backend = "offline"
                    self.event("backend_unavailable")
                retry_at = time.monotonic() + backoff
                backoff = min(backoff * 2, 30)
            except Exception:
                if self.backend != "offline":
                    self.backend = "offline"
                    self.event("backend_unavailable")
                LOG.exception("Hardware publication failed")
                retry_at = time.monotonic() + backoff
                backoff = min(backoff * 2, 30)

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
                    tasks.create_task(self._publish_loop())
        except Exception:
            self.fault = "hardware_loop_failed"
            LOG.exception("Hardware monitoring stopped")
        finally:
            self.ready = False
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

    @app.get("/health")
    def health():
        return {"ok": service.ready and service.task is not None and not service.task.done(),
                "mode": settings["mode"], "fault": service.fault}

    @app.get("/state")
    def state():
        return service.snapshot()

    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("/etc/sauli/controller.json"))
    parser.add_argument("--hardware", type=Path, default=Path("/etc/sauli/hardware.json"))
    args = parser.parse_args()
    import uvicorn
    uvicorn.run(create_app(Config.load(args.config), load_hardware(args.hardware)),
                host="127.0.0.1", port=8765, workers=1, reload=False)


if __name__ == "__main__":
    main()
