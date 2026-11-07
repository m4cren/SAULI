"""Hardware boundaries must stay deterministic without claiming real pins."""

import asyncio
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from sauli_pi.communication.protocol import FrameDecoder, FrameError, encode_frame
from sauli_pi.communication.esp32_serial import EspLink
from sauli_pi.config import Config
from sauli_pi.hardware.controller import DoorInput, GPIOController
from sauli_pi.hardware_service import HardwareService, load_hardware
from sauli_pi.workflows.door import DoorWorkflow


def test_frames_handle_partial_combined_boot_chatter_and_oversize():
    decoder = FrameDecoder()
    first = encode_frame({"v": 1, "type": "ping", "seq": 1})
    second = encode_frame({"v": 1, "type": "pong", "seq": 1})
    assert decoder.feed(b"ESP-ROM:boot\n" + first[:5]) == []
    assert [m["type"] for m in decoder.feed(first[5:] + second)] == ["ping", "pong"]
    assert decoder.dropped == 1
    assert decoder.feed(b"x" * 4097) == []
    assert decoder.dropped == 2
    with pytest.raises(FrameError):
        encode_frame({"v": 2, "type": "ping"})


def test_serial_write_failure_disconnects_without_stopping_reconnect_loop():
    class BrokenSerial:
        def write(self, _payload):
            raise OSError("device disconnected")

        def close(self):
            raise OSError("device already gone")

    link = EspLink()
    link.serial = BrokenSerial()
    with pytest.raises(ConnectionError, match="serial write failed"):
        asyncio.run(link.send({"v": 1, "type": "ping", "seq": 1}))
    assert link.serial is None
    assert link.snapshot()["connection"] == "offline"
    assert link.snapshot()["error"] == "serial_write_failed"


def test_stale_telemetry_is_not_displayed_as_current_sensor_data():
    link = EspLink()
    link.serial = object()
    link.last_seen = time.monotonic()
    link.last_telemetry = {"type": "telemetry", "slots": [{"code": "P-01", "present": True}]}
    link.last_telemetry_at = link.last_seen - 6
    assert link.snapshot()["connection"] == "online"
    assert link.snapshot()["telemetry"] is None


def test_reed_polarity_and_debounce():
    door = DoorInput(closed_level=0, debounce_seconds=0.05)
    door.update(1, now=1.0)
    assert door.snapshot() == {"raw_level": 1, "door": "open"}
    door.update(0, now=2.0)
    assert door.snapshot() == {"raw_level": 0, "door": "open"}
    door.update(0, now=2.06)
    assert door.snapshot()["door"] == "closed"


def test_simulated_gpio_pulse_is_bounded_and_cleans_up_on_cancel():
    async def exercise():
        gpio = GPIOController(simulation=True, closed_level={"pocket": 0, "medium": 0},
                              active_high={name: True for name in GPIOController.OUTPUTS},
                              pulse_seconds=0.1)
        gpio.open()
        task = asyncio.create_task(gpio.pulse("pocket"))
        await asyncio.sleep(0.01)
        assert gpio.outputs["pocket_solenoid"] is True
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert gpio.outputs["pocket_solenoid"] is False
        gpio.close()
    asyncio.run(exercise())
    with pytest.raises(ValueError):
        GPIOController(simulation=True, closed_level={"pocket": 0, "medium": 0},
                       active_high={name: True for name in GPIOController.OUTPUTS},
                       pulse_seconds=2)


def test_simulation_rejects_real_command_and_expired_command(tmp_path: Path):
    device = str(uuid4())
    config = Config("https://api.example.test", "https://app.example.test", "KIOSK-A",
                    "SAULI-A", tmp_path / "credential")
    settings = {"mode": "simulation", "device_id": device,
                "reed_closed_level": {"pocket": 0, "medium": 0},
                "output_active_high": {name: True for name in GPIOController.OUTPUTS},
                "enable_actuators": True}
    service = HardwareService(config, settings)
    row = {"id": str(uuid4()), "device_id": device, "action": "pulse_pocket",
           "expires_at": (datetime.now(UTC) + timedelta(seconds=5)).isoformat()}
    assert asyncio.run(service.handle_command(row))["code"] == "simulation_mode"
    assert service.gpio.outputs["pocket_solenoid"] is False
    assert asyncio.run(service.handle_command(row))["code"] == "duplicate"
    row["id"] = str(uuid4())
    row["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    assert asyncio.run(service.handle_command(row))["code"] == "expired"


def test_real_config_requires_enrolled_uuid_and_explicit_polarity(tmp_path: Path):
    file = tmp_path / "hardware.json"
    file.write_text('{"mode":"real","device_id":"not-a-uuid"}', encoding="utf-8")
    with pytest.raises(ValueError, match="enrolled device UUID"):
        load_hardware(file)
    file.write_text('{"mode":"simulation","enable_actuators":true}', encoding="utf-8")
    with pytest.raises(ValueError, match="polarity"):
        load_hardware(file)


def test_simulation_starts_without_device_credential(tmp_path: Path):
    config = Config("https://api.example.test", "https://app.example.test", "KIOSK-A",
                    "SAULI-A", tmp_path / "credential-does-not-exist")
    settings = {"mode": "simulation", "reed_closed_level": {"pocket": 0, "medium": 0},
                "output_active_high": {name: True for name in GPIOController.OUTPUTS}}
    service = HardwareService(config, settings)

    async def exercise():
        task = asyncio.create_task(service.run())
        await asyncio.sleep(0.02)
        assert service.ready is True
        assert service.credential is None
        assert service.backend == "unknown"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(exercise())


def test_reed_changes_are_recorded_after_debounce(tmp_path: Path):
    config = Config("https://api.example.test", "https://app.example.test", "KIOSK-A",
                    "SAULI-A", tmp_path / "credential")
    settings = {"mode": "simulation", "reed_closed_level": {"pocket": 0, "medium": 0},
                "output_active_high": {name: True for name in GPIOController.OUTPUTS}}
    service = HardwareService(config, settings)
    service.gpio.open()
    service.record_door_changes()
    assert service.events == []
    pocket = service.gpio.doors["pocket"]
    pocket.update(0, now=1.0)
    service.record_door_changes()
    assert service.events == []
    pocket.update(0, now=1.1)
    service.record_door_changes()
    assert service.events[0]["kind"] == "pocket_door_closed"


def test_door_workflow_requires_closed_door_and_observes_both_transitions():
    workflow = DoorWorkflow(open_timeout_seconds=2, close_timeout_seconds=5)
    with pytest.raises(ValueError, match="door_not_closed"):
        workflow.start(str(uuid4()), "pocket", "unknown")
    command_id = str(uuid4())
    workflow.start(command_id, "pocket", "closed")
    workflow.pulsing()
    workflow.pulse_finished(now=10)
    assert workflow.observe("closed", now=10.5) is None
    with pytest.raises(ValueError, match="door_workflow_busy"):
        workflow.start(str(uuid4()), "medium", "closed")
    assert workflow.observe("open", now=11) == "workflow_door_opened"
    assert workflow.observe("closed", now=12) == "workflow_door_closed"
    assert workflow.snapshot() == {"command_id": command_id, "door": "pocket",
                                   "phase": "completed", "fault": None}


def test_door_workflow_reports_open_and_close_timeouts():
    workflow = DoorWorkflow(open_timeout_seconds=2, close_timeout_seconds=5)
    workflow.start(str(uuid4()), "medium", "closed")
    workflow.pulse_finished(now=10)
    assert workflow.observe("closed", now=12) == "workflow_open_timeout"
    assert workflow.snapshot()["fault"] == "door_open_timeout"
    workflow.start(str(uuid4()), "medium", "closed")
    workflow.pulse_finished(now=20)
    assert workflow.observe("open", now=21) == "workflow_door_opened"
    assert workflow.observe("open", now=26) == "workflow_close_timeout"
    assert workflow.snapshot()["fault"] == "door_close_timeout"
