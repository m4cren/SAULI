"""Mocked GPIO proof for authenticated direct command delivery."""

import asyncio
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from sauli_pi.config import Config
from sauli_pi.hardware.controller import GPIOController
from sauli_pi.hardware_service import HardwareService, create_app


TOKEN = "direct-test-token-with-at-least-32-characters"


def make_service(tmp_path, device_id: str, *, mismatch: bool = False):
    config = Config("https://api.example.test", "https://app.example.test",
                    "KIOSK-A", "SAULI-A", tmp_path / "credential")
    settings = {
        "mode": "real", "command_transport": "direct", "device_id": device_id,
        "direct_api_token": TOKEN,
        "direct_replay_file": str(tmp_path / "replay.json"),
        "direct_incident_queue_file": str(tmp_path / "incidents.json"),
        "reed_closed_level": {"pocket": 0, "medium": 0},
        "output_active_high": {name: True for name in GPIOController.OUTPUTS},
        "enable_actuators": True, "output_polarity_verified": True,
    }
    service = HardwareService(config, settings)
    service.gpio = GPIOController(
        simulation=True, closed_level={"pocket": 0, "medium": 0},
        active_high={name: True for name in GPIOController.OUTPUTS},
        max_hold_seconds=300, allow_outputs=True,
    )
    service.gpio.open()
    for door in ("pocket", "medium"):
        service.gpio.set_simulated_door(door, 0)
        service.gpio.doors[door].update(0, now=time.monotonic() + 0.1)
    service.ready = True
    service.esp.serial = object()
    service.esp.boot_id = "boot-direct"
    service.esp.last_seen = time.monotonic()
    service.esp.last_telemetry_at = service.esp.last_seen
    service.esp.telemetry_at = datetime.now(UTC).isoformat()
    slots = [
        {"code": f"P-{number:02d}", "ready": True, "fault": None,
         "present": mismatch and number == 1}
        for number in range(1, 9)
    ] + [
        {"code": f"M-{number:02d}", "ready": True, "fault": None,
         "present": False}
        for number in range(1, 5)
    ]
    service.esp.last_telemetry = {
        "v": 1, "type": "telemetry", "seq": 1,
        "uptime_ms": 100, "slots": slots,
    }
    return service, settings


def command(device_id: str, door: str) -> dict:
    return {
        "id": str(uuid4()), "device_id": device_id,
        "action": f"pulse_{door}",
        "expires_at": (datetime.now(UTC) + timedelta(seconds=10)).isoformat(),
        "transport": "direct",
        "assigned_slot": "P-01" if door == "pocket" else "M-01",
        "expected_slots": [
            {"code": f"P-{number:02d}", "present": False} for number in range(1, 9)
        ] + [
            {"code": f"M-{number:02d}", "present": False} for number in range(1, 5)
        ],
    }


async def capture_guidance(service):
    sent = []

    async def send(message):
        sent.append(message)

    service.esp.send = send
    return sent


@pytest.mark.parametrize("door,pin", [("pocket", 27), ("medium", 23)])
def test_authorized_direct_unlock_holds_exact_gpio_once(tmp_path, door, pin):
    device_id = str(uuid4())
    service, _settings = make_service(tmp_path, device_id)
    payload = command(device_id, door)

    async def exercise():
        first = await service.execute_direct_command(payload)
        await asyncio.sleep(0.4)
        second = await service.execute_direct_command(payload)
        return first, second

    first, second = asyncio.run(exercise())
    assert first == second
    assert first["status"] == "acked"
    assert first["code"] == "unlock_held"
    assert GPIOController.OUTPUTS[f"{door}_solenoid"] == pin
    assert service.gpio.outputs[f"{door}_solenoid"] is True
    other = "medium" if door == "pocket" else "pocket"
    assert service.gpio.outputs[f"{other}_solenoid"] is False
    assert service._last_unlock["deactivated_at"] is None


def test_direct_endpoint_rejects_unauthenticated_command(tmp_path):
    device_id = str(uuid4())
    service, settings = make_service(tmp_path, device_id)
    app = create_app(service.config, settings)
    app.state_service = service
    with TestClient(app) as client:
        response = client.post("/v1/commands", json=command(device_id, "pocket"))
    assert response.status_code == 403


def test_direct_unlock_rejects_unsafe_sensor_state_without_pulse(tmp_path):
    device_id = str(uuid4())
    service, _settings = make_service(tmp_path, device_id, mismatch=True)
    result = asyncio.run(service.execute_direct_command(command(device_id, "pocket")))
    assert result["status"] == "failed"
    assert result["code"] == "sensor_state_mismatch"
    assert not service.gpio.outputs["pocket_solenoid"]


def test_delayed_manual_open_recovers_without_releasing_gpio27(tmp_path):
    service, _settings = make_service(tmp_path, str(uuid4()))
    payload = command(service.settings["device_id"], "pocket")
    assert asyncio.run(service.execute_direct_command(payload))["status"] == "acked"
    service.door_workflow.deadline = time.monotonic() - 1
    assert service.door_workflow.observe("closed") == "workflow_open_timeout"
    assert service.door_workflow.phase == "awaiting_open"
    assert service.door_workflow.fault is None
    assert service.gpio.outputs["pocket_solenoid"] is True
    assert service.door_workflow.observe("open") == "workflow_door_opened"
    assert service.door_workflow.phase == "awaiting_close"
    assert service.gpio.outputs["pocket_solenoid"] is True


def test_local_deposit_success_is_provisional_and_reversal_warns_until_corrected(
        tmp_path):
    service, _settings = make_service(tmp_path, str(uuid4()))
    payload = command(service.settings["device_id"], "pocket")
    assert asyncio.run(service.execute_direct_command(payload))["code"] == "unlock_held"
    assert service.gpio.outputs["pocket_solenoid"] is True

    async def exercise():
        sent = await capture_guidance(service)
        await service._observe_local_presence("P-01", True)
        assert service._local_warning_snapshot()["provisional_success"] is True
        assert service._local_violations == {}
        assert service.gpio.outputs["pocket_solenoid"] is True
        await service._observe_local_presence("P-01", False)
        assert service._local_violations == {"P-01": "wrong_removal"}
        assert service.gpio.outputs["buzzer"] is True
        assert sent[-1]["modes"]["P-01"] == "SOS_BLINK"
        service.event("workflow_door_closed", payload["id"])
        assert service.gpio.outputs["pocket_solenoid"] is True
        assert service._local_violations == {"P-01": "wrong_removal"}
        await service._observe_local_presence("P-01", True)
        assert service._local_violations == {}
        assert service.gpio.outputs["buzzer"] is False
        assert sent[-1]["modes"]["P-01"] == "OFF"
        assert service.gpio.outputs["pocket_solenoid"] is True

    asyncio.run(exercise())
    updates = [row["snapshot"]["local_incident_updates"]
               for row in service._security_events]
    assert updates == [
        [{"slot": "P-01", "kind": "wrong_removal", "active": True}],
        [{"slot": "P-01", "kind": "wrong_removal", "active": False}],
    ]


def test_local_retrieval_reversal_and_multiple_wrong_slots_clear_independently(
        tmp_path):
    service, _settings = make_service(tmp_path, str(uuid4()))
    payload = command(service.settings["device_id"], "pocket")
    payload["expected_slots"][0]["present"] = True
    payload["expected_slots"][8]["present"] = True
    service._start_local_operation(payload)

    async def exercise():
        sent = await capture_guidance(service)
        await service._observe_local_presence("P-01", False)
        assert service._local_provisional is True
        await service._observe_local_presence("P-01", True)
        await service._observe_local_presence("P-02", True)
        await service._observe_local_presence("M-01", False)
        assert service._local_violations == {
            "P-01": "wrong_placement", "P-02": "wrong_placement",
            "M-01": "wrong_removal",
        }
        assert all(sent[-1]["modes"][slot] == "SOS_BLINK"
                   for slot in ("P-01", "P-02", "M-01"))
        await service._observe_local_presence("P-02", False)
        assert "P-02" not in service._local_violations
        assert set(service._local_violations) == {"P-01", "M-01"}
        await service._observe_local_presence("M-01", True)
        await service._observe_local_presence("P-01", False)
        assert service._local_violations == {}
        assert service._local_provisional is True

    asyncio.run(exercise())


def test_local_security_queue_survives_backend_outage(tmp_path, monkeypatch):
    service, _settings = make_service(tmp_path, str(uuid4()))
    payload = command(service.settings["device_id"], "pocket")
    service._start_local_operation(payload)
    service.credential = "credential"

    async def prepare():
        await capture_guidance(service)
        await service._observe_local_presence("P-02", True)

    asyncio.run(prepare())
    persisted = service._incident_queue_file.read_text(encoding="utf-8")
    assert '"wrong_placement"' in persisted

    attempts = []

    def unavailable(*_args):
        attempts.append(True)
        raise OSError("backend unavailable")

    monkeypatch.setattr("sauli_pi.hardware_service.request_json", unavailable)

    async def exercise():
        task = asyncio.create_task(service._direct_event_loop())
        try:
            async with asyncio.timeout(1):
                while not attempts:
                    await asyncio.sleep(0.01)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(exercise())
    assert len(service._security_events) == 1
    assert service._local_violations == {"P-02": "wrong_placement"}
    assert service.gpio.outputs["buzzer"] is True


def test_backend_finalization_ends_local_monitor_only_after_confirmation(
        tmp_path, monkeypatch):
    service, _settings = make_service(tmp_path, str(uuid4()))
    payload = command(service.settings["device_id"], "pocket")
    result = asyncio.run(service.execute_direct_command(payload))
    assert result["code"] == "unlock_held"
    assert service.gpio.outputs["pocket_solenoid"] is True
    service.event("workflow_door_closed", payload["id"])
    assert service._awaiting_backend_finalization is True
    assert service._local_warning_snapshot()["finalization_error"] == "FINALIZATION_PENDING"
    service.credential = "credential"

    def completed(*_args):
        return {"phase": "completed", "finalized": True, "guidance": {}}

    monkeypatch.setattr("sauli_pi.hardware_service.request_json", completed)

    async def exercise():
        await capture_guidance(service)
        task = asyncio.create_task(service._direct_event_loop())
        try:
            async with asyncio.timeout(1):
                while service._direct_events:
                    await asyncio.sleep(0.01)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(exercise())
    assert service._local_warning_snapshot()["monitoring"] is False
    assert service.gpio.outputs["pocket_solenoid"] is False
    assert service._last_unlock["deactivated_at"] is not None


def test_failed_finalization_keeps_unlock_held_and_reports_error(
        tmp_path, monkeypatch):
    service, _settings = make_service(tmp_path, str(uuid4()))
    payload = command(service.settings["device_id"], "medium")
    assert asyncio.run(service.execute_direct_command(payload))["code"] == "unlock_held"
    service._awaiting_backend_finalization = True
    service._direct_events.append({"presence": None,
                                   "snapshot": service._direct_event_snapshot()})
    service.credential = "credential"

    def pending(*_args):
        return {"phase": "awaiting_door_close", "finalized": False,
                "reason": "SENSOR_DATA_INCOMPLETE", "guidance": {}}

    monkeypatch.setattr("sauli_pi.hardware_service.request_json", pending)

    async def exercise():
        await capture_guidance(service)
        task = asyncio.create_task(service._direct_event_loop())
        try:
            async with asyncio.timeout(1):
                while service._direct_events:
                    await asyncio.sleep(0.01)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(exercise())
    assert service.gpio.outputs["medium_solenoid"] is True
    assert service._local_warning_snapshot()["monitoring"] is True
    assert service._local_warning_snapshot()["finalization_error"] == "SENSOR_DATA_INCOMPLETE"


def test_definitive_finalization_failure_releases_output_without_false_success(
        tmp_path, monkeypatch):
    service, _settings = make_service(tmp_path, str(uuid4()))
    payload = command(service.settings["device_id"], "pocket")
    assert asyncio.run(service.execute_direct_command(payload))["status"] == "acked"
    service.event("workflow_door_closed", payload["id"])
    service.credential = "credential"

    def rejected(*_args):
        return {"phase": "requires_review", "finalized": False,
                "reason": "ASSIGNED_SLOT_FINAL_STATE_MISMATCH", "guidance": {}}

    monkeypatch.setattr("sauli_pi.hardware_service.request_json", rejected)

    async def exercise():
        await capture_guidance(service)
        task = asyncio.create_task(service._direct_event_loop())
        try:
            async with asyncio.timeout(1):
                while service._direct_events:
                    await asyncio.sleep(0.01)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(exercise())
    assert service.gpio.outputs["pocket_solenoid"] is False
    assert service.door_workflow.phase == "fault"
    assert service._local_warning_snapshot()["monitoring"] is True
    assert service._local_warning_snapshot()["finalization_error"] == (
        "ASSIGNED_SLOT_FINAL_STATE_MISMATCH")


def test_solenoid_hold_limit_aborts_safely_and_closed_retry_can_reauthorize(tmp_path):
    service, _settings = make_service(tmp_path, str(uuid4()))
    payload = command(service.settings["device_id"], "pocket")
    assert asyncio.run(service.execute_direct_command(payload))["status"] == "acked"
    service.gpio._solenoid_started["pocket"] = time.monotonic() - 301
    assert service.gpio.hold_limit_exceeded("pocket") is True
    service._abort_workflow("solenoid_hold_timeout")
    assert service.gpio.outputs["pocket_solenoid"] is False
    assert service.door_workflow.fault == "solenoid_hold_timeout"
    retry = command(service.settings["device_id"], "pocket")
    assert asyncio.run(service.execute_direct_command(retry))["status"] == "acked"
    assert service.gpio.outputs["pocket_solenoid"] is True


def test_close_event_freezes_pre_close_telemetry_for_freshness_proof(tmp_path):
    device_id = str(uuid4())
    service, _settings = make_service(tmp_path, device_id)
    service.esp.last_telemetry["seq"] = 10
    service._direct_events.clear()

    service.event("workflow_door_closed", str(uuid4()))
    service.esp.last_telemetry["seq"] = 11

    queued = service._direct_events[0]["snapshot"]
    assert queued["esp"]["telemetry"]["seq"] == 10
    assert service.snapshot()["esp"]["telemetry"]["seq"] == 11
    assert service._completion_snapshot_pending is True


def test_post_close_snapshot_recovers_with_new_esp_boot_id(tmp_path):
    device_id = str(uuid4())
    service, _settings = make_service(tmp_path, device_id)
    service._direct_events.clear()
    # A Pi restart loses the in-memory post-close flag. Direct mode's one-shot
    # boot recovery snapshot must still reach reconciliation.
    service._completion_snapshot_pending = False
    service._boot_recovery_snapshot_pending = True
    batches = ["hello", "telemetry"]
    sent = []

    async def read():
        if not batches:
            await asyncio.sleep(0.01)
            return []
        kind = batches.pop(0)
        service.esp.last_seen = time.monotonic()
        if kind == "hello":
            service.esp.boot_id = "boot-recovered"
            service.esp.last_telemetry = None
            service.esp.last_telemetry_at = 0
            service.esp.telemetry_at = None
            return [{"v": 1, "type": "hello", "boot_id": "boot-recovered"}]
        service.esp.last_telemetry = {
            "v": 1, "type": "telemetry", "seq": 1,
            "uptime_ms": 10, "slots": [],
        }
        service.esp.last_telemetry_at = service.esp.last_seen
        service.esp.telemetry_at = datetime.now(UTC).isoformat()
        return [service.esp.last_telemetry]

    async def send(message):
        sent.append(message)

    service.esp.read = read
    service.esp.send = send

    async def exercise():
        task = asyncio.create_task(service._esp_loop())
        try:
            async with asyncio.timeout(1):
                while not service._direct_events:
                    await asyncio.sleep(0.01)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(exercise())
    queued = service._direct_events[0]["snapshot"]
    assert queued["esp"]["boot_id"] == "boot-recovered"
    assert queued["esp"]["telemetry"]["seq"] == 1
    assert service._completion_snapshot_pending is False
    assert service._boot_recovery_snapshot_pending is False
    assert any(message["type"] == "snapshot" for message in sent)


def test_failed_finalization_requests_another_fresh_esp_snapshot(
        monkeypatch, tmp_path):
    device_id = str(uuid4())
    service, _settings = make_service(tmp_path, device_id)
    service.credential = "device-credential"
    service._direct_events.append({"presence": None,
                                   "snapshot": service._direct_event_snapshot()})
    sent = []

    def request(_origin, path, _payload, _credential):
        assert path == "/api/hardware/workflow-event"
        return {"phase": "awaiting_door_close", "finalized": False,
                "needs_fresh_snapshot": True, "guidance": {}}

    async def send(message):
        sent.append(message)

    monkeypatch.setattr("sauli_pi.hardware_service.request_json", request)
    service.esp.send = send

    async def exercise():
        task = asyncio.create_task(service._direct_event_loop())
        try:
            async with asyncio.timeout(1):
                while service._direct_events:
                    await asyncio.sleep(0.01)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(exercise())
    assert service._completion_snapshot_pending is True
    assert {"v": 1, "type": "snapshot"} in sent


def test_direct_workflow_events_are_delivered_in_frozen_fifo_order(
        monkeypatch, tmp_path):
    device_id = str(uuid4())
    service, _settings = make_service(tmp_path, device_id)
    service.credential = "device-credential"
    service._direct_events.clear()
    command_id = str(uuid4())
    service.esp.last_telemetry["seq"] = 20
    service.event("workflow_door_opened", command_id)
    service.esp.last_telemetry["seq"] = 21
    service.event("workflow_door_closed", command_id)
    delivered = []

    def request(_origin, _path, payload, _credential):
        delivered.append(payload["snapshot"])
        return {"phase": "door_open", "finalized": False, "guidance": {}}

    monkeypatch.setattr("sauli_pi.hardware_service.request_json", request)

    async def exercise():
        task = asyncio.create_task(service._direct_event_loop())
        try:
            async with asyncio.timeout(1):
                while service._direct_events:
                    await asyncio.sleep(0.01)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(exercise())
    assert [snapshot["esp"]["telemetry"]["seq"] for snapshot in delivered] == [20, 21]
    assert delivered[0]["events"][0]["kind"] == "workflow_door_opened"
    assert delivered[1]["events"][0]["kind"] == "workflow_door_closed"

