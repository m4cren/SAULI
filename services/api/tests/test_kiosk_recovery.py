"""Regression checks for registered kiosk heartbeat and guarded review recovery."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from app.auth.dependencies import get_admin_user
from app.config import Settings
from app.core.errors import ServiceError
from app.main import create_app
from app.repositories.supabase_kiosks import SupabaseKioskRepository


ROOT = Path(__file__).resolve().parents[3]
MIGRATION = ROOT / "supabase/migrations/202611130001_sauli_review_recovery_and_guidance.sql"


class Query:
    def __init__(self, client, name):
        self.client, self.name = client, name

    def select(self, _columns): return self
    def eq(self, _column, _value): return self
    def is_(self, _column, _value): return self
    def limit(self, _count): return self
    def update(self, _values): return self
    def insert(self, _values): return self

    def execute(self):
        if self.client.fail_on == self.name:
            raise httpx.ReadError("connection dropped")
        return SimpleNamespace(data=self.client.rows.get(self.name, []))


class Database:
    def __init__(self, expires_at=None, fail_on=None):
        self.fail_on = fail_on
        device_id, unit_id = str(uuid4()), str(uuid4())
        self.rows = {
            "kiosk_device_credentials": [{"device_id": device_id, "expires_at": expires_at}],
            "kiosk_devices": [{"id": device_id, "unit_id": unit_id,
                               "status": "active", "revoked_at": None}],
            "sauli_units": [{"unit_code": "SAULI-A", "status": "active",
                             "display_name": "Station A"}],
        }

    def table(self, name): return Query(self, name)


class Items:
    def __init__(self, database): self.database = database
    def require(self): return self.database


def test_nonexpiring_registered_credential_allows_real_heartbeat():
    app = create_app(Settings())
    app.state.kiosks = SupabaseKioskRepository(Items(Database()))
    with TestClient(app) as client:
        response = client.post("/api/kiosk-devices/heartbeat",
                               headers={"Authorization": "Device " + "a" * 64},
                               json={"controller_version": "0.1.0"})
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_revoked_or_expired_device_credentials_fail_closed():
    expired = Database("2000-01-01T00:00:00Z")
    revoked = Database()
    revoked.rows["kiosk_device_credentials"] = []
    for database in (expired, revoked):
        app = create_app(Settings())
        app.state.kiosks = SupabaseKioskRepository(Items(database))
        with TestClient(app) as client:
            response = client.post("/api/kiosk-devices/heartbeat",
                                   headers={"Authorization": "Device " + "a" * 64}, json={})
        assert response.status_code == 403


def test_heartbeat_database_outage_is_503_and_never_fake_success(monkeypatch):
    monkeypatch.setattr("app.repositories.supabase_kiosks.time.sleep", lambda _: None)
    for failing_table in ("kiosk_device_credentials", "kiosk_devices"):
        app = create_app(Settings())
        app.state.kiosks = SupabaseKioskRepository(Items(Database(fail_on=failing_table)))
        with TestClient(app) as client:
            response = client.post("/api/kiosk-devices/heartbeat",
                                   headers={"Authorization": "Device " + "a" * 64}, json={})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "SUPABASE_UNAVAILABLE"


def test_bootstrap_database_outage_does_not_issue_a_code():
    repo = SupabaseKioskRepository(Items(Database(fail_on="kiosk_browser_bootstraps")))
    try:
        asyncio.run(repo.bootstrap(str(uuid4())))
    except ServiceError as exc:
        assert exc.status_code == 503
        assert exc.code == "SUPABASE_UNAVAILABLE"
    else:
        assert False, "an unwritten bootstrap code must not be returned"


def test_review_rearm_is_admin_only_and_validates_reason():
    unit_id, actor_id = uuid4(), uuid4()
    app = create_app(Settings())
    calls = []

    class Kiosks:
        async def rearm_unopened_hardware_review(self, unit, actor, reason):
            calls.append((unit, actor, reason))
            return {"status": "rearmed"}

    app.state.kiosks = Kiosks()
    path = f"/api/units/admin/{unit_id}/hardware-review/rearm"
    with TestClient(app) as client:
        assert client.post(path, json={"reason": "Physically checked both doors and slots"}).status_code in (401, 403)
        app.dependency_overrides[get_admin_user] = lambda: SimpleNamespace(id=str(actor_id))
        assert client.post(path, json={"reason": "too short"}).status_code == 422
        assert client.post(path, json={"reason": "Physically checked both doors and slots"}).json() == {"status": "rearmed"}
    assert calls == [(unit_id, actor_id, "Physically checked both doors and slots")]


def test_review_rearm_denied_result_maps_to_conflict():
    repo = SupabaseKioskRepository(Items(Database()))

    async def denied(_name, _params): return {"error": "HARDWARE_NOT_SAFE"}

    repo.rpc = denied
    try:
        asyncio.run(repo.rearm_unopened_hardware_review(uuid4(), uuid4(), "Physically checked both doors and slots"))
    except ServiceError as exc:
        assert exc.status_code == 409
        assert exc.code == "REVIEW_REARM_DENIED"
    else:
        assert False, "unsafe review must remain blocked"


def test_recovery_migration_keeps_alarm_incident_driven_and_rearm_guarded():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    guidance = sql.split("create or replace function public.sauli_hardware_guidance", 1)[1]
    guidance = guidance.split("create table public.sauli_hardware_review_resolutions", 1)[0]
    assert "sauli_hardware_incidents" in guidance
    assert "and active) into v_buzzer" in guidance
    assert "'review_required',v_review_required" in guidance
    assert "phase = 'requires_review'" not in guidance.split("into v_buzzer", 1)[0]
    assert "when exists(select 1 from public.sauli_hardware_incidents" in guidance
    assert "when v_deposit is not null and v_slot.id = v_assigned and v_buzzer then 'sos_blink'" in guidance
    recovery = sql.split("create function public.sauli_rearm_unopened_hardware_review", 1)[1]
    for guard in ("v_tx.phase is distinct from 'requires_review'",
                  "v_tx.last_door is distinct from 'closed'", "v_tx.opened_at is not null",
                  "v_tx.closed_at is not null", "v_snapshot.snapshot #>> '{pi,mode}'",
                  "v_snapshot.snapshot #>> '{esp,connection}'", "v_presence.boot_id",
                  "v_reading->>'present'", "v_snapshot.snapshot->>'pending_presence_count'",
                  "v_snapshot.snapshot #>> '{pi,doors,pocket,raw_level}' is null",
                  "v_snapshot.snapshot #>> '{pi,doors,medium,raw_level}' is null"):
        assert guard in recovery
    assert "insert into public.sauli_hardware_review_resolutions" in recovery
    assert "phase = 'awaiting_door_open'" in recovery
    assert "pulse_pocket" in recovery and "pulse_medium" in recovery
    for reset in ("reset_sauli_data.sql", "production_reset_sauli_data.sql"):
        assert "sauli_hardware_review_resolutions" in (ROOT / "supabase" / reset).read_text(encoding="utf-8")
