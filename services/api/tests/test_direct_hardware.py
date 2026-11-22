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
from app.main import create_app
from app.repositories.supabase_kiosks import (
    SupabaseKioskRepository,
    merge_direct_warning,
)


DIRECT_MIGRATION = (Path(__file__).resolve().parents[3]
                    / "supabase/migrations/202611210001_sauli_direct_hardware_transport.sql")
FINALIZATION_MIGRATION = (Path(__file__).resolve().parents[3]
    / "supabase/migrations/202611220001_sauli_direct_workflow_finalization.sql")


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

    class Hardware:
        async def command(self, incoming_device_id, command):
            assert incoming_device_id == device_id
            assert command["action"] == action
            assert command["transport"] == "direct"
            assert len(command["expected_slots"]) == 12
            return {"id": command["id"], "status": "acked",
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
                      "code": "pulse_completed"}
    assert [name for name, _ in calls] == ["sauli_authorize_workflow_unlock"]


def test_direct_rejection_is_secure_and_records_definitive_failure():
    device_id, unit_id, command_id = (str(uuid4()) for _ in range(3))
    calls = []

    class Hardware:
        async def command(self, _device_id, command):
            return {"id": command["id"], "status": "failed",
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
        "violations": [
            {"slot": "P-02", "kind": "wrong_placement"},
            {"slot": "M-01", "kind": "wrong_removal"},
        ],
    }}
    merge_direct_warning(result, state)
    assert result["wrong_slots"] == ["P-02", "M-01"]
    assert result["phase"] == "warning_active"
    state["local_warning"]["violations"] = []
    state["local_warning"]["provisional_success"] = True
    merge_direct_warning(result, state)
    assert result["wrong_slots"] == []
    assert result["phase"] == "provisional_success"


def direct_finalization_sql() -> str:
    sql = FINALIZATION_MIGRATION.read_text(encoding="utf-8").lower()
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

