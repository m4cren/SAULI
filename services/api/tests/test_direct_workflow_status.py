"""Regression: Supabase command identity is not proof of GPIO activation."""

import asyncio
from uuid import uuid4

from app.repositories.supabase_kiosks import SupabaseKioskRepository


def test_direct_workflow_never_fakes_ack_from_database_command_id():
    command_id = str(uuid4())
    device = {"id": str(uuid4()), "unit_id": str(uuid4())}

    class Hardware:
        async def state(self, device_id):
            assert device_id == device["id"]
            return {"pi": {"doors": {"pocket": {"door": "closed"}}},
                    "last_unlock": None, "door_workflow": {"phase": "idle"},
                    "local_warning": {"monitoring": False}}

    repo = SupabaseKioskRepository(None, hardware=Hardware(), hardware_transport="direct")

    async def fetch(_fn, _label):
        return {"_command_id": command_id, "placement_status": "reserved",
                "retrieval_status": None, "wrong_slots": [],
                "hardware_online": False, "phase": "awaiting_door_open",
                "door": "unknown", "last_unlock": None,
                "unlock_command_status": None, "unlock_retry_available": False}

    repo._read_with_retry = fetch
    result = asyncio.run(repo.hardware_workflow(device, item_id=str(uuid4()), session_id=None))
    assert result["unlock_command_status"] is None
    assert result["last_unlock"] is None
    assert result["door"] == "unknown"


def test_direct_workflow_ack_requires_matching_pi_command_id_and_activation():
    command_id = str(uuid4())
    device = {"id": str(uuid4()), "unit_id": str(uuid4())}

    class Hardware:
        async def state(self, _):
            return {"pi": {"doors": {}}, "last_unlock": {
                "command_id": command_id, "status": "completed",
                "activated_at": "2026-11-22T04:46:22+00:00",
            }, "local_warning": {"monitoring": False}}

    repo = SupabaseKioskRepository(None, hardware=Hardware(), hardware_transport="direct")

    async def fetch(_fn, _label):
        return {"_command_id": command_id, "phase": "awaiting_door_open",
                "last_unlock": None, "unlock_command_status": None,
                "unlock_retry_available": False}

    repo._read_with_retry = fetch
    result = asyncio.run(repo.hardware_workflow(device, item_id=str(uuid4()), session_id=None))
    assert result["unlock_command_status"] == "acked"
    assert result["last_unlock"]["activated_at"]
