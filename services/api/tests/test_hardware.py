"""Hardware telemetry is device scoped; public diagnostics are read only."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.auth.kiosk import get_device, get_kiosk_session
from app.config import Settings
from app.core.errors import ServiceError
from app.main import create_app
from app.repositories.supabase_kiosks import SupabaseKioskRepository
from app.routes.hardware import HardwareSnapshot

WORKFLOW_MIGRATION = (Path(__file__).resolve().parents[3]
                      / "supabase/migrations/202611110002_sauli_workflow_unlock_and_incident_corrections.sql")
PRESENCE_MIGRATION = (Path(__file__).resolve().parents[3]
                      / "supabase/migrations/202611090001_sauli_hardware_presence.sql")


def snapshot():
    return {"pi": {"mode": "real", "doors": {
        "medium": {"raw_level": 1, "door": "open"},
        "pocket": {"raw_level": 0, "door": "closed"}},
        "outputs": {name: False for name in (
            "main_light", "buzzer", "medium_solenoid", "pocket_solenoid",
            "pocket_light_gate", "medium_light_gate")},
        "lock_feedback": "unavailable"},
        "esp": {"connection": "offline", "telemetry": None}}


def test_legacy_heartbeat_preserves_unknown_pending_queue():
    assert HardwareSnapshot.model_validate(snapshot()).pending_presence_count is None
    assert HardwareSnapshot.model_validate({
        **snapshot(), "pending_presence_count": 0,
    }).pending_presence_count == 0


def test_hardware_heartbeat_rejects_anonymous_and_simulated_payload():
    app = create_app(Settings(supabase_url=None, supabase_service_role_key=None, emailjs_enabled=False))
    with TestClient(app) as client:
        assert client.post("/api/hardware/heartbeat", json={"snapshot": snapshot()}).status_code == 403
    app.dependency_overrides[get_device] = lambda: {"id": str(uuid4()), "unit_id": str(uuid4())}
    with TestClient(app) as client:
        data = snapshot()
        data["pi"]["mode"] = "simulation"
        assert client.post("/api/hardware/heartbeat", json={"snapshot": data}).status_code == 422


def test_authenticated_heartbeat_uses_bound_device_and_strips_untrusted_fields():
    device = {"id": str(uuid4()), "unit_id": str(uuid4())}
    app = create_app(Settings(supabase_url=None, supabase_service_role_key=None, emailjs_enabled=False))
    app.dependency_overrides[get_device] = lambda: device

    class Kiosks:
        async def hardware_heartbeat(self, incoming, data):
            assert incoming == device
            assert "secret" not in data
            assert data["sequence"] == 42
            assert data["observed_at"] == "2026-11-07T12:00:00Z"
            assert data["pi"]["lock_feedback"] == "unavailable"
            assert data["events"][0]["kind"] == "command_completed"
            assert "private_note" not in data["events"][0]
            assert data["esp"]["boot_id"] == "boot_123"
            assert data["esp"]["telemetry_at"] == "2026-11-07T12:00:00Z"
            assert data["pending_presence_count"] == 2

        async def claim_hardware_commands(self, incoming):
            assert incoming == device
            return []

        async def hardware_guidance(self, incoming):
            assert incoming == device
            return {"modes": {"P-01": "OFF"}, "buzzer": False}

    app.state.kiosks = Kiosks()
    data = snapshot()
    data["secret"] = "must-be-dropped"
    data["sequence"] = 42
    data["observed_at"] = "2026-11-07T12:00:00Z"
    data["esp"]["boot_id"] = "boot_123"
    data["esp"]["telemetry_at"] = "2026-11-07T12:00:00Z"
    data["pending_presence_count"] = 2
    data["events"] = [{"at": "2026-11-07T12:00:00Z", "kind": "command_completed",
                       "command_id": str(uuid4()), "private_note": "must-be-dropped"}]
    with TestClient(app) as client:
        response = client.post("/api/hardware/heartbeat", json={"snapshot": data})
    assert response.status_code == 200
    assert response.json() == {"device_id": device["id"], "commands": [],
                               "guidance": {"modes": {"P-01": "OFF"}, "buzzer": False}}


def test_fresh_reboot_snapshot_is_reconciled_before_alarm_guidance():
    device = {"id": str(uuid4()), "unit_id": str(uuid4())}
    app = create_app(Settings(supabase_url=None, supabase_service_role_key=None, emailjs_enabled=False))
    app.dependency_overrides[get_device] = lambda: device
    calls = []
    slots = [
        {"code": code, "ready": True, "calibrated": True,
         "present": code != "P-01", "fault": None}
        for code in [*(f"P-{number:02d}" for number in range(1, 9)),
                     *(f"M-{number:02d}" for number in range(1, 5))]
    ]

    class Kiosks:
        async def hardware_heartbeat(self, incoming, data):
            calls.append("reconcile")
            assert incoming == device
            assert data["esp"]["boot_id"] == "reboot_2"
            assert data["esp"]["connection"] == "online"
            observed = data["esp"]["telemetry"]["slots"]
            assert len(observed) == 12
            assert [(row["code"], row["present"], row["ready"]) for row in observed] == [
                (row["code"], row["present"], row["ready"]) for row in slots]
            assert data["pending_presence_count"] == 0

        async def claim_hardware_commands(self, incoming):
            calls.append("claim")
            assert incoming == device
            return []

        async def hardware_guidance(self, incoming):
            calls.append("guidance")
            assert incoming == device
            return {"modes": {"P-01": "SOS_BLINK"}, "buzzer": True}

    app.state.kiosks = Kiosks()
    data = snapshot()
    data["esp"] = {"connection": "online", "boot_id": "reboot_2",
                   "telemetry_at": datetime.now(UTC).isoformat(),
                   "telemetry": {"v": 1, "type": "telemetry", "seq": 1,
                                 "uptime_ms": 500, "slots": slots}}
    data["pending_presence_count"] = 0
    with TestClient(app) as client:
        response = client.post("/api/hardware/heartbeat", json={"snapshot": data})
    assert response.status_code == 200
    assert calls == ["reconcile", "guidance", "claim"]
    assert response.json()["guidance"] == {"modes": {"P-01": "SOS_BLINK"}, "buzzer": True}


def test_guidance_outage_does_not_claim_an_unlock_command():
    device = {"id": str(uuid4()), "unit_id": str(uuid4())}
    app = create_app(Settings(supabase_url=None, supabase_service_role_key=None, emailjs_enabled=False))
    app.dependency_overrides[get_device] = lambda: device
    calls = []

    class Kiosks:
        async def hardware_heartbeat(self, incoming, _snapshot):
            assert incoming == device
            calls.append("reconcile")

        async def hardware_guidance(self, incoming):
            assert incoming == device
            calls.append("guidance")
            raise ServiceError("SUPABASE_UNAVAILABLE", "Hardware service is unavailable.", 503)

        async def claim_hardware_commands(self, _incoming):
            calls.append("claim")
            return [{"id": str(uuid4()), "kind": "unlock"}]

    app.state.kiosks = Kiosks()
    with TestClient(app) as client:
        response = client.post("/api/hardware/heartbeat", json={"snapshot": snapshot()})
    assert response.status_code == 503
    assert calls == ["reconcile", "guidance"]


def test_hardware_guidance_retries_read_error_without_replaying_commands(monkeypatch):
    monkeypatch.setattr("app.repositories.supabase_kiosks.time.sleep", lambda _seconds: None)
    unit_id = str(uuid4())

    class Client:
        calls = 0
        fail_until = 2

        def rpc(self, name, params):
            assert name == "sauli_hardware_guidance"
            assert params == {"p_unit_id": unit_id}
            return self

        def execute(self):
            self.calls += 1
            if self.calls <= self.fail_until:
                raise httpx.ReadError("connection reset")
            return SimpleNamespace(data={"modes": {"P-01": "NORMAL_BLINK"}, "buzzer": False})

    repo = SupabaseKioskRepository(items=None)
    client = Client()
    repo.client = lambda: client
    assert asyncio.run(repo.hardware_guidance({"unit_id": unit_id}))["buzzer"] is False
    assert client.calls == 3

    client = Client()
    client.fail_until = 3
    repo.client = lambda: client
    with pytest.raises(ServiceError) as error:
        asyncio.run(repo.hardware_guidance({"unit_id": unit_id}))
    assert error.value.code == "SUPABASE_UNAVAILABLE"
    assert error.value.status_code == 503
    assert client.calls == 3


def test_reboot_snapshot_sql_detects_both_mismatches_before_idle_and_deduplicates():
    sql = WORKFLOW_MIGRATION.read_text(encoding="utf-8").lower()
    reconcile = sql.split("create or replace function public.sauli_reconcile_hardware_workflow", 1)[1]
    before_idle = reconcile.split("if v_slot.id is null or v_item.id is null then", 1)[0]
    assert "p_snapshot #>> '{pi,mode}' = 'real'" in before_idle
    assert "p_snapshot #>> '{esp,connection}' = 'online'" in before_idle
    assert "v_boot is not null and v_pending = 0" in before_idle
    assert "v_telemetry_at between now() - interval '5 seconds'" in before_idle
    assert "v_reading->>'ready' is distinct from 'true'" in before_idle
    assert "(v_sensed_present and v_observed_slot.status='available')" in before_idle
    assert "(not v_sensed_present and v_observed_slot.status='occupied')" in before_idle
    assert "case when v_sensed_present then 'wrong_placement' else 'wrong_removal' end" in before_idle
    assert "on conflict do nothing" in before_idle
    assert "update public.sauli_hardware_incidents set active=false,resolved_at=now()" in before_idle

    presence_sql = PRESENCE_MIGRATION.read_text(encoding="utf-8").lower()
    assert "on public.sauli_hardware_incidents(unit_id,slot_id) where active" in presence_sql
    guidance = sql.split("create or replace function public.sauli_hardware_guidance", 1)[1]
    guidance = guidance.split("create or replace function public.sauli_reconcile_hardware_workflow", 1)[0]
    assert "and slot_id = v_slot.id and active) then 'sos_blink'" in guidance
    assert "'buzzer',v_buzzer" in guidance


def test_public_status_is_read_only_and_admin_control_disabled_by_default():
    app = create_app(Settings(supabase_url=None, supabase_service_role_key=None, emailjs_enabled=False))
    class Kiosks:
        async def public_hardware_status(self):
            return {"units": []}
    app.state.kiosks = Kiosks()
    with TestClient(app) as client:
        response = client.get("/api/hardware/public")
        assert response.json() == {"units": []}
        assert response.headers["cache-control"] == "no-store, max-age=0"
        assert client.post("/api/hardware/admin/test-command", json={
            "device_id": str(uuid4()), "action": "pulse_pocket"}).status_code in (401, 403)


def test_presence_events_are_device_scoped_and_validate_transitions():
    device = {"id": str(uuid4()), "unit_id": str(uuid4())}
    app = create_app(Settings(supabase_url=None, supabase_service_role_key=None, emailjs_enabled=False))
    class Kiosks:
        async def device_from_credential(self, _credential):
            return None
        async def apply_hardware_presence(self, incoming, event):
            assert incoming == device
            assert event == {"event_id": "boot-1", "boot_id": "boot", "seq": 1,
                             "slot": "P-01", "kind": "ITEM_PRESENT", "present": True}
            return {"ok": True, "duplicate": False}
    app.state.kiosks = Kiosks()
    payload = {"event_id": "boot-1", "boot_id": "boot", "seq": 1,
               "slot": "P-01", "kind": "ITEM_PRESENT", "present": True}
    with TestClient(app) as client:
        assert client.post("/api/hardware/presence", json=payload).status_code == 403
        app.dependency_overrides[get_device] = lambda: device
        assert client.post("/api/hardware/presence", json=payload).json()["ok"] is True
        assert client.post("/api/hardware/presence", json={**payload, "present": False}).status_code == 422
        assert client.post("/api/hardware/presence", json={**payload, "slot": "P-09"}).status_code == 422


def test_workflow_and_capture_light_require_kiosk_session():
    kiosk = {"id": str(uuid4()), "unit_id": str(uuid4())}
    item_id = str(uuid4())
    app = create_app(Settings(supabase_url=None, supabase_service_role_key=None, emailjs_enabled=False))
    class Kiosks:
        async def browser_session(self, _token):
            return None
        async def hardware_workflow(self, incoming, *, item_id, session_id):
            assert incoming == kiosk and item_id is not None and session_id is None
            return {"status": "waiting"}
        async def enqueue_capture_light(self, incoming, enabled):
            assert incoming == kiosk and enabled is True
            return {"queued": True}
    app.state.kiosks = Kiosks()
    with TestClient(app) as client:
        assert client.get("/api/hardware/workflow", params={"item_id": item_id}).status_code in (401, 403)
        app.dependency_overrides[get_kiosk_session] = lambda: kiosk
        assert client.get("/api/hardware/workflow", params={"item_id": item_id}).json() == {"status": "waiting"}
        assert client.get("/api/hardware/workflow").status_code == 422
        assert client.post("/api/hardware/capture-light", json={"enabled": True}).status_code == 202


def test_hardware_workflow_surfaces_other_active_incidents_in_same_unit():
    unit_id, item_id, other_item_id, wrong_slot_id = (str(uuid4()) for _ in range(4))
    queries = []

    class Query:
        def __init__(self, table):
            self.table = table
            self.filters = {}

        def select(self, _columns):
            return self

        def eq(self, column, value):
            self.filters[column] = value
            return self

        def limit(self, _count):
            return self

        def order(self, _column, desc=False):
            return self

        def execute(self):
            queries.append((self.table, self.filters.copy()))
            rows = {
                "found_items": [{"id": item_id, "unit_id": unit_id,
                                 "placement_status": "reserved"}],
                "sauli_hardware_incidents": [{"slot_id": wrong_slot_id,
                                              "kind": "wrong_removal",
                                              "found_item_id": other_item_id}],
                "storage_slots": [{"id": wrong_slot_id, "code": "P-06"}],
                "sauli_hardware_snapshots": [],
                "sauli_hardware_transactions": [],
            }
            return SimpleNamespace(data=rows[self.table])

    class Client:
        def table(self, name):
            return Query(name)

    repository = SupabaseKioskRepository(None)
    repository.client = lambda: Client()
    workflow = asyncio.run(repository.hardware_workflow(
        {"unit_id": unit_id}, item_id=item_id, session_id=None))

    assert workflow["wrong_slots"] == ["P-06"]
    assert ("sauli_hardware_incidents", {"unit_id": unit_id, "active": True}) in queries


def test_expired_unclaimed_unlock_can_be_retried():
    unit_id, item_id, command_id = (str(uuid4()) for _ in range(3))
    expiration = datetime.now(UTC) - timedelta(seconds=1)

    class Query:
        def __init__(self, table):
            self.name = table

        def select(self, _columns):
            return self

        def eq(self, _column, _value):
            return self

        def limit(self, _count):
            return self

        def order(self, _column, desc=False):
            return self

        def execute(self):
            rows = {
                "found_items": [{"id": item_id, "unit_id": unit_id,
                                 "placement_status": "reserved"}],
                "sauli_hardware_incidents": [],
                "sauli_hardware_snapshots": [],
                "sauli_hardware_transactions": [{"phase": "awaiting_door_open",
                    "last_door": "closed", "found_item_id": item_id,
                    "retrieval_session_id": None, "command_id": command_id}],
                "sauli_hardware_commands": [{"status": "pending",
                    "expires_at": expiration.isoformat()}],
            }
            return SimpleNamespace(data=rows[self.name])

    class Client:
        def table(self, name):
            return Query(name)

    repository = SupabaseKioskRepository(None)
    repository.client = lambda: Client()
    workflow = asyncio.run(repository.hardware_workflow(
        {"unit_id": unit_id}, item_id=item_id, session_id=None))
    assert workflow["unlock_retry_available"] is True


def test_workflow_read_recovers_from_one_dropped_connection(monkeypatch):
    monkeypatch.setattr("app.repositories.supabase_kiosks.time.sleep", lambda _: None)
    item_id, unit_id = str(uuid4()), str(uuid4())
    attempts = 0

    class Query:
        def __init__(self, table): self.table = table
        def select(self, _columns): return self
        def eq(self, _column, _value): return self
        def limit(self, _count): return self
        def order(self, _column, desc=False): return self
        def execute(self):
            nonlocal attempts
            if self.table == "found_items":
                attempts += 1
                if attempts == 1:
                    raise httpx.ReadError("connection dropped")
                return SimpleNamespace(data=[{"id": item_id, "unit_id": unit_id,
                                              "placement_status": "reserved"}])
            return SimpleNamespace(data=[])

    class Database:
        def table(self, name): return Query(name)

    repository = SupabaseKioskRepository(None)
    repository.client = lambda: Database()
    workflow = asyncio.run(repository.hardware_workflow(
        {"unit_id": unit_id}, item_id=item_id, session_id=None))
    assert attempts == 2
    assert workflow["placement_status"] == "reserved"
    assert workflow["hardware_online"] is False
    assert workflow["phase"] is None
    assert workflow["unlock_command_status"] is None


def test_workflow_exposes_committed_command_after_ambiguous_unlock_timeout():
    unit_id, item_id, command_id = (str(uuid4()) for _ in range(3))

    class Query:
        def __init__(self, table): self.table = table
        def select(self, _columns): return self
        def eq(self, _column, _value): return self
        def limit(self, _count): return self
        def order(self, _column, desc=False): return self
        def execute(self):
            rows = {
                "found_items": [{"id": item_id, "unit_id": unit_id,
                                 "placement_status": "reserved"}],
                "sauli_hardware_incidents": [],
                "sauli_hardware_snapshots": [],
                "sauli_hardware_transactions": [{"phase": "awaiting_door_open",
                    "last_door": "closed", "found_item_id": item_id,
                    "retrieval_session_id": None, "command_id": command_id}],
                "sauli_hardware_commands": [{"status": "pending",
                    "expires_at": (datetime.now(UTC) + timedelta(seconds=30)).isoformat()}],
            }
            return SimpleNamespace(data=rows[self.table])

    class Database:
        def table(self, name): return Query(name)

    calls = 0

    class RpcQuery:
        def execute(self):
            nonlocal calls
            calls += 1
            raise httpx.ReadError("response lost after commit")

    database = Database()
    database.rpc = lambda _name, _params: RpcQuery()
    repository = SupabaseKioskRepository(None)
    repository.client = lambda: database
    from app.core.errors import ServiceError
    try:
        asyncio.run(repository.enqueue_workflow_unlock(
            {"id": str(uuid4()), "unit_id": unit_id}, item_id=item_id))
        assert False, "The lost response must be surfaced"
    except ServiceError as exc:
        assert exc.status_code == 503
    assert calls == 1  # A write must never be retried after an ambiguous result.
    workflow = asyncio.run(repository.hardware_workflow(
        {"unit_id": unit_id}, item_id=item_id, session_id=None))
    assert workflow["unlock_command_status"] == "pending"
    assert workflow["unlock_retry_available"] is False


def test_unlock_sql_is_idempotent_and_rejects_presence_mismatch():
    sql = WORKFLOW_MIGRATION.read_text(encoding="utf-8")
    begin = sql.index("create or replace function public.sauli_queue_workflow_unlock")
    end = sql.index("end $$;", begin)
    body = sql[begin:end]
    assert "v_command.status <> 'pending' or v_command.expires_at > now()" in body
    assert "hp.present is distinct from (ss.status='occupied')" in body
    assert "insert into public.sauli_hardware_commands" in body


def test_workflow_read_outage_returns_503_not_404_or_500(monkeypatch):
    monkeypatch.setattr("app.repositories.supabase_kiosks.time.sleep", lambda _: None)
    item_id, unit_id = str(uuid4()), str(uuid4())
    attempts = 0

    class Query:
        def select(self, _columns): return self
        def eq(self, _column, _value): return self
        def limit(self, _count): return self
        def execute(self):
            nonlocal attempts
            attempts += 1
            raise httpx.ReadError("connection dropped")

    class Database:
        def table(self, _name): return Query()

    app = create_app(Settings(supabase_url=None, supabase_service_role_key=None,
                              emailjs_enabled=False))
    repository = SupabaseKioskRepository(None)
    repository.client = lambda: Database()
    app.state.kiosks = repository
    app.dependency_overrides[get_kiosk_session] = lambda: {"unit_id": unit_id}
    with TestClient(app) as client:
        response = client.get("/api/hardware/workflow", params={"item_id": item_id})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SUPABASE_UNAVAILABLE"
    assert attempts == 3


def test_unlock_retry_routes_forward_the_correct_kiosk_identity():
    item_id, session_id, unit_id = str(uuid4()), str(uuid4()), str(uuid4())
    kiosk = {"unit_id": unit_id}
    calls = []

    class Kiosks:
        async def browser_session(self, _token):
            return None

        async def enqueue_workflow_unlock(self, incoming, *, item_id=None, session_id=None):
            calls.append((incoming, item_id, session_id))
            return {"status": "pending"}

    app = create_app(Settings(supabase_url=None, supabase_service_role_key=None,
                              emailjs_enabled=False))
    app.state.kiosks = Kiosks()
    with TestClient(app) as client:
        assert client.post(f"/api/found-items/{item_id}/request-unlock").status_code in (401, 403)
        app.dependency_overrides[get_kiosk_session] = lambda: kiosk
        assert client.post(f"/api/found-items/{item_id}/request-unlock").json() == {"status": "pending"}
        assert client.post(f"/api/retrieval-sessions/{session_id}/request-unlock").json() == {"status": "pending"}
    assert calls == [(kiosk, item_id, None), (kiosk, None, session_id)]
