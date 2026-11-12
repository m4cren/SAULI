"""Hardware telemetry is device scoped; public diagnostics are read only."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth.kiosk import get_device, get_kiosk_session
from app.config import Settings
from app.main import create_app
from app.repositories.supabase_kiosks import SupabaseKioskRepository
from app.routes.hardware import HardwareSnapshot


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
