"""Loopback diagnostics and outbound device telemetry, separate from browser launch."""

import argparse
import asyncio
import json
import logging
import time
from collections import deque
from uuid import UUID
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

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
        self.door_workflow = DoorWorkflow(
            open_timeout_seconds=float(settings.get("door_open_timeout_seconds", 5)),
            close_timeout_seconds=float(settings.get("door_close_timeout_seconds", 30)))
        self.task: asyncio.Task | None = None

    def event(self, kind: str, command_id: str | None = None) -> None:
        entry = {"at": datetime.now(UTC).isoformat(), "kind": kind}
        if command_id:
            entry["command_id"] = command_id
        self.events = ([entry] + self.events)[:20]

    def snapshot(self) -> dict:
        self.gpio.sample_inputs()
        return {"schema_version": 1, "unit_code": self.config.unit_code,
                "device_code": self.config.device_code,
                "recorded_at": datetime.now(UTC).isoformat(),
                "backend": self.backend, "pi": self.gpio.snapshot(),
                "esp": self.esp.snapshot() if self.settings["mode"] == "real" else
                {"connection": "simulated", "telemetry": None},
                "events": self.events[:10],
                "door_workflow": self.door_workflow.snapshot()}

    def record_door_changes(self) -> None:
        for name, door in self.gpio.doors.items():
            state = door.snapshot()["door"]
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
            self.gpio.sample_inputs()
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
            self.record_door_changes()
            self.ready = True
        except Exception:
            self.fault = "gpio_start_failed"
            LOG.exception("Hardware GPIO startup failed")
            return
        try:
            if self.settings["mode"] == "real":
                try:
                    self.esp.connect()
                except Exception:
                    self.esp.error = "serial_unavailable"
            next_report = 0.0
            next_connect = 0.0
            next_ping = 0.0
            while True:
                if self.settings["mode"] == "real":
                    if self.esp.serial is None and time.monotonic() >= next_connect:
                        next_connect = time.monotonic() + 5
                        try:
                            self.esp.connect()
                        except Exception:
                            self.esp.error = "serial_unavailable"
                    if self.esp.serial is not None:
                        for message in await self.esp.read():
                            if message["type"] == "hello":
                                self.event("esp_hello")
                            elif message["type"] == "ping":
                                try:
                                    await self.esp.send({"v": 1, "type": "pong", "seq": message.get("seq", 0), "uptime_ms": int(time.monotonic() * 1000)})
                                except ConnectionError:
                                    self.event("esp_disconnected")
                        if self.esp.serial is not None and time.monotonic() >= next_ping:
                            next_ping = time.monotonic() + 3
                            self._ping_seq += 1
                            try:
                                await self.esp.send({"v": 1, "type": "ping", "seq": self._ping_seq, "uptime_ms": int(time.monotonic() * 1000)})
                            except ConnectionError:
                                self.event("esp_disconnected")
                        if self.esp.last_seen and time.monotonic() - self.esp.last_seen > 10:
                            self.esp.error = "telemetry_stale"
                self.gpio.sample_inputs()
                self.record_door_changes()
                if self.settings["mode"] == "real" and time.monotonic() >= next_report:
                    next_report = time.monotonic() + 2
                    try:
                        result = await asyncio.to_thread(
                            request_json, self.config.backend_url,
                            "/api/hardware/heartbeat",
                            {"snapshot": self.snapshot()}, self.credential)
                        self.backend = "online"
                        for row in result.get("commands", []):
                            ack = await self.handle_command(row)
                            await asyncio.to_thread(
                                request_json, self.config.backend_url,
                                "/api/hardware/ack", ack, self.credential)
                    except DeviceApiError:
                        self.backend = "offline"
                        self.event("backend_unavailable")
                    except Exception:
                        self.backend = "offline"
                        LOG.exception("Hardware heartbeat failed")
                        self.event("backend_unavailable")
                await asyncio.sleep(0.1)
        finally:
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
