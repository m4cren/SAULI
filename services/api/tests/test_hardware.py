"""Hardware telemetry is device scoped; public diagnostics are read only."""

from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth.kiosk import get_device
from app.config import Settings
from app.main import create_app


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
    app = create_app(Settings())
    with TestClient(app) as client:
        assert client.post("/api/hardware/heartbeat", json={"snapshot": snapshot()}).status_code == 403
    app.dependency_overrides[get_device] = lambda: {"id": str(uuid4()), "unit_id": str(uuid4())}
    with TestClient(app) as client:
        data = snapshot()
        data["pi"]["mode"] = "simulation"
        assert client.post("/api/hardware/heartbeat", json={"snapshot": data}).status_code == 422


def test_authenticated_heartbeat_uses_bound_device_and_strips_untrusted_fields():
    device = {"id": str(uuid4()), "unit_id": str(uuid4())}
    app = create_app(Settings())
    app.dependency_overrides[get_device] = lambda: device

    class Kiosks:
        async def hardware_heartbeat(self, incoming, data):
            assert incoming == device
            assert "secret" not in data
            assert data["pi"]["lock_feedback"] == "unavailable"
            assert data["events"][0]["kind"] == "command_completed"
            assert "private_note" not in data["events"][0]

        async def claim_hardware_commands(self, incoming):
            assert incoming == device
            return []

    app.state.kiosks = Kiosks()
    data = snapshot()
    data["secret"] = "must-be-dropped"
    data["events"] = [{"at": "2026-11-07T12:00:00Z", "kind": "command_completed",
                       "command_id": str(uuid4()), "private_note": "must-be-dropped"}]
    with TestClient(app) as client:
        response = client.post("/api/hardware/heartbeat", json={"snapshot": data})
    assert response.status_code == 200
    assert response.json() == {"device_id": device["id"], "commands": []}


def test_public_status_is_read_only_and_admin_control_disabled_by_default():
    app = create_app(Settings())
    class Kiosks:
        async def public_hardware_status(self):
            return {"units": []}
    app.state.kiosks = Kiosks()
    with TestClient(app) as client:
        assert client.get("/api/hardware/public").json() == {"units": []}
        assert client.post("/api/hardware/admin/test-command", json={
            "device_id": str(uuid4()), "action": "pulse_pocket"}).status_code in (401, 403)
