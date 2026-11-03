"""Unit isolation and device authorization at the API boundary."""

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth.dependencies import get_admin_user
from app.config import Settings
from app.main import create_app
from app.services.retrieval_tokens import new_token, qr_payload


MIGRATION = Path(__file__).resolve().parents[3] / "supabase/migrations/202611020001_sauli_multi_unit_foundation.sql"
RESET = Path(__file__).resolve().parents[3] / "supabase/reset_sauli_data.sql"
PRODUCTION_RESET = Path(__file__).resolve().parents[3] / "supabase/production_reset_sauli_data.sql"
PRODUCTION_PREFLIGHT = Path(__file__).resolve().parents[3] / "supabase/production_reset_preflight.sql"


def test_multi_unit_migration_has_transactional_isolation_guards():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "begin;" in sql and "commit;" in sql
    assert "unique(unit_id,code)" in sql
    assert "on conflict (unit_id,code) do nothing" in sql
    assert "for update skip locked" in sql
    assert "cross_unit_slot_item" in sql
    assert "cross_unit_slot_event" in sql
    assert "unit_identity_immutable" in sql
    assert "slot_unit_immutable" in sql
    assert "sauli_register_kiosk_device" in sql
    assert "sauli_approve_kiosk_pairing" in sql
    assert "fi.unit_id = p_unit_id" in sql
    assert "p-09','p-10','m-05" in sql
    assert "unit_slot_configuration_invalid" in sql


def test_reset_is_guarded_and_preserves_registration():
    sql = RESET.read_text(encoding="utf-8").lower()
    assert "sauli_deployment_guard" in sql
    assert "development" in sql
    assert "delete from public.sauli_units" not in sql
    assert "delete from public.kiosk_devices" not in sql
    assert "delete from storage.objects" not in sql


def test_production_reset_requires_preflight_and_preserves_identity():
    preflight = PRODUCTION_PREFLIGHT.read_text(encoding="utf-8").lower()
    sql = PRODUCTION_RESET.read_text(encoding="utf-8").lower()
    assert "delete from" not in preflight and "update public." not in preflight
    assert "v_confirmation text := 'replace_with_confirmation'" in sql
    assert "reset all sauli production data" in sql
    assert "sauli_production_reset_counts_changed" in sql
    assert "v_expected_nonempty_slots" in sql
    assert "begin;" in sql and "commit;" in sql
    for table in ("sauli_units", "kiosk_devices", "kiosk_device_credentials",
                  "kiosk_browser_sessions", "sauli_deployment_guard"):
        assert f"delete from public.{table}" not in sql
        assert f"update public.{table}" not in sql
    assert "delete from storage.objects" not in sql


def test_kiosk_api_requires_a_valid_session_and_scopes_availability():
    unit_a, unit_b = uuid4(), uuid4()
    app = create_app(Settings())

    class Devices:
        active = False

        async def browser_session(self, token):
            if token == "valid-session" and self.active:
                return {"id": str(uuid4()), "unit_id": str(unit_a),
                        "unit": {"unit_code": "SAULI-A", "display_name": "Station A"}}
            return None

    class Items:
        async def list_slots(self, *, unit_id=None):
            assert unit_id == unit_a
            return [{"unit_id": str(unit_a), "code": "P-01", "size_class": "pocket",
                     "status": "available", "is_active": True},
                    {"unit_id": str(unit_a), "code": "P-02", "size_class": "pocket",
                     "status": "occupied", "is_active": True}]

    app.state.kiosks = Devices()
    app.state.items = Items()
    with TestClient(app) as client:
        assert client.get("/api/kiosk-devices/session").status_code == 403
        assert client.get("/api/storage-slots/availability?size_class=pocket").status_code == 403
        assert client.get("/api/kiosk-devices/session", headers={"X-Kiosk-Session": "forged"}).status_code == 403
        app.state.kiosks.active = True
        valid = {"X-Kiosk-Session": "valid-session"}
        assert client.get("/api/kiosk-devices/session", headers=valid).json()["unit_id"] == str(unit_a)
        response = client.get("/api/storage-slots/availability?size_class=pocket", headers=valid)
        assert response.status_code == 200
        assert response.json()["available"] == 1
        assert response.json()["occupied"] == 1
    assert unit_a != unit_b


def test_anonymous_admin_endpoint_denied():
    app = create_app(Settings())
    with TestClient(app) as client:
        response = client.get("/api/units/admin/fleet")
    assert response.status_code in (401, 403)


def test_qr_validation_uses_authenticated_kiosk_unit():
    unit_a, unit_b = uuid4(), uuid4()
    app = create_app(Settings(retrieval_token_pepper="a" * 48))

    class Devices:
        async def browser_session(self, token):
            if token == "valid-session":
                return {"id": str(uuid4()), "unit_id": str(unit_a),
                        "unit": {"unit_code": "SAULI-A", "display_name": "Station A"}}
            return None

    class Items:
        def __init__(self):
            self.checked_unit = None

        async def validate_retrieval(self, digest, action_digest, unit_id):
            self.checked_unit = unit_id
            return {"error": "INVALID_RETRIEVAL_TOKEN"}

    app.state.kiosks = Devices()
    app.state.items = Items()
    payload = {"qr_payload": qr_payload(new_token())}
    with TestClient(app) as client:
        assert client.post("/api/retrieval-sessions/validate", json=payload).status_code == 403
        assert client.post("/api/retrieval-sessions/validate", json={**payload,
            "unit_id": str(unit_b)}, headers={"X-Kiosk-Session": "valid-session"}).status_code == 422
        response = client.post("/api/retrieval-sessions/validate", json=payload,
            headers={"X-Kiosk-Session": "valid-session"})
    assert response.status_code == 404
    assert app.state.items.checked_unit == unit_a


def test_unit_location_edit_is_admin_only_and_cannot_change_unit_code():
    unit_id = uuid4()
    payload = {"display_name": "Library cabinet", "campus_code": "LSPU-SPCC",
               "campus_name": "San Pablo City Campus", "building_name": "Library",
               "floor": "Ground", "location_description": "Near the entrance"}
    path = f"/api/units/admin/{unit_id}"
    app = create_app(Settings())
    with TestClient(app) as client:
        assert client.put(path, json=payload).status_code in (401, 403)

    class Kiosks:
        async def edit_unit(self, incoming_id, data):
            assert incoming_id == unit_id
            assert data == payload
            return {"id": str(unit_id), "unit_code": "SAULI-LIBRARY-01", **data}

    app.state.kiosks = Kiosks()
    app.dependency_overrides[get_admin_user] = lambda: object()
    with TestClient(app) as client:
        assert client.put(path, json={**payload, "unit_code": "SAULI-OTHER"}).status_code == 422
        response = client.put(path, json=payload)
    assert response.status_code == 200
    assert response.json()["unit_code"] == "SAULI-LIBRARY-01"
