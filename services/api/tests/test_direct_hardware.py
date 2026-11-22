"""Focused checks for the database-free direct hardware command path."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.kiosk import get_device
from app.config import Settings
from app.core.errors import ServiceError
from app.integrations.direct_hardware import DirectHardwareGateway
from app.main import create_app
from app.repositories.supabase_kiosks import (
    SupabaseKioskRepository,
    merge_direct_warning,
)


DIRECT_MIGRATION = (Path(__file__).resolve().parents[3]
                    / "supabase/migrations/202611210001_sauli_direct_hardware_transport.sql")
FINALIZATION_MIGRATION = (Path(__file__).resolve().parents[3]
    / "supabase/migrations/202611220001_sauli_direct_workflow_finalization.sql")
HELD_UNLOCK_MIGRATION = (Path(__file__).resolve().parents[3]
    / "supabase/migrations/202611220002_sauli_held_unlock_workflow.sql")
RECOVERY_MIGRATION = (Path(__file__).resolve().parents[3]
    / "supabase/migrations/202611220003_sauli_direct_unlock_recovery.sql")
LOCAL_COMPLETION_MIGRATION = (Path(__file__).resolve().parents[3]
    / "supabase/migrations/202611220004_sauli_local_physical_completion.sql")


def hardware_snapshot() -> dict:
    return {
        "pi": {
            "mode": "real",
            "doors": {
                "medium": {"raw_level": 0, "door": "closed"},
                "pocket": {"raw_level": 0, "door": "closed"},
            },
            "outputs": {name: False for name in (
                "main_light", "buzzer", "medium_solenoid", "pocket_solenoid",
                "pocket_light_gate", "medium_light_gate",
            )},
            "lock_feedback": "unavailable",
        },
        "esp": {"connection": "offline", "telemetry": None},
    }


@pytest.mark.parametrize("action", ["pulse_pocket", "pulse_medium"])
def test_direct_unlock_uses_authorization_rpc_and_never_command_queue(action):
    device_id, unit_id, command_id = (str(uuid4()) for _ in range(3))
    assigned = "P-01" if action == "pulse_pocket" else "M-01"
    calls = []
    issued_grant = "signed-grant." + "x" * 100

    class Hardware:
        async def state(self, incoming_device_id):
            assert incoming_device_id == device_id
            return {"door_workflow": {"phase": "idle"}}

        def issue_unlock_grant(self, incoming_device, authorization, **context):
            assert incoming_device["id"] == device_id
            assert authorization["action"] == action
            assert context["operation"] == "deposit"
            return issued_grant

        async def command_from_grant(self, incoming_device, grant, **context):
            assert incoming_device["id"] == device_id
            assert grant == issued_grant
            assert context["operation"] == "deposit"
            return {"id": command_id, "status": "acked",
                    "code": "pulse_completed"}

    repository = SupabaseKioskRepository(
        None, hardware=Hardware(), hardware_transport="direct")

    async def rpc(name, params):
        calls.append((name, params))
        assert name == "sauli_authorize_workflow_unlock"
        return {
            "command_id": command_id, "status": "authorized", "action": action,
            "assigned_slot": assigned,
            "expected_slots": [
                {"code": f"P-{number:02d}", "present": False} for number in range(1, 9)
            ] + [
                {"code": f"M-{number:02d}", "present": False} for number in range(1, 5)
            ],
            "expires_at": (datetime.now(UTC) + timedelta(seconds=10)).isoformat(),
        }

    repository.rpc = rpc
    result = asyncio.run(repository.enqueue_workflow_unlock(
        {"id": device_id, "unit_id": unit_id}, item_id=str(uuid4())))
    assert result == {"command_id": command_id, "status": "acked",
                      "code": "pulse_completed", "unlock_grant": issued_grant}
    assert [name for name, _ in calls] == ["sauli_authorize_workflow_unlock"]


def test_definitive_pre_activation_rejection_is_recorded_for_new_authorization():
    device_id, unit_id, command_id = (str(uuid4()) for _ in range(3))
    calls = []
    issued_grant = "signed-grant." + "x" * 100

    class Hardware:
        async def state(self, _device_id):
            return {"door_workflow": {"phase": "idle"}}

        def issue_unlock_grant(self, _device, _authorization, **_context):
            return issued_grant

        async def command_from_grant(self, _device, grant, **_context):
            assert grant == issued_grant
            return {"id": command_id, "status": "failed",
                    "code": "sensor_state_mismatch"}

    repository = SupabaseKioskRepository(
        None, hardware=Hardware(), hardware_transport="direct")

    async def rpc(name, params):
        calls.append(name)
        if name == "sauli_authorize_workflow_unlock":
            return {
                "command_id": command_id, "action": "pulse_pocket",
                "assigned_slot": "P-01", "expected_slots": [],
                "expires_at": (datetime.now(UTC) + timedelta(seconds=10)).isoformat(),
            }
        assert name == "sauli_record_direct_unlock_result"
        assert params["p_command_id"] == command_id
        assert params["p_code"] == "sensor_state_mismatch"
        return True

    repository.rpc = rpc
    with pytest.raises(ServiceError) as error:
        asyncio.run(repository.enqueue_workflow_unlock(
            {"id": device_id, "unit_id": unit_id}, item_id=str(uuid4())))
    assert error.value.code == "SENSOR_STATE_MISMATCH"
    assert error.value.status_code == 409
    assert calls == ["sauli_authorize_workflow_unlock",
                     "sauli_record_direct_unlock_result"]


def test_previously_authorized_grant_unlocks_without_supabase_round_trip():
    device_id, unit_id, workflow_id, command_id = (str(uuid4()) for _ in range(4))
    issued_grant = "signed-grant." + "x" * 100

    class Hardware:
        async def command_from_grant(self, device, grant, **context):
            assert device == {"id": device_id, "unit_id": unit_id}
            assert grant == issued_grant
            assert context == {"workflow_id": workflow_id, "operation": "deposit"}
            return {"id": command_id, "status": "acked", "code": "unlock_held"}

    repository = SupabaseKioskRepository(
        None, hardware=Hardware(), hardware_transport="direct")

    async def forbidden_rpc(name, _params):
        raise AssertionError(f"Authorized unlock must not call Supabase RPC {name}")

    repository.rpc = forbidden_rpc
    result = asyncio.run(repository.enqueue_workflow_unlock(
        {"id": device_id, "unit_id": unit_id}, item_id=workflow_id,
        grant=issued_grant))
    assert result == {"command_id": command_id, "status": "acked",
                      "code": "unlock_held", "unlock_grant": issued_grant}


def test_gpio_ack_returns_without_waiting_for_supabase_reconciliation():
    device_id, unit_id, workflow_id, command_id = (str(uuid4()) for _ in range(4))
    issued_grant = "signed-grant." + "x" * 100
    delivered = []

    class Hardware:
        async def command_from_grant(self, _device, grant, **_context):
            delivered.append(grant)
            return {"id": command_id, "status": "acked", "code": "unlock_held",
                    "snapshot": hardware_snapshot()}

    repository = SupabaseKioskRepository(
        None, hardware=Hardware(), hardware_transport="direct")

    async def unavailable(_name, _params):
        raise ServiceError("DATABASE_UNAVAILABLE", "Database unavailable.", 503)

    repository.rpc = unavailable
    result = asyncio.run(repository.enqueue_workflow_unlock(
        {"id": device_id, "unit_id": unit_id}, item_id=workflow_id,
        grant=issued_grant))
    assert result["status"] == "acked"
    assert result["command_id"] == command_id
    assert delivered == [issued_grant]


def test_original_review_409_recovers_only_after_authenticated_pi_reconciliation():
    device_id, unit_id, workflow_id, command_id = (str(uuid4()) for _ in range(4))
    calls = []
    signed = "signed-grant." + "x" * 100
    snapshot = {"authenticated": "fresh-pi-state"}

    class Hardware:
        async def state(self, incoming_device_id):
            assert incoming_device_id == device_id
            calls.append("authenticated_pi_state")
            return snapshot

        def issue_unlock_grant(self, device, authorization, **context):
            assert device["id"] == device_id
            assert authorization["command_id"] == command_id
            assert context == {"workflow_id": workflow_id, "operation": "deposit"}
            return signed

    repository = SupabaseKioskRepository(
        None, hardware=Hardware(), hardware_transport="direct")
    authorizations = iter([
        {"error": "WORKFLOW_REQUIRES_REVIEW"},
        {
            "command_id": command_id, "status": "authorized",
            "action": "pulse_pocket", "assigned_slot": "P-01",
            "expected_slots": [{"code": f"P-{n:02d}", "present": False}
                               for n in range(1, 9)] +
                              [{"code": f"M-{n:02d}", "present": False}
                               for n in range(1, 5)],
        },
    ])

    async def rpc(name, params):
        calls.append(name)
        if name == "sauli_authorize_workflow_unlock":
            return next(authorizations)
        assert name == "sauli_recover_direct_unopened_workflow"
        assert params["p_device_id"] == device_id
        assert params["p_item_id"] == workflow_id
        assert params["p_snapshot"] == snapshot
        return {"status": "recovered", "resolution_id": str(uuid4())}

    repository.rpc = rpc
    result = asyncio.run(repository.enqueue_workflow_unlock(
        {"id": device_id, "unit_id": unit_id}, item_id=workflow_id,
        authorize_only=True))
    assert result == {"command_id": command_id, "status": "authorized",
                      "unlock_grant": signed}
    assert calls == ["sauli_authorize_workflow_unlock", "authenticated_pi_state",
                     "sauli_recover_direct_unopened_workflow",
                     "sauli_authorize_workflow_unlock"]


def test_old_timeout_command_is_rearmed_with_a_new_id_instead_of_replayed():
    device_id, unit_id, workflow_id, old_command_id, new_command_id = (
        str(uuid4()) for _ in range(5))
    signed = "signed-grant." + "x" * 100
    calls = []

    class Hardware:
        async def state(self, _device_id):
            calls.append("authenticated_pi_state")
            return {"door_workflow": {
                "phase": "fault", "fault": "door_open_timeout",
                "command_id": old_command_id,
            }}

        def issue_unlock_grant(self, _device, authorization, **_context):
            assert authorization["command_id"] == new_command_id
            return signed

    repository = SupabaseKioskRepository(
        None, hardware=Hardware(), hardware_transport="direct")
    authorizations = iter([
        {
            "command_id": old_command_id, "status": "authorized",
            "action": "pulse_pocket", "assigned_slot": "P-01",
            "expected_slots": [],
        },
        {
            "command_id": new_command_id, "status": "authorized",
            "action": "pulse_pocket", "assigned_slot": "P-01",
            "expected_slots": [],
        },
    ])

    async def rpc(name, _params):
        calls.append(name)
        if name == "sauli_authorize_workflow_unlock":
            return next(authorizations)
        assert name == "sauli_recover_direct_unopened_workflow"
        return {"status": "recovered", "resolution_id": str(uuid4())}

    repository.rpc = rpc
    result = asyncio.run(repository.enqueue_workflow_unlock(
        {"id": device_id, "unit_id": unit_id}, item_id=workflow_id,
        authorize_only=True))
    assert result["command_id"] == new_command_id
    assert result["unlock_grant"] == signed
    assert calls == ["sauli_authorize_workflow_unlock", "authenticated_pi_state",
                     "sauli_recover_direct_unopened_workflow",
                     "sauli_authorize_workflow_unlock"]


def test_faulted_workflow_stays_blocked_when_authenticated_recovery_is_unsafe():
    device_id, unit_id, workflow_id = (str(uuid4()) for _ in range(3))

    class Hardware:
        async def state(self, _device_id):
            return {"pi": {"doors": {"pocket": {"door": "open"}}}}

    repository = SupabaseKioskRepository(
        None, hardware=Hardware(), hardware_transport="direct")

    async def rpc(name, _params):
        if name == "sauli_authorize_workflow_unlock":
            return {"error": "WORKFLOW_REQUIRES_REVIEW"}
        assert name == "sauli_recover_direct_unopened_workflow"
        return {"error": "HARDWARE_NOT_SAFE"}

    repository.rpc = rpc
    with pytest.raises(ServiceError) as error:
        asyncio.run(repository.enqueue_workflow_unlock(
            {"id": device_id, "unit_id": unit_id}, item_id=workflow_id,
            authorize_only=True))
    assert error.value.code == "WORKFLOW_HARDWARE_NOT_SAFE"
    assert error.value.status_code == 409


def _gateway_fixture():
    device_id, unit_id, workflow_id, command_id = (str(uuid4()) for _ in range(4))
    token = "test-direct-hardware-token-" + "x" * 32
    gateway = DirectHardwareGateway(Settings(
        supabase_url=None, supabase_service_role_key=None, emailjs_enabled=False,
        hardware_direct_devices={device_id: {
            "url": "http://127.0.0.1:8787", "token": token,
        }},
    ))
    device = {"id": device_id, "unit_id": unit_id}
    authorization = {
        "command_id": command_id, "action": "pulse_pocket", "assigned_slot": "P-01",
        "expected_slots": [
            {"code": f"P-{number:02d}", "present": False} for number in range(1, 9)
        ] + [
            {"code": f"M-{number:02d}", "present": False} for number in range(1, 5)
        ],
    }
    return gateway, device, workflow_id, authorization


def test_unlock_grant_rejects_invalid_wrong_device_wrong_door_and_replay(monkeypatch):
    gateway, device, workflow_id, authorization = _gateway_fixture()
    grant = gateway.issue_unlock_grant(
        device, authorization, workflow_id=workflow_id, operation="deposit")
    try:
        with pytest.raises(ServiceError) as invalid:
            gateway.verify_unlock_grant(
                device, grant[:-1] + ("A" if grant[-1] != "A" else "B"),
                workflow_id=workflow_id, operation="deposit")
        assert invalid.value.code == "INVALID_UNLOCK_GRANT"

        wrong_device = {"id": device["id"], "unit_id": str(uuid4())}
        with pytest.raises(ServiceError) as mismatch:
            gateway.verify_unlock_grant(
                wrong_device, grant, workflow_id=workflow_id, operation="deposit")
        assert mismatch.value.code == "UNLOCK_GRANT_DEVICE_MISMATCH"

        invalid_door_authorization = {**authorization, "action": "pulse_medium"}
        invalid_door = gateway.issue_unlock_grant(
            device, invalid_door_authorization,
            workflow_id=workflow_id, operation="deposit")
        with pytest.raises(ServiceError) as door_error:
            gateway.verify_unlock_grant(
                device, invalid_door, workflow_id=workflow_id, operation="deposit")
        assert door_error.value.code == "INVALID_UNLOCK_GRANT"

        gateway.verify_unlock_grant(
            device, grant, workflow_id=workflow_id, operation="deposit", consume=True)
        with pytest.raises(ServiceError) as replay:
            gateway.verify_unlock_grant(
                device, grant, workflow_id=workflow_id, operation="deposit", consume=True)
        assert replay.value.code == "UNLOCK_GRANT_REPLAYED"
    finally:
        asyncio.run(gateway.close())


def test_unlock_grant_rejects_expiry_and_wrong_workflow(monkeypatch):
    gateway, device, workflow_id, authorization = _gateway_fixture()
    grant = gateway.issue_unlock_grant(
        device, authorization, workflow_id=workflow_id, operation="deposit")
    try:
        with pytest.raises(ServiceError) as workflow_error:
            gateway.verify_unlock_grant(
                device, grant, workflow_id=str(uuid4()), operation="deposit")
        assert workflow_error.value.code == "UNLOCK_GRANT_WORKFLOW_MISMATCH"

        import app.integrations.direct_hardware as direct_hardware_module
        monkeypatch.setattr(
            direct_hardware_module.time, "time",
            lambda: datetime.now(UTC).timestamp() + 301)
        with pytest.raises(ServiceError) as expired:
            gateway.verify_unlock_grant(
                device, grant, workflow_id=workflow_id, operation="deposit")
        assert expired.value.code == "UNLOCK_GRANT_EXPIRED"
    finally:
        asyncio.run(gateway.close())


def test_uncertain_delivery_is_resolved_from_authenticated_pi_without_resend():
    gateway, device, workflow_id, authorization = _gateway_fixture()
    grant = gateway.issue_unlock_grant(
        device, authorization, workflow_id=workflow_id, operation="deposit")
    command_calls = []

    async def uncertain(_device_id, command):
        command_calls.append(command["id"])
        raise ServiceError("HARDWARE_UNAVAILABLE", "lost response", 503)

    async def accepted_state(_device_id):
        return {"last_unlock": {
            "command_id": authorization["command_id"], "status": "completed",
            "activated_at": datetime.now(UTC).isoformat(),
        }}

    gateway.command = uncertain
    gateway.state = accepted_state
    try:
        first = asyncio.run(gateway.command_from_grant(
            device, grant, workflow_id=workflow_id, operation="deposit"))
        second = asyncio.run(gateway.command_from_grant(
            device, grant, workflow_id=workflow_id, operation="deposit"))
        assert first["status"] == second["status"] == "acked"
        assert first["code"] == "unlock_already_accepted"
        assert command_calls == [authorization["command_id"]]
    finally:
        asyncio.run(gateway.close())


def test_unconfirmed_delivery_never_claims_gpio_activation_or_resends():
    gateway, device, workflow_id, authorization = _gateway_fixture()
    grant = gateway.issue_unlock_grant(
        device, authorization, workflow_id=workflow_id, operation="deposit")
    command_calls = []

    async def uncertain(_device_id, command):
        command_calls.append(command["id"])
        raise ServiceError("HARDWARE_UNAVAILABLE", "lost response", 503)

    async def no_evidence(_device_id):
        return {"last_unlock": None}

    gateway.command = uncertain
    gateway.state = no_evidence
    try:
        with pytest.raises(ServiceError) as first:
            asyncio.run(gateway.command_from_grant(
                device, grant, workflow_id=workflow_id, operation="deposit"))
        assert first.value.code == "HARDWARE_DELIVERY_UNCONFIRMED"
        with pytest.raises(ServiceError) as retry:
            asyncio.run(gateway.command_from_grant(
                device, grant, workflow_id=workflow_id, operation="deposit"))
        assert retry.value.code == "HARDWARE_DELIVERY_UNCONFIRMED"
        assert command_calls == [authorization["command_id"]]
    finally:
        asyncio.run(gateway.close())


def test_local_completion_uses_post_physical_completion_rpc():
    device = {"id": str(uuid4()), "unit_id": str(uuid4())}
    repository = SupabaseKioskRepository(None, hardware_transport="direct")
    calls = []
    snapshot = {"local_completion": {"verified": True, "command_id": str(uuid4())}}

    async def rpc(name, params):
        calls.append((name, params))
        return {"phase": "completed", "finalized": True}

    repository.rpc = rpc
    result = asyncio.run(repository.hardware_workflow_event(device, snapshot, None))
    assert result["finalized"] is True
    assert calls == [("sauli_reconcile_local_hardware_completion", {
        "p_device_id": device["id"], "p_snapshot": snapshot,
    })]


def test_live_direct_workflow_uses_pi_state_without_supabase_read():
    workflow_id, command_id = str(uuid4()), str(uuid4())

    class Hardware:
        async def state(self, _device_id):
            return {
                "pi": {"doors": {"pocket": {"door": "closed"}}},
                "last_unlock": {"status": "completed", "activated_at": "now",
                                "deactivated_at": "now"},
                "door_workflow": {"door": "pocket"},
                "local_warning": {
                    "monitoring": True, "command_id": command_id,
                    "workflow_id": workflow_id, "assigned_slot": "P-01",
                    "operation": "deposit", "assigned_present": True,
                    "expected_present": True, "provisional_success": True,
                    "awaiting_finalization": True,
                    "finalization_error": "SYNCHRONIZATION_PENDING",
                    "local_phase": "locally_completed", "locally_completed": True,
                    "sync_pending": True, "violations": [],
                },
            }

    repository = SupabaseKioskRepository(
        None, hardware=Hardware(), hardware_transport="direct")
    result = asyncio.run(repository.hardware_workflow(
        {"id": str(uuid4()), "unit_id": str(uuid4())},
        item_id=workflow_id, session_id=None))
    assert result["phase"] == "synchronizing"
    assert result["locally_completed"] is True
    assert result["sync_pending"] is True
    assert result["door"] == "closed"


def test_operator_review_rearm_uses_fresh_authenticated_direct_state():
    unit_id, device_id, actor_id = (uuid4() for _ in range(3))
    snapshot = hardware_snapshot()

    class Hardware:
        async def state(self, requested_device_id):
            assert requested_device_id == str(device_id)
            return snapshot

    repository = SupabaseKioskRepository(
        None, hardware=Hardware(), hardware_transport="direct")
    calls = []

    async def read_device(_callback, label):
        assert label == "review device"
        return {"id": str(device_id)}

    async def rpc(name, params):
        calls.append((name, params))
        return {"status": "rearmed", "resolution_id": str(uuid4())}

    repository._read_with_retry = read_device
    repository.rpc = rpc
    result = asyncio.run(repository.rearm_unopened_hardware_review(
        unit_id, actor_id, "Reviewed physical and database state match."))
    assert result["status"] == "rearmed"
    assert calls == [("sauli_rearm_direct_hardware_review", {
        "p_unit_id": str(unit_id), "p_device_id": str(device_id),
        "p_actor_id": str(actor_id),
        "p_reason": "Reviewed physical and database state match.",
        "p_snapshot": snapshot,
    })]


def test_direct_timeout_recovery_sql_requires_fresh_authenticated_safe_state():
    sql = RECOVERY_MIGRATION.read_text(encoding="utf-8").lower()
    assert "sauli_recover_direct_unopened_workflow" in sql
    assert "door_open_timeout" in sql
    assert "opened_at is not null" in sql
    assert "p_snapshot #>> '{pi,doors,pocket,door}' is distinct from 'closed'" in sql
    assert "p_snapshot #>> '{pi,doors,medium,door}' is distinct from 'closed'" in sql
    assert "p_snapshot #>> '{pi,outputs,pocket_solenoid}' is distinct from 'false'" in sql
    assert "p_snapshot #>> '{pi,outputs,medium_solenoid}' is distinct from 'false'" in sql
    assert "jsonb_array_length(p_snapshot #> '{esp,telemetry,slots}') <> 12" in sql
    assert "sauli_hardware_review_resolutions" in sql
    assert "insert into public.sauli_hardware_commands" not in sql


def test_local_completion_migration_keeps_gpio_independent_and_recovery_guarded():
    sql = LOCAL_COMPLETION_MIGRATION.read_text(encoding="utf-8").lower()
    completion = sql.split(
        "create function public.sauli_reconcile_local_hardware_completion", 1)[1]
    assert "'{pi,outputs,pocket_solenoid}' is distinct from 'false'" in completion
    assert "'{pi,outputs,medium_solenoid}' is distinct from 'false'" in completion
    assert "local_completion" in completion
    assert "telemetry_sequence" in completion
    assert "unresolved_hardware_incident" in completion
    assert "if v_tx.phase='completed'" in completion
    assert "on conflict (retrieval_session_id) do nothing" in completion
    recovery = sql.split("create function public.sauli_rearm_direct_hardware_review", 1)[1]
    assert "v_tx.phase <> 'requires_review'" in recovery
    assert "unresolved_hardware_incident" in recovery
    assert "physical_database_mismatch" in recovery
    assert "command_id=null" in recovery
    assert "insert into public.sauli_hardware_commands" not in sql


def test_direct_mode_never_claims_supabase_commands_from_heartbeat():
    device = {"id": str(uuid4()), "unit_id": str(uuid4())}
    app = create_app(Settings(
        supabase_url=None, supabase_service_role_key=None,
        emailjs_enabled=False, hardware_transport="direct",
    ))
    app.dependency_overrides[get_device] = lambda: device

    class Kiosks:
        def __getattr__(self, name):
            raise AssertionError(f"Direct heartbeat must not call {name}")

    app.state.kiosks = Kiosks()
    with TestClient(app) as client:
        response = client.post("/api/hardware/heartbeat",
                               json={"snapshot": hardware_snapshot()})
    assert response.status_code == 410
    assert response.json()["error"]["code"] == "LEGACY_HARDWARE_TRANSPORT_DISABLED"


def test_direct_sql_guard_authorizes_without_queueing_a_database_command():
    sql = DIRECT_MIGRATION.read_text(encoding="utf-8").lower()
    authorization = sql.split(
        "create or replace function public.sauli_authorize_workflow_unlock", 1)[1]
    authorization = authorization.split("end $$;", 1)[0]
    assert "fi.placement_status='reserved'" in authorization
    assert "rs.status='validated'" in authorization
    assert "sauli_hardware_incidents" in authorization
    assert "v_slot_count <> 12" in authorization
    assert "expected_slots" in authorization
    assert "insert into public.sauli_hardware_commands" not in authorization
    assert "sauli_claim_hardware_commands" not in authorization


def test_direct_workflow_event_uses_snapshot_rpc_without_presence_baseline():
    device = {"id": str(uuid4()), "unit_id": str(uuid4())}
    calls = []
    repository = SupabaseKioskRepository(None, hardware_transport="direct")

    async def rpc(name, params):
        calls.append((name, params))
        return {"phase": "completed", "finalized": True}

    repository.rpc = rpc
    result = asyncio.run(repository.hardware_workflow_event(
        device, hardware_snapshot(), {
            "event_id": "boot-1", "boot_id": "boot", "seq": 1,
            "slot": "P-01", "kind": "ITEM_PRESENT", "present": True,
        }))
    assert result["finalized"] is True
    assert [name for name, _ in calls] == ["sauli_reconcile_direct_hardware_workflow"]
    assert calls[0][1] == {"p_device_id": device["id"],
                            "p_snapshot": hardware_snapshot()}


def test_direct_security_transitions_are_recorded_before_reconciliation():
    device = {"id": str(uuid4()), "unit_id": str(uuid4())}
    snapshot = hardware_snapshot()
    snapshot["local_warning"] = {
        "monitoring": True, "active": True, "command_id": str(uuid4()),
        "assigned_slot": "P-01", "operation": "deposit",
        "provisional_success": False,
        "violations": [{"slot": "P-02", "kind": "wrong_placement"}],
    }
    snapshot["local_incident_updates"] = [
        {"slot": "P-02", "kind": "wrong_placement", "active": True}]
    calls = []
    repository = SupabaseKioskRepository(None, hardware_transport="direct")

    async def rpc(name, params):
        calls.append((name, params))
        return ({"applied": 1, "active": True,
                 "phase": "warning_active", "finalized": False}
                if name == "sauli_apply_direct_security_updates"
                else {"phase": "warning_active", "finalized": False})

    repository.rpc = rpc
    result = asyncio.run(repository.hardware_workflow_event(device, snapshot, None))
    assert result["phase"] == "warning_active"
    assert [name for name, _params in calls] == [
        "sauli_apply_direct_security_updates"]


def test_live_direct_warning_overrides_stale_database_incident_view():
    command_id = str(uuid4())
    result = {"_command_id": command_id, "wrong_slots": [],
              "phase": "door_open"}
    state = {"local_warning": {
        "monitoring": True, "command_id": command_id,
        "provisional_success": False,
        "assigned_slot": "P-01", "assigned_present": False,
        "expected_present": True, "awaiting_finalization": False,
        "finalization_error": None,
        "violations": [
            {"slot": "P-02", "kind": "wrong_placement"},
            {"slot": "M-01", "kind": "wrong_removal"},
        ],
    }}
    merge_direct_warning(result, state)
    assert result["wrong_slots"] == ["P-02", "M-01"]
    assert result["phase"] == "warning_active"
    assert result["assigned_slot"] == "P-01"
    assert result["assigned_present"] is False
    state["local_warning"]["violations"] = []
    state["local_warning"]["provisional_success"] = True
    merge_direct_warning(result, state)
    assert result["wrong_slots"] == []
    assert result["phase"] == "provisional_success"
    state["local_warning"]["awaiting_finalization"] = True
    state["local_warning"]["finalization_error"] = "SENSOR_DATA_INCOMPLETE"
    merge_direct_warning(result, state)
    assert result["phase"] == "awaiting_door_close"
    assert result["finalization_error"] == "SENSOR_DATA_INCOMPLETE"


def direct_finalization_sql() -> str:
    sql = HELD_UNLOCK_MIGRATION.read_text(encoding="utf-8").lower()
    return sql.split(
        "create or replace function public.sauli_reconcile_direct_hardware_workflow", 1
    )[1].split("end $$;", 1)[0]


def test_direct_finalization_commits_deposit_and_retrieval_business_records():
    body = direct_finalization_sql()
    assert "set status='occupied',occupied_at=v_completed_at" in body
    assert "set placement_status='placed',placed_at=v_completed_at" in body
    assert "'hardware_item_placed','esp32_switch'" in body
    assert "set status='retrieved'" in body
    assert "set status='available',current_found_item_id=null" in body
    assert "set status='completed',completed_at=v_completed_at" in body
    assert "insert into public.retrieval_logs" in body
    assert "set phase='completed'" in body


def test_direct_finalization_requires_fresh_post_close_complete_sensor_view():
    body = direct_finalization_sql()
    assert "v_telemetry_at > v_tx.closed_at" in body
    assert "jsonb_array_length(v_telemetry->'slots')=12" in body
    assert "where unit_id=v_unit and is_active)=12" in body
    assert "v_seq <= v_tx.close_telemetry_seq" in body
    assert "post_close_sequence_required" in body
    assert "sensor_data_incomplete" in body
    assert "needs_fresh_snapshot',true" in body


def test_direct_finalization_preserves_identity_door_and_command_guards():
    body = direct_finalization_sql()
    assert "d.is_primary and u.status='active'" in body
    assert "id=v_tx.assigned_slot_id and unit_id=v_unit and is_active" in body
    assert "v_slot.current_found_item_id is distinct from v_item.id" in body
    assert "p_snapshot #>> '{last_unlock,command_id}' = v_tx.command_id::text" in body
    assert "p_snapshot #>> '{last_unlock,status}' = 'completed'" in body
    assert "v_deactivated_at" not in body
    assert "array['pi','outputs',v_group || '_solenoid'] = 'true'" in body
    assert "event->>'kind'='workflow_door_opened'" in body
    assert "event->>'kind'='workflow_door_closed'" in body
    assert "unauthenticated_door_open" in body
    assert "unauthenticated_door_close" in body


def test_direct_finalization_handles_new_esp_boot_without_historical_baseline():
    body = direct_finalization_sql()
    assert "if v_boot = v_tx.close_boot_id" in body
    assert "a new esp boot is accepted only through this fresh full snapshot" in body
    assert "sauli_hardware_presence" not in body
    assert "sauli_hardware_snapshots" not in body


def test_direct_finalization_records_wrong_slots_and_blocks_active_incidents():
    body = direct_finalization_sql()
    assert "else v_observed_slot.status='occupied' end" in body
    assert "insert into public.sauli_hardware_incidents" in body
    assert "case when v_present then 'wrong_placement' else 'wrong_removal' end" in body
    assert "set active=false,resolved_at=now()" in body
    assert "where unit_id=v_unit and active" in body
    assert "unresolved_hardware_incident" in body
    assert "assigned_slot_final_state_mismatch" in body
    assert "set phase='requires_review'" in body


def test_direct_security_update_sql_is_idempotent_and_resolves_same_incident():
    sql = FINALIZATION_MIGRATION.read_text(encoding="utf-8").lower()
    body = sql.split(
        "create or replace function public.sauli_apply_direct_security_updates", 1
    )[1].split("end $$;", 1)[0]
    assert "p_snapshot #>> '{local_warning,command_id}'" in body
    assert "insert into public.sauli_hardware_incidents" in body
    assert "on conflict do nothing" in body
    assert "set active=false,resolved_at=now()" in body
    assert "found_item_id is not distinct from v_tx.found_item_id" in body
    assert "retrieval_session_id is not distinct from v_tx.retrieval_session_id" in body


def test_direct_finalization_ignores_delayed_pre_open_snapshot_safely():
    body = direct_finalization_sql()
    assert "v_snapshot_at := coalesce" in body
    assert "v_snapshot_at >= v_tx.opened_at" in body
    assert "snapshot_time_required" in body
    assert "stale_event_ignored" in body
    stale = body.index("'reason','stale_event_ignored'")
    final_updates = body.index("v_completed_at := now()")
    assert stale < final_updates


def test_direct_finalization_is_idempotent_after_completion():
    body = direct_finalization_sql()
    completed_guard = body.index("if v_tx.phase='completed' then")
    deposit_write = body.index("set status='occupied',occupied_at=v_completed_at")
    retrieval_write = body.index("set status='retrieved'")
    assert completed_guard < deposit_write
    assert completed_guard < retrieval_write
    assert "return jsonb_build_object('phase','completed','finalized',true);" in body

