"""Hardware telemetry is device scoped; public diagnostics are read only."""

from uuid import uuid4

from app.auth.kiosk import get_device, get_kiosk_session
from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient


def snapshot():
    return {"pi": {"mode": "real", "doors": {
        "medium": {"raw_level": 1, "door": "open"},
        "pocket": {"raw_level": 0, "door": "closed"}},
        "outputs": {name: False for name in (
            "main_light", "buzzer", "medium_solenoid", "pocket_solenoid",
            "pocket_light_gate", "medium_light_gate")},
        "lock_feedback": "unavailable"},
        "esp": {"connection": "offline", "telemetry": None}}


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
