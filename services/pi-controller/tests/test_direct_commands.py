"""Mocked GPIO proof for authenticated direct command delivery."""

import asyncio
import base64
import hashlib
import hmac
import json
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
        "direct_completion_queue_file": str(tmp_path / "completions.json"),
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


def command(device_id: str, door: str, operation: str = "deposit") -> dict:
    expires = int((datetime.now(UTC) + timedelta(seconds=60)).timestamp())
    result = {
        "id": str(uuid4()), "device_id": device_id,
        "action": f"pulse_{door}",
        "expires_at": datetime.fromtimestamp(expires, UTC).isoformat(),
        "transport": "direct",
        "assigned_slot": "P-01" if door == "pocket" else "M-01",
        "expected_slots": [
            {"code": f"P-{number:02d}", "present": False} for number in range(1, 9)
        ] + [
            {"code": f"M-{number:02d}", "present": False} for number in range(1, 5)
        ],
    }
    assigned = result["assigned_slot"]
    for row in result["expected_slots"]:
        if row["code"] == assigned:
            row["present"] = operation == "retrieval"
    claims = {
        "v": 1, "jti": result["id"], "device_id": device_id,
        "unit_id": str(uuid4()), "workflow_id": str(uuid4()),
        "operation": operation, "door": door,
        "slot": result["assigned_slot"],
        "expected_slots": result["expected_slots"],
        "iat": int(datetime.now(UTC).timestamp()), "exp": expires,
    }
    encoded = base64.urlsafe_b64encode(json.dumps(
        claims, sort_keys=True, separators=(",", ":")).encode()).rstrip(b"=").decode()
    signature = base64.urlsafe_b64encode(hmac.new(
        TOKEN.encode(), encoded.encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
    result["grant"] = f"{encoded}.{signature}"
    return result


def set_door(service, door: str, state: str) -> None:
    level = 1 if state == "open" else 0
    now = time.monotonic()
    service.gpio.set_simulated_door(door, level)
    service.gpio.doors[door].update(level, now=now)
    service.gpio.doors[door].update(level, now=now + 0.1)
    service.record_door_changes()


def final_telemetry(service, payload: dict, seq: int) -> dict:
    assigned = payload["assigned_slot"]
    initial = {row["code"]: row["present"] for row in payload["expected_slots"]}
    initial[assigned] = not initial[assigned]
    telemetry = {
        "v": 1, "type": "telemetry", "seq": seq, "uptime_ms": 200,
        "slots": [{"code": code, "ready": True, "fault": None,
                   "present": initial[code]} for code in sorted(initial)],
    }
    service.esp.last_seen = time.monotonic()
    service.esp.last_telemetry_at = service.esp.last_seen
    service.esp.telemetry_at = datetime.now(UTC).isoformat()
    service.esp.last_telemetry = telemetry
    return telemetry


def rewrite_grant(payload: dict, **changes) -> dict:
    """Return a command whose grant is validly signed with changed claims."""
    encoded, _signature = payload["grant"].split(".", 1)
    claims = json.loads(base64.urlsafe_b64decode(
        encoded + "=" * (-len(encoded) % 4)))
    claims.update(changes)
    encoded = base64.urlsafe_b64encode(json.dumps(
        claims, sort_keys=True, separators=(",", ":")).encode()).rstrip(b"=").decode()
    signature = base64.urlsafe_b64encode(hmac.new(
        TOKEN.encode(), encoded.encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
    return {**payload, "grant": f"{encoded}.{signature}"}


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


@pytest.mark.parametrize(
    "mutation,expected_code",
    [
        ("invalid_signature", "invalid_unlock_grant"),
        ("expired", "unlock_grant_expired"),
        ("wrong_device", "unlock_grant_claim_mismatch"),
        ("wrong_door", "unlock_grant_claim_mismatch"),
    ],
)
def test_pi_rejects_invalid_unlock_grants_without_gpio(tmp_path, mutation, expected_code):
    device_id = str(uuid4())
    service, _settings = make_service(tmp_path, device_id)
    payload = command(device_id, "pocket")
    if mutation == "invalid_signature":
        payload["grant"] = payload["grant"][:-1] + (
            "A" if payload["grant"][-1] != "A" else "B")
    elif mutation == "expired":
        payload = rewrite_grant(payload, exp=int(datetime.now(UTC).timestamp()) - 1)
    elif mutation == "wrong_device":
        payload = rewrite_grant(payload, device_id=str(uuid4()))
    else:
        payload = rewrite_grant(payload, door="medium")

    result = asyncio.run(service.execute_direct_command(payload))

    assert result["status"] == "failed"
    assert result["code"] == expected_code
    assert service.gpio.outputs["pocket_solenoid"] is False
    assert service.gpio.outputs["medium_solenoid"] is False


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
        await service._refresh_guidance(force=True)
        assert sent[-1]["modes"]["P-01"] == "NORMAL_BLINK"
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
        assert sent[-1]["modes"]["P-01"] == "STEADY_ON"
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


@pytest.mark.parametrize("door,pin", [("pocket", 27), ("medium", 23)])
@pytest.mark.parametrize("operation", ["deposit", "retrieval"])
def test_local_post_close_verification_lowers_correct_gpio_before_backend(
        tmp_path, door, pin, operation):
    service, _settings = make_service(tmp_path, str(uuid4()))
    payload = command(service.settings["device_id"], door, operation)
    if operation == "retrieval":
        next(row for row in service.esp.last_telemetry["slots"]
             if row["code"] == payload["assigned_slot"])["present"] = True
    assert asyncio.run(service.execute_direct_command(payload))["status"] == "acked"
    assert GPIOController.OUTPUTS[f"{door}_solenoid"] == pin
    set_door(service, door, "open")
    assigned = payload["assigned_slot"]
    target = operation == "deposit"

    async def exercise():
        await service._observe_local_presence(assigned, target)
        assert service._local_operation["phase"] == "item_verified"
        set_door(service, door, "closed")
        assert service._local_operation["phase"] == "door_closed"
        assert service.gpio.outputs[f"{door}_solenoid"] is True
        telemetry = final_telemetry(service, payload, seq=2)
        await service._observe_local_telemetry(telemetry)
        assert await service._try_local_completion(telemetry) is True

    asyncio.run(exercise())
    assert service.gpio.outputs[f"{door}_solenoid"] is False
    assert service._local_operation["phase"] == "locally_completed"
    assert service._local_warning_snapshot()["sync_pending"] is True
    assert service._last_unlock["deactivated_at"] is not None
    assert '"local_completion"' in service._completion_queue_file.read_text(encoding="utf-8")


def test_backend_outage_after_local_completion_keeps_gpio_low_and_event_durable(
        tmp_path, monkeypatch):
    service, _settings = make_service(tmp_path, str(uuid4()))
    payload = command(service.settings["device_id"], "pocket")
    asyncio.run(service.execute_direct_command(payload))
    set_door(service, "pocket", "open")

    async def complete():
        await service._observe_local_presence("P-01", True)
        set_door(service, "pocket", "closed")
        telemetry = final_telemetry(service, payload, seq=3)
        await service._observe_local_telemetry(telemetry)
        await service._try_local_completion(telemetry)

    asyncio.run(complete())
    service.credential = "credential"
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
    assert service.gpio.outputs["pocket_solenoid"] is False
    assert any(row.get("durable") for row in service._direct_events)
    restarted, _ = make_service(tmp_path, service.settings["device_id"])
    assert restarted._local_warning_snapshot()["locally_completed"] is True
    assert any(row.get("durable") for row in restarted._direct_events)

    uploads = []

    def synchronized(_origin, path, payload, _credential):
        uploads.append((path, payload))
        return {"phase": "completed", "finalized": True}

    async def discard_uart(_message):
        return None

    monkeypatch.setattr("sauli_pi.hardware_service.request_json", synchronized)
    restarted.credential = "credential"
    restarted.esp.send = discard_uart

    async def synchronize():
        task = asyncio.create_task(restarted._direct_event_loop())
        try:
            async with asyncio.timeout(1):
                while restarted._direct_events:
                    await asyncio.sleep(0.01)
            await asyncio.sleep(0.05)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(synchronize())
    assert len(uploads) == 1
    assert restarted._local_operation is None
    assert json.loads(restarted._completion_queue_file.read_text(encoding="utf-8")) == []


def test_direct_event_uploader_never_calls_backend_while_gate_is_high(
        tmp_path, monkeypatch):
    service, _settings = make_service(tmp_path, str(uuid4()))
    service.credential = "credential"
    payload = command(service.settings["device_id"], "pocket")
    assert asyncio.run(service.execute_direct_command(payload))["status"] == "acked"
    service._direct_events.clear()
    service._queue_direct_event(service._direct_event_snapshot())
    attempts = []

    def record_attempt(*_args):
        attempts.append(True)
        return {"phase": "awaiting_door_open", "finalized": False}

    monkeypatch.setattr("sauli_pi.hardware_service.request_json", record_attempt)

    async def exercise():
        task = asyncio.create_task(service._direct_event_loop())
        try:
            await asyncio.sleep(0.15)
            assert attempts == []
            assert service.gpio.outputs["pocket_solenoid"] is True
            service._abort_workflow("operator_abort")
            async with asyncio.timeout(1):
                while not attempts:
                    await asyncio.sleep(0.01)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(exercise())
    assert service.gpio.outputs["pocket_solenoid"] is False
    assert attempts == [True]


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
    payload = command(device_id, "pocket")
    asyncio.run(service.execute_direct_command(payload))
    set_door(service, "pocket", "open")
    service.esp.last_telemetry["seq"] = 10
    service._direct_events.clear()

    set_door(service, "pocket", "closed")
    service.esp.last_telemetry["seq"] = 11

    queued = service._direct_events[0]["snapshot"]
    assert queued["esp"]["telemetry"]["seq"] == 10
    assert service.snapshot()["esp"]["telemetry"]["seq"] == 11
    assert service._completion_snapshot_pending is True
    assert service._local_operation["close_seq"] == 10


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


def test_pi_restart_requests_identity_from_already_running_esp(tmp_path):
    service, _settings = make_service(tmp_path, str(uuid4()))
    service.esp.serial = None
    service.esp.boot_id = None
    sent = []
    hello_sent = False

    def connect():
        service.esp.serial = object()

    async def send(message):
        sent.append(message)

    async def read():
        nonlocal hello_sent
        if not hello_sent and any(row.get("type") == "identify" for row in sent):
            hello_sent = True
            service.esp.boot_id = "boot-already-running"
            service.esp.last_seen = time.monotonic()
            return [{"v": 1, "type": "hello", "boot_id": "boot-already-running"}]
        await asyncio.sleep(0.01)
        return []

    service.esp.connect = connect
    service.esp.send = send
    service.esp.read = read

    async def exercise():
        task = asyncio.create_task(service._esp_loop())
        try:
            async with asyncio.timeout(1):
                while service.esp.boot_id != "boot-already-running":
                    await asyncio.sleep(0.01)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(exercise())
    assert sent[0] == {"v": 1, "type": "identify"}
    assert service.esp.boot_id == "boot-already-running"


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

