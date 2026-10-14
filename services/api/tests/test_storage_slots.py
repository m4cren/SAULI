"""Storage contract tests; live PostgreSQL concurrency needs a local Supabase instance."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.config import Settings
from app.core.errors import ServiceError
from app.main import create_app
from app.repositories.supabase_found_items import SupabaseFoundItemRepository
from app.schemas.auth import UserResponse
from app.services.matching import eligible
from app.services.storage_slots import availability


MIGRATION = Path(__file__).resolve().parents[3] / "supabase/migrations/202610110001_sauli_storage_slots.sql"


def test_migration_defines_exact_layout_and_atomic_transitions():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "generate_series(1,10)" in sql and "generate_series(1,5)" in sql
    assert "on conflict (code) do nothing" in sql
    assert "unique(size_class,ordinal)" in sql and "current_found_item_id uuid unique" in sql
    assert "size_class = p_size and status = 'available'" in sql
    assert "order by ordinal limit 1 for update skip locked" in sql
    assert "no_available_storage_slot" in sql
    assert "status = 'occupied'" in sql and "placement_status = 'placed'" in sql
    assert "simulated_item_placed','web_simulation'" in sql


def test_availability_is_size_specific_and_counts_reserved_separately():
    rows = [{"size_class": "pocket", "status": "reserved"}, {"size_class": "pocket", "status": "occupied"},
            {"size_class": "medium", "status": "available"}]
    pocket = availability(rows, "pocket")
    medium = availability(rows, "medium")
    assert (pocket.available, pocket.reserved, pocket.occupied, pocket.can_assign) == (0, 1, 1, False)
    assert (medium.available, medium.can_assign) == (1, True)


def test_slot_listing_retries_transient_network_reads_and_keeps_503_on_outage(monkeypatch):
    monkeypatch.setattr("app.repositories.supabase_found_items.time.sleep", lambda _seconds: None)
    slots = [
        {"code": "M-01", "size_class": "medium", "ordinal": 1, "current_found_item_id": None},
        {"code": "P-01", "size_class": "pocket", "ordinal": 1, "current_found_item_id": None},
    ]

    class Client:
        calls = 0
        fail_until = 2

        def table(self, name):
            assert name == "storage_slots"
            return self

        def select(self, _columns):
            return self

        def execute(self):
            self.calls += 1
            if self.calls <= self.fail_until:
                raise httpx.ReadError("dropped connection")
            return SimpleNamespace(data=[row.copy() for row in slots])

    repo = SupabaseFoundItemRepository(Settings())
    repo.client = Client()
    rows = asyncio.run(repo.list_slots())
    assert [row["code"] for row in rows] == ["P-01", "M-01"]
    assert repo.client.calls == 3

    repo.client = Client()
    repo.client.fail_until = 3
    with pytest.raises(ServiceError) as error:
        asyncio.run(repo.list_slots())
    assert error.value.code == "SUPABASE_UNAVAILABLE" and error.value.status_code == 503
    assert repo.client.calls == 3


def test_only_placed_occupied_items_are_searchable():
    base = {"status": "available", "created_at": datetime.now(timezone.utc).isoformat()}
    assert not eligible({**base, "placement_status": "reserved", "slot_status": "reserved"}, None)
    assert not eligible({**base, "placement_status": "placed", "slot_status": "reserved"}, None)
    assert not eligible({**base, "placement_status": "placed", "slot_status": "out_of_service"}, None)
    assert eligible({**base, "placement_status": "placed", "slot_status": "occupied"}, None)


def test_full_section_uses_stable_409_error_and_requested_size():
    app = create_app(Settings())

    class FullRepo:
        async def find_by_key(self, _key): return None
        async def upload(self, *_args): pass
        async def remove(self, _paths): pass
        async def reserve_item(self, _row, size):
            raise ServiceError("NO_AVAILABLE_STORAGE_SLOT", "The section is full.", 409, {"requested_size": size})

    app.state.items = FullRepo()
    from test_integration import analysis, png
    with TestClient(app) as client:
        response = client.post("/api/found-items/confirm-and-store", headers={"X-Idempotency-Key": str(uuid4())},
            data={"found_location": "Library", "analysis_json": analysis().model_dump_json(), "storage_size": "medium"},
            files={"front_image": ("front.png", png(), "image/png"), "back_image": ("back.png", png(), "image/png")})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NO_AVAILABLE_STORAGE_SLOT"
    assert response.json()["error"]["requested_size"] == "medium"


def test_placement_returns_assigned_slot_and_is_idempotent_at_api_boundary():
    item_id = uuid4()
    row = {"id": str(item_id), "storage_size": "pocket", "placement_status": "reserved",
           "extraction_summary": "Watch", "found_location": "Library", "found_at": datetime.now(timezone.utc).isoformat()}
    slot = {"code": "P-03", "size_class": "pocket", "status": "reserved"}

    class PlacementRepo:
        calls = 0
        async def simulate_placement(self, received_id, code):
            assert received_id == item_id and code == "P-03"
            self.calls += 1
            return {"item": {**row, "placement_status": "placed"}, "slot": {**slot, "status": "occupied"}}

    repo = PlacementRepo()
    app = create_app(Settings())
    app.state.items = repo
    with TestClient(app) as client:
        first = client.post(f"/api/found-items/{item_id}/simulate-placement", json={"slot_code": "P-03"})
        second = client.post(f"/api/found-items/{item_id}/simulate-placement", json={"slot_code": "P-03"})
    assert first.status_code == second.status_code == 200
    assert first.json()["slot_code"] == second.json()["slot_code"] == "P-03"
    assert first.json()["slot_status"] == "occupied" and repo.calls == 2


def test_claim_confirmation_hides_position_until_kiosk_scans_qr():
    user_id, item_id, candidate_id = uuid4(), uuid4(), uuid4()

    class ClaimRepo:
        async def decide_match(self, candidate, user, decision):
            assert (candidate, user, decision) == (candidate_id, user_id, "accepted")
            return {"candidate": {"found_item_id": str(item_id)},
                    "slot": {"code": "M-04", "size_class": "medium", "status": "occupied"}}

    app = create_app(Settings())
    app.state.items = ClaimRepo()
    app.dependency_overrides[get_current_user] = lambda: UserResponse(id=str(user_id))
    with TestClient(app) as client:
        response = client.post(f"/api/matches/{candidate_id}/confirm")
    assert response.status_code == 200
    assert response.json()["item_id"] == str(item_id)
    assert response.json()["slot_code"] is None
    assert response.json()["section"] is None


def test_admin_slot_list_requires_role_and_returns_all_positions():
    now = datetime.now(timezone.utc).isoformat()
    codes = [f"P-{number:02}" for number in range(1, 11)] + [f"M-{number:02}" for number in range(1, 6)]

    class SlotRepo:
        async def list_slots(self, include_items=False):
            assert include_items
            return [{"id": str(uuid4()), "code": code, "size_class": "pocket" if code.startswith("P") else "medium",
                     "ordinal": int(code[-2:]), "status": "available", "current_found_item_id": None,
                     "item_summary": None, "reserved_at": None, "occupied_at": None, "updated_at": now} for code in codes]

    admin_id = str(uuid4())
    app = create_app(Settings(sauli_admin_user_id=admin_id))
    app.state.items = SlotRepo()
    app.dependency_overrides[get_current_user] = lambda: UserResponse(id=str(uuid4()))
    with TestClient(app) as client:
        forbidden = client.get("/api/storage-slots")
        assert forbidden.status_code == 403
        app.dependency_overrides[get_current_user] = lambda: UserResponse(id=str(uuid4()), role="admin")
        assert client.get("/api/storage-slots").status_code == 403
        app.dependency_overrides[get_current_user] = lambda: UserResponse(id=admin_id, role="admin")
        response = client.get("/api/storage-slots")
    assert response.status_code == 200
    assert [slot["code"] for slot in response.json()] == codes


def test_admin_item_photos_require_role_and_are_signed_on_demand():
    item_id, admin_id = uuid4(), str(uuid4())

    class PhotoRepo:
        signed = []
        async def get_item(self, received_id):
            assert received_id == item_id
            return {"slot_status": "occupied", "front_image_path": "found-items/item/front.png",
                    "back_image_path": "found-items/item/back.png"}
        async def signed_url(self, path):
            self.signed.append(path)
            return f"https://storage.example/signed/{path}"

    repo = PhotoRepo()
    app = create_app(Settings(sauli_admin_user_id=admin_id))
    app.state.items = repo
    app.dependency_overrides[get_current_user] = lambda: UserResponse(id=str(uuid4()))
    with TestClient(app) as client:
        route = f"/api/storage-slots/items/{item_id}/images"
        assert client.get(route).status_code == 403
        assert repo.signed == []
        app.dependency_overrides[get_current_user] = lambda: UserResponse(id=admin_id, role="admin")
        response = client.get(route)
        assert response.status_code == 200
        assert response.json()["front_image_url"].endswith("/front.png")
        assert response.json()["back_image_url"].endswith("/back.png")
        assert repo.signed == ["found-items/item/front.png", "found-items/item/back.png"]

        async def unassigned(_item_id):
            return {"slot_status": None, "front_image_path": "found-items/item/front.png"}
        repo.get_item = unassigned
        assert client.get(route).status_code == 404
