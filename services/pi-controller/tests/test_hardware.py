"""Hardware boundaries must stay deterministic without claiming real pins."""

import asyncio
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from sauli_pi.communication.esp32_serial import EspLink
from sauli_pi.communication.protocol import FrameDecoder, FrameError, encode_frame
from sauli_pi.config import Config
from sauli_pi.hardware.controller import DoorInput, GPIOController
from sauli_pi.hardware_service import (
    HardwareService,
    load_hardware,
    valid_presence_event,
)
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


def test_esp_reboot_invalidates_prior_sensor_snapshot():
    class Frames:
        def __init__(self):
            self.frames = [
                encode_frame({"v": 1, "type": "hello", "boot_id": "boot-a"}) +
                encode_frame({"v": 1, "type": "telemetry", "seq": 7, "slots": []}),
                encode_frame({"v": 1, "type": "hello", "boot_id": "boot-b"}),
            ]

        def read(self, _size):
            return self.frames.pop(0)

    async def exercise():
        link = EspLink()
        link.serial = Frames()
        await link.read()
        assert link.snapshot()["telemetry"] is not None
        assert link.snapshot()["boot_id"] == "boot-a"
        await link.read()
        assert link.snapshot()["telemetry"] is None
        assert link.snapshot()["telemetry_at"] is None
        assert link.snapshot()["boot_id"] == "boot-b"

    asyncio.run(exercise())


@pytest.mark.parametrize("queued_event", [False, True])
def test_reboot_snapshot_reaches_backend_after_queued_presence(monkeypatch, tmp_path: Path,
                                                               queued_event: bool):
    device = str(uuid4())
    config = Config("https://api.example.test", "https://app.example.test", "KIOSK-A",
                    "SAULI-A", tmp_path / "credential")
    settings = {"mode": "real", "device_id": device,
                "reed_closed_level": {"pocket": 0, "medium": 0},
                "output_active_high": {name: True for name in GPIOController.OUTPUTS},
                "enable_actuators": False, "telemetry_interval_seconds": 0.25,
                "telemetry_min_gap_seconds": 0.1}
    service = HardwareService(config, settings)
    service.esp.serial = object()
    service.esp.boot_id = "reboot_2"
    service.esp.last_seen = time.monotonic()
    service.esp.last_telemetry_at = service.esp.last_seen
    service.esp.telemetry_at = datetime.now(UTC).isoformat()
    slots = [{"code": code, "ready": True, "calibrated": True,
              "present": code != "P-01", "fault": None}
             for code in sorted({f"P-{number:02d}" for number in range(1, 9)} |
                                {f"M-{number:02d}" for number in range(1, 5)})]
    service.esp.last_telemetry = {"v": 1, "type": "telemetry", "seq": 1,
                                  "uptime_ms": 500, "slots": slots}
    if queued_event:
        service._pending_presence["reboot_2-1"] = {
            "event_id": "reboot_2-1", "boot_id": "reboot_2", "seq": 1,
            "slot": "P-01", "kind": "SENSOR_SNAPSHOT", "present": False}
    calls = []
    guidance_applied = asyncio.Event()
    modes = {row["code"]: "OFF" for row in slots}
    modes["P-01"] = "SOS_BLINK"

    def fake_request(_origin, path, payload, _credential):
        calls.append((path, payload))
        if path == "/api/hardware/heartbeat":
            return {"commands": [], "guidance": {"modes": modes, "buzzer": True}}
        return {"ok": True}

    async def fake_send(message):
        if message.get("action") == "set_all_lights":
            guidance_applied.set()

    monkeypatch.setattr("sauli_pi.hardware_service.request_json", fake_request)
    service.esp.send = fake_send

    async def exercise():
        publisher = asyncio.create_task(service._publish_loop())
        try:
            await asyncio.wait_for(guidance_applied.wait(), timeout=1)
        finally:
            publisher.cancel()
            await asyncio.gather(publisher, return_exceptions=True)

    asyncio.run(exercise())
    paths = [path for path, _ in calls]
    assert paths == (["/api/hardware/presence"] if queued_event else []) + [
        "/api/hardware/heartbeat"]
    heartbeat = calls[-1][1]["snapshot"]
    assert heartbeat["esp"]["boot_id"] == "reboot_2"
    assert heartbeat["esp"]["connection"] == "online"
    assert heartbeat["esp"]["telemetry"]["slots"] == slots
    assert heartbeat["pending_presence_count"] == 0
    assert not any(service.gpio.outputs.values())


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


def test_led_test_allowlist_pulses_only_selected_solenoid(tmp_path: Path):
    device = str(uuid4())
    config = Config("https://api.example.test", "https://app.example.test", "KIOSK-A",
                    "SAULI-A", tmp_path / "credential")
    settings = {"mode": "real", "device_id": device,
                "reed_closed_level": {"pocket": 0, "medium": 0},
                "output_active_high": {name: True for name in GPIOController.OUTPUTS},
                "enable_actuators": True, "output_polarity_verified": True,
                "solenoid_led_test_channel": "pocket"}
    service = HardwareService(config, settings)
    service.gpio = GPIOController(simulation=True,
                                  closed_level={"pocket": 0, "medium": 0},
                                  active_high={name: True for name in GPIOController.OUTPUTS},
                                  pulse_seconds=0.05, allow_outputs=True)
    service.gpio.open()
    service.gpio.sample_inputs()
    service.gpio.set_simulated_door("pocket", 0)
    service.gpio.doors["pocket"].update(0, now=time.monotonic() + 0.1)
    expiry = (datetime.now(UTC) + timedelta(seconds=5)).isoformat()

    async def exercise():
        denied = await service.handle_command({"id": str(uuid4()), "device_id": device,
                                               "action": "pulse_medium", "expires_at": expiry})
        assert denied["code"] == "test_channel_not_allowed"
        assert not service.gpio.outputs["medium_solenoid"]
        accepted = await service.handle_command({"id": str(uuid4()), "device_id": device,
                                                 "action": "pulse_pocket", "expires_at": expiry})
        assert accepted["code"] == "pulse_completed"
        assert not service.gpio.outputs["pocket_solenoid"]
        assert not service.gpio.outputs["medium_solenoid"]

    asyncio.run(exercise())
    service.gpio.close()


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
        assert service.ready is False
        assert not any(service.gpio.outputs.values())

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


def test_door_open_during_unlock_pulse_is_preserved():
    workflow = DoorWorkflow(open_timeout_seconds=2, close_timeout_seconds=5)
    command_id = str(uuid4())
    workflow.start(command_id, "pocket", "closed")
    workflow.pulsing()
    assert workflow.observe("open", now=10) == "workflow_door_opened"
    workflow.pulse_finished(now=10.2)
    assert workflow.snapshot()["phase"] == "awaiting_close"
    assert workflow.observe("closed", now=11) == "workflow_door_closed"
    assert workflow.snapshot()["command_id"] == command_id


def test_closed_reed_during_unlock_pulse_does_not_timeout():
    workflow = DoorWorkflow(open_timeout_seconds=2, close_timeout_seconds=5)
    workflow.start(str(uuid4()), "pocket", "closed")
    workflow.pulsing()
    assert workflow.observe("closed", now=10) is None
    assert workflow.snapshot()["phase"] == "pulsing"
    workflow.pulse_finished(now=10.2)
    assert workflow.observe("closed", now=10.5) is None
    assert workflow.snapshot()["phase"] == "awaiting_open"


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


def test_timing_config_rejects_invalid_values(tmp_path: Path):
    file = tmp_path / "hardware.json"
    file.write_text('{"mode":"simulation","telemetry_interval_seconds":0}', encoding="utf-8")
    with pytest.raises(ValueError, match="telemetry_interval_seconds"):
        load_hardware(file)
    file.write_text('{"mode":"simulation","telemetry_interval_seconds":0.5,'
                    '"telemetry_min_gap_seconds":0.75}', encoding="utf-8")
    with pytest.raises(ValueError, match="cannot exceed"):
        load_hardware(file)
    file.write_text('{"mode":"simulation"}', encoding="utf-8")
    assert load_hardware(file)["telemetry_interval_seconds"] == 0.5


def test_gpio_and_workflow_continue_during_blocked_heartbeat(monkeypatch, tmp_path: Path):
    config = Config("https://api.example.test", "https://app.example.test", "KIOSK-A",
                    "SAULI-A", tmp_path / "credential")
    settings = {"mode": "simulation", "reed_closed_level": {"pocket": 0, "medium": 0},
                "output_active_high": {name: True for name in GPIOController.OUTPUTS},
                "gpio_sample_seconds": 0.02, "telemetry_interval_seconds": 0.05,
                "telemetry_min_gap_seconds": 0.02}
    service = HardwareService(config, settings)
    started = threading.Event()
    release = threading.Event()
    active = 0
    maximum = 0
    calls = []

    def slow_request(_origin, path, payload, _credential):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        calls.append((path, payload))
        started.set()
        release.wait(timeout=2)
        active -= 1
        return {"commands": []}

    monkeypatch.setattr("sauli_pi.hardware_service.request_json", slow_request)

    async def exercise():
        service.gpio.open()
        level = [0]
        service.gpio.sample_inputs = lambda: service.gpio.doors["pocket"].update(level[0])
        service.gpio.doors["pocket"].update(0, now=time.monotonic() - 1)
        service.gpio.sample_inputs()
        service.record_door_changes()
        service.door_workflow.start("test-command", "pocket", "closed")
        service.door_workflow.pulse_finished()
        sampler = asyncio.create_task(service._sample_loop())
        publisher = asyncio.create_task(service._publish_loop())
        try:
            assert await asyncio.to_thread(started.wait, 1)
            level[0] = 1
            deadline = time.monotonic() + 0.5
            while service.door_workflow.snapshot()["phase"] != "awaiting_close" and time.monotonic() < deadline:
                await asyncio.sleep(0.01)
            assert service.door_workflow.snapshot()["phase"] == "awaiting_close"
            assert any(event["kind"] == "pocket_door_open" for event in service.events)
            # A blocked backend cannot cause a second in-flight request.
            assert maximum == 1
            service.door_workflow.deadline = time.monotonic() - 1
            deadline = time.monotonic() + 0.2
            while service.door_workflow.snapshot()["phase"] != "fault" and time.monotonic() < deadline:
                await asyncio.sleep(0.01)
            assert service.door_workflow.snapshot()["fault"] == "door_close_timeout"
            release.set()
            await asyncio.sleep(0.1)
            assert any(event["kind"] == "workflow_door_opened" for event in service.events)
            assert any(any(e["kind"] == "pocket_door_open" for e in call[1]["snapshot"]["events"])
                       for call in calls if call[0] == "/api/hardware/heartbeat")
        finally:
            release.set()
            sampler.cancel()
            publisher.cancel()
            await asyncio.gather(sampler, publisher, return_exceptions=True)
            service.gpio.close()

    asyncio.run(exercise())
    assert maximum == 1


def test_failed_ack_is_retried_without_reexecuting_command(monkeypatch, tmp_path: Path):
    config = Config("https://api.example.test", "https://app.example.test", "KIOSK-A",
                    "SAULI-A", tmp_path / "credential")
    settings = {"mode": "simulation", "reed_closed_level": {"pocket": 0, "medium": 0},
                "output_active_high": {name: True for name in GPIOController.OUTPUTS},
                "telemetry_interval_seconds": 0.05, "telemetry_min_gap_seconds": 0.02}
    service = HardwareService(config, settings)
    commands = [
        {"id": str(uuid4()), "created_at": "2026-11-09T12:00:02Z"},
        {"id": str(uuid4()), "created_at": "2026-11-09T12:00:01Z"},
    ]
    requests = []
    executions = []

    def fake_request(_origin, path, _payload, _credential):
        requests.append(path)
        if path == "/api/hardware/heartbeat":
            return {"commands": commands if requests.count(path) == 1 else []}
        if requests.count("/api/hardware/ack") == 1:
            from sauli_pi.communication.backend_client import DeviceApiError
            raise DeviceApiError("temporary failure")
        return {"ok": True}

    async def fake_command(row):
        executions.append(row["id"])
        return {"id": row["id"], "status": "acked", "code": "pulse_completed"}

    monkeypatch.setattr("sauli_pi.hardware_service.request_json", fake_request)
    service.handle_command = fake_command

    async def exercise():
        task = asyncio.create_task(service._publish_loop())
        await asyncio.sleep(1.2)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(exercise())
    assert executions == [row["id"] for row in reversed(commands)]
    assert requests[:5] == ["/api/hardware/heartbeat", "/api/hardware/ack",
                            "/api/hardware/ack", "/api/hardware/ack", "/api/hardware/heartbeat"]


def test_silent_esp_read_does_not_block_gpio_sampling(tmp_path: Path):
    config = Config("https://api.example.test", "https://app.example.test", "KIOSK-A",
                    "SAULI-A", tmp_path / "credential")
    settings = {"mode": "real", "reed_closed_level": {"pocket": 0, "medium": 0},
                "output_active_high": {name: True for name in GPIOController.OUTPUTS},
                "gpio_sample_seconds": 0.02}
    service = HardwareService(config, settings)
    service.esp.serial = object()
    reads = 0
    samples = 0

    async def silent_read():
        nonlocal reads
        reads += 1
        await asyncio.sleep(0.25)
        return []

    async def silent_send(_message):
        return None

    def sample():
        nonlocal samples
        samples += 1

    service.esp.read = silent_read
    service.esp.send = silent_send
    service.gpio.sample_inputs = sample

    async def exercise():
        sampler = asyncio.create_task(service._sample_loop())
        serial = asyncio.create_task(service._esp_loop())
        await asyncio.sleep(0.12)
        sampler.cancel()
        serial.cancel()
        await asyncio.gather(sampler, serial, return_exceptions=True)

    asyncio.run(exercise())
    assert reads == 1
    assert samples >= 4


def test_invalid_esp_presence_does_not_enter_backend_retry_queue(tmp_path: Path):
    config = Config("https://api.example.test", "https://app.example.test", "KIOSK-A",
                    "SAULI-A", tmp_path / "credential")
    settings = {"mode": "simulation", "reed_closed_level": {"pocket": 0, "medium": 0},
                "output_active_high": {name: True for name in GPIOController.OUTPUTS}}
    service = HardwareService(config, settings)
    service.esp.serial = object()
    invalid = {"v": 1, "type": "event", "event_id": "boot-1", "boot_id": "boot",
               "seq": 1, "slot": "P-01", "kind": "ITEM_REMOVED", "present": True}
    valid = {**invalid, "event_id": "boot-2", "seq": 2, "slot": "P-02",
             "kind": "ITEM_PRESENT"}
    assert valid_presence_event(invalid) is False
    assert valid_presence_event({**valid, "seq": True}) is False
    assert valid_presence_event({**valid, "slot": "P-99"}) is False
    assert valid_presence_event(valid) is True
    sent = []
    reads = 0

    async def read():
        nonlocal reads
        reads += 1
        return [invalid, valid] if reads == 1 else []

    async def send(message):
        sent.append(message)

    service.esp.read = read
    service.esp.send = send

    async def exercise():
        task = asyncio.create_task(service._esp_loop())
        await asyncio.sleep(0.08)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(exercise())
    assert list(service._pending_presence) == ["boot-2"]
    assert {"v": 1, "type": "event_ack", "event_id": "boot-1"} in sent
    assert {"v": 1, "type": "snapshot"} in sent


def test_guidance_clears_lights_and_buzzer_on_invalid_or_lost_backend(tmp_path: Path):
    config = Config("https://api.example.test", "https://app.example.test", "KIOSK-A",
                    "SAULI-A", tmp_path / "credential")
    settings = {"mode": "simulation", "reed_closed_level": {"pocket": 0, "medium": 0},
                "output_active_high": {name: True for name in GPIOController.OUTPUTS},
                "enable_actuators": True}
    service = HardwareService(config, settings)
    service.gpio.allow_outputs = True
    service.esp.serial = object()
    sent = []

    async def send(message):
        sent.append(message)

    service.esp.send = send
    modes = {f"P-{number:02d}": "OFF" for number in range(1, 9)}
    modes.update({f"M-{number:02d}": "OFF" for number in range(1, 5)})
    modes["P-01"] = "NORMAL_BLINK"
    modes["P-02"] = "SOS_BLINK"

    async def exercise():
        await service._apply_guidance({"modes": modes, "buzzer": True})
        assert service.gpio.outputs["buzzer"] is True
        assert sent[-1]["modes"] == modes
        wrong_slot_modes = {**modes, "P-01": "OFF", "P-99": "SOS_BLINK"}
        wrong_slot_modes.pop("P-02")
        await service._apply_guidance({"modes": wrong_slot_modes, "buzzer": True})
        assert service.gpio.outputs["buzzer"] is False
        assert set(sent[-1]["modes"].values()) == {"OFF"}
        await service._apply_guidance({"modes": modes, "buzzer": True})
        await service._apply_guidance({"modes": {"P-01": "STEADY_ON"}})
        assert service.gpio.outputs["buzzer"] is False
        assert set(sent[-1]["modes"].values()) == {"OFF"}
        assert len(sent[-1]["modes"]) == 12
        await service._apply_guidance({"modes": modes, "buzzer": True})
        await service._clear_guidance()
        assert sent[-1]["modes"]["P-02"] == "OFF"

    asyncio.run(exercise())
