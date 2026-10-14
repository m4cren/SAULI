"""Retrieval API and migration security contracts without a live Supabase project."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.config import Settings
from app.core.errors import ServiceError
from app.main import create_app
from app.repositories.supabase_found_items import SupabaseFoundItemRepository
from app.schemas.auth import UserResponse
from app.services.retrieval_sessions import issue, replace, simulate, validate
from app.services.retrieval_tokens import QR_PREFIX, parse_qr_payload, token_hash

MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "supabase/migrations/202610110002_sauli_retrieval_sessions.sql"
)
LIVE_STATUS_MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "supabase/migrations/202610110003_sauli_retrieval_live_status.sql"
)
RESOLVED_REPORT_MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "supabase/migrations/202610140001_sauli_resolve_retrieved_reports.sql"
)


class RetrievalRepo:
    def __init__(self):
        self.sessions = {}
        self.hashes = set()
        self.events = []
        self.logs = []
        self.item_status = "claimed"
        self.slot_status = "occupied"

    async def issue_retrieval(
        self, candidate_id, user_id, digest, ttl_minutes, display_name
    ):
        assert candidate_id and user_id
        assert digest not in self.hashes
        assert QR_PREFIX not in digest
        self.hashes.add(digest)
        for row in self.sessions.values():
            if row["status"] in ("issued", "validated"):
                row["status"] = "cancelled"
        issued_at = datetime.now(UTC)
        row = {
            "id": str(uuid4()),
            "token_hash": digest,
            "status": "issued",
            "issued_at": issued_at.isoformat(),
            "expires_at": (issued_at + timedelta(minutes=ttl_minutes)).isoformat(),
            "item_summary": "Gold watch",
            "user_id": str(user_id),
            "action_hash": None,
            "wrong_item_out": False,
            "display_name": display_name,
        }
        self.sessions[row["id"]] = row
        self.events.append("qr_issued")
        return {
            key: row[key]
            for key in ("id", "status", "issued_at", "expires_at", "item_summary")
        }

    async def retrieval_status(self, session_id, user_id):
        row = self.sessions.get(str(session_id))
        if not row or row["user_id"] != str(user_id):
            return {"error": "RETRIEVAL_NOT_FOUND"}
        if row["status"] == "issued" and datetime.fromisoformat(
            row["expires_at"]
        ) <= datetime.now(UTC):
            row["status"] = "expired"
        return {
            key: row[key]
            for key in ("id", "status", "issued_at", "expires_at", "item_summary")
        } | {
            "validated_at": row.get("validated_at"),
            "completed_at": row.get("completed_at"),
            "slot_code": "M-04"
            if row["status"] in ("validated", "completed")
            else None,
            "section": "medium"
            if row["status"] in ("validated", "completed")
            else None,
            "wrong_item_out": row["status"] == "validated" and row["wrong_item_out"],
            "retriever": row["display_name"],
            "can_replace": row["status"] in ("issued", "expired"),
            "completed": row["status"] == "completed",
        }

    async def replace_retrieval(self, session_id, user_id, digest, ttl_minutes):
        row = self.sessions.get(str(session_id))
        if not row or row["user_id"] != str(user_id):
            return {"error": "RETRIEVAL_NOT_FOUND"}
        if row["status"] not in ("issued", "expired"):
            return {"error": "RETRIEVAL_QR_ALREADY_USED"}
        assert digest not in self.hashes
        self.hashes.add(digest)
        issued_at = datetime.now(UTC)
        row.update(
            token_hash=digest,
            status="issued",
            issued_at=issued_at.isoformat(),
            expires_at=(issued_at + timedelta(minutes=ttl_minutes)).isoformat(),
            action_hash=None,
        )
        self.events.append("qr_replaced")
        return {
            key: row[key]
            for key in ("id", "status", "issued_at", "expires_at", "item_summary")
        }

    async def validate_retrieval(self, digest, action_hash):
        row = next(
            (item for item in self.sessions.values() if item["token_hash"] == digest),
            None,
        )
        if not row:
            return {"error": "INVALID_RETRIEVAL_TOKEN"}
        if row["status"] == "cancelled":
            return {"error": "RETRIEVAL_CANCELLED"}
        if row["status"] == "expired" or datetime.fromisoformat(
            row["expires_at"]
        ) <= datetime.now(UTC):
            row["status"] = "expired"
            return {"error": "RETRIEVAL_QR_EXPIRED"}
        if row["status"] != "issued":
            return {"error": "RETRIEVAL_QR_ALREADY_USED"}
        if self.item_status != "claimed":
            return {"error": "ITEM_NOT_AVAILABLE"}
        if self.slot_status != "occupied":
            return {"error": "STORAGE_POSITION_MISMATCH"}
        row.update(
            status="validated",
            action_hash=action_hash,
            validated_at=datetime.now(UTC).isoformat(),
        )
        self.events.extend(("qr_validated", "simulated_door_ready"))
        return {
            "id": row["id"],
            "status": "validated",
            "item_summary": row["item_summary"],
            "slot_code": "M-04",
            "section": "medium",
            "slot_status": self.slot_status,
        }

    async def simulate_retrieval(self, session_id, digest, event):
        row = self.sessions[str(session_id)]
        if digest != row["action_hash"]:
            return {"error": "INVALID_RETRIEVAL_ACTION"}
        if row["status"] == "completed" and event == "correct_item_lifted":
            return {
                "id": row["id"],
                "status": "completed",
                "completed_at": row["completed_at"],
            }
        if row["status"] != "validated":
            return {"error": "RETRIEVAL_QR_ALREADY_USED"}
        if event == "wrong_item_lifted":
            if not row["wrong_item_out"]:
                row["wrong_item_out"] = True
                self.events.append("simulated_wrong_item_lifted")
        elif event == "item_returned":
            if row["wrong_item_out"]:
                row["wrong_item_out"] = False
                self.events.append("simulated_item_returned")
        elif event == "correct_item_lifted":
            if row["wrong_item_out"]:
                return {"error": "WRONG_ITEM_NOT_RETURNED"}
            row["status"] = "completed"
            row["completed_at"] = datetime.now(UTC).isoformat()
            self.item_status = "retrieved"
            self.slot_status = "available"
            self.logs.append(row["id"])
            self.events.extend(("simulated_correct_item_lifted", "retrieval_completed"))
        return {
            "id": row["id"],
            "status": row["status"],
            "wrong_item_out": row["wrong_item_out"],
            "completed_at": row.get("completed_at"),
        }

    async def retrieval_logs(self):
        return [
            {
                "id": str(uuid4()),
                "retrieval_session_id": session_id,
                "retriever": self.sessions[session_id]["display_name"],
                "item_summary": "Gold watch",
                "slot_code": "M-04",
                "retrieved_at": self.sessions[session_id]["completed_at"],
                "completion_source": "web_simulation",
            }
            for session_id in self.logs
        ]

    async def claimant_retrieval_logs(self, user_id):
        return [
            row
            for row in await self.retrieval_logs()
            if self.sessions[row["retrieval_session_id"]]["user_id"] == str(user_id)
        ]


def test_qr_tokens_are_unique_hashed_and_ttl_uses_configuration():
    repo = RetrievalRepo()
    settings = Settings(retrieval_token_pepper="a" * 48, retrieval_qr_ttl_minutes=180)
    user_id = uuid4()
    first = asyncio.run(issue(repo, settings, uuid4(), user_id, "Claimant"))
    second = asyncio.run(issue(repo, settings, uuid4(), user_id, "Claimant"))
    assert first["raw_token"] != second["raw_token"]
    assert first["qr_payload"] == QR_PREFIX + first["raw_token"]
    assert repo.sessions[first["id"]]["status"] == "cancelled"
    assert repo.sessions[second["id"]]["token_hash"] == token_hash(
        second["raw_token"], settings.retrieval_token_pepper
    )
    assert all(
        "raw_token" not in row and "qr_payload" not in row
        for row in repo.sessions.values()
    )
    assert datetime.fromisoformat(second["expires_at"]) - datetime.fromisoformat(
        second["issued_at"]
    ) == timedelta(hours=3)
    shorter = Settings(retrieval_token_pepper="a" * 48, retrieval_qr_ttl_minutes=45)
    replacement = asyncio.run(replace(repo, shorter, UUID(second["id"]), user_id))
    assert datetime.fromisoformat(replacement["expires_at"]) - datetime.fromisoformat(
        replacement["issued_at"]
    ) == timedelta(minutes=45)


def test_bad_format_unknown_expired_replaced_and_used_qr():
    repo = RetrievalRepo()
    settings = Settings(retrieval_token_pepper="a" * 48)
    with pytest.raises(ServiceError, match="INVALID_QR_FORMAT"):
        parse_qr_payload("https://example.com/not-sauli")
    with pytest.raises(ServiceError, match="INVALID_RETRIEVAL_TOKEN"):
        asyncio.run(validate(repo, settings, QR_PREFIX + "A" * 43))
    issued = asyncio.run(issue(repo, settings, uuid4(), uuid4(), None))
    session_id = issued["id"]
    repo.sessions[session_id]["expires_at"] = (
        datetime.now(UTC) - timedelta(seconds=1)
    ).isoformat()
    with pytest.raises(ServiceError, match="RETRIEVAL_QR_EXPIRED"):
        asyncio.run(validate(repo, settings, issued["qr_payload"]))
    replacement = asyncio.run(
        replace(
            repo, settings, UUID(session_id), UUID(repo.sessions[session_id]["user_id"])
        )
    )
    assert replacement["raw_token"] != issued["raw_token"]
    with pytest.raises(ServiceError, match="INVALID_RETRIEVAL_TOKEN"):
        asyncio.run(validate(repo, settings, issued["qr_payload"]))
    accepted = asyncio.run(validate(repo, settings, replacement["qr_payload"]))
    assert accepted["slot_code"] == "M-04"
    with pytest.raises(ServiceError, match="RETRIEVAL_QR_ALREADY_USED"):
        asyncio.run(validate(repo, settings, replacement["qr_payload"]))


def test_qr_rejects_unavailable_item_and_mismatched_slot():
    repo = RetrievalRepo()
    settings = Settings(retrieval_token_pepper="a" * 48)
    issued = asyncio.run(issue(repo, settings, uuid4(), uuid4(), None))
    repo.item_status = "archived"
    with pytest.raises(ServiceError, match="ITEM_NOT_AVAILABLE"):
        asyncio.run(validate(repo, settings, issued["qr_payload"]))
    repo.item_status = "claimed"
    repo.slot_status = "available"
    with pytest.raises(ServiceError, match="STORAGE_POSITION_MISMATCH"):
        asyncio.run(validate(repo, settings, issued["qr_payload"]))


def test_simulated_wrong_return_and_correct_removal_are_idempotent():
    repo = RetrievalRepo()
    settings = Settings(retrieval_token_pepper="a" * 48)
    issued = asyncio.run(issue(repo, settings, uuid4(), uuid4(), None))
    accepted = asyncio.run(validate(repo, settings, issued["qr_payload"]))
    session_id = UUID(accepted["id"])
    action = accepted["action_token"]
    with pytest.raises(ServiceError, match="INVALID_RETRIEVAL_ACTION"):
        asyncio.run(
            simulate(repo, settings, session_id, "A" * 43, "correct_item_lifted")
        )
    asyncio.run(simulate(repo, settings, session_id, action, "wrong_item_lifted"))
    asyncio.run(simulate(repo, settings, session_id, action, "wrong_item_lifted"))
    with pytest.raises(ServiceError, match="WRONG_ITEM_NOT_RETURNED"):
        asyncio.run(simulate(repo, settings, session_id, action, "correct_item_lifted"))
    assert repo.item_status == "claimed" and repo.slot_status == "occupied"
    asyncio.run(simulate(repo, settings, session_id, action, "item_returned"))
    asyncio.run(simulate(repo, settings, session_id, action, "item_returned"))
    assert repo.item_status == "claimed" and repo.slot_status == "occupied"
    completed = asyncio.run(
        simulate(repo, settings, session_id, action, "correct_item_lifted")
    )
    again = asyncio.run(
        simulate(repo, settings, session_id, action, "correct_item_lifted")
    )
    assert (
        completed["id"] == again["id"]
        and completed["status"] == again["status"] == "completed"
    )
    assert repo.item_status == "retrieved" and repo.slot_status == "available"
    assert repo.logs == [accepted["id"]]
    assert (
        repo.events.count("simulated_wrong_item_lifted")
        == repo.events.count("simulated_item_returned")
        == 1
    )


def test_api_requires_claimant_for_status_and_admin_for_logs():
    repo = RetrievalRepo()
    claimant_id, other_id, admin_id = uuid4(), uuid4(), uuid4()
    app = create_app(
        Settings(retrieval_token_pepper="a" * 48, sauli_admin_user_id=str(admin_id))
    )
    app.state.items = repo
    app.dependency_overrides[get_current_user] = lambda: UserResponse(
        id=str(claimant_id), name="Claimant"
    )
    with TestClient(app) as client:
        created = client.post(
            "/api/retrieval-sessions", json={"match_candidate_id": str(uuid4())}
        )
        assert created.status_code == 200, created.json()
        session_id = created.json()["id"]
        assert "slot_code" not in created.json()
        initial = client.get(f"/api/retrieval-sessions/{session_id}")
        assert initial.status_code == 200 and initial.json()["slot_code"] is None
        app.dependency_overrides[get_current_user] = lambda: UserResponse(
            id=str(other_id)
        )
        assert client.get(f"/api/retrieval-sessions/{session_id}").status_code == 404
        assert client.get("/api/retrieval-sessions/history").json() == []
        assert (
            client.post(f"/api/retrieval-sessions/{session_id}/replace").status_code
            == 404
        )
        assert client.get("/api/retrieval-sessions/admin/logs").status_code == 403
        app.dependency_overrides[get_current_user] = lambda: UserResponse(
            id=str(admin_id), role="admin"
        )
        assert client.get("/api/retrieval-sessions/admin/logs").status_code == 200


def test_pc_retrieval_api_path_releases_slot_and_rejects_rescan():
    repo = RetrievalRepo()
    claimant_id, other_id, admin_id = uuid4(), uuid4(), uuid4()
    app = create_app(
        Settings(retrieval_token_pepper="a" * 48, sauli_admin_user_id=str(admin_id))
    )
    app.state.items = repo
    app.dependency_overrides[get_current_user] = lambda: UserResponse(
        id=str(claimant_id), name="Test claimant"
    )
    with TestClient(app) as client:
        issued = client.post(
            "/api/retrieval-sessions", json={"match_candidate_id": str(uuid4())}
        ).json()
        assert issued["status"] == "issued" and "M-04" not in str(issued)
        accepted = client.post(
            "/api/retrieval-sessions/validate",
            json={"qr_payload": issued["qr_payload"]},
        )
        assert accepted.status_code == 200
        assert accepted.json()["slot_code"] == "M-04"
        assert (
            client.post(
                "/api/retrieval-sessions/validate",
                json={"qr_payload": issued["qr_payload"]},
            ).json()["error"]["code"]
            == "RETRIEVAL_QR_ALREADY_USED"
        )
        route = f"/api/retrieval-sessions/{issued['id']}"
        headers = {"X-Retrieval-Action": accepted.json()["action_token"]}
        location = client.get(route).json()
        assert location["status"] == "validated"
        assert location["slot_code"] == "M-04" and location["section"] == "medium"
        assert location["wrong_item_out"] is False
        assert client.post(route + "/simulate-wrong-item", headers=headers).json()[
            "wrong_item_out"
        ]
        assert client.get(route).json()["wrong_item_out"] is True
        assert (
            client.post(route + "/simulate-item-returned", headers=headers).json()[
                "wrong_item_out"
            ]
            is False
        )
        assert client.get(route).json()["wrong_item_out"] is False
        completed = client.post(route + "/simulate-completion", headers=headers)
        assert (
            completed.status_code == 200 and completed.json()["status"] == "completed"
        )
        assert (
            client.post(route + "/simulate-completion", headers=headers).json()[
                "status"
            ]
            == "completed"
        )
        assert (
            repo.item_status == "retrieved"
            and repo.slot_status == "available"
            and len(repo.logs) == 1
        )
        receipt = client.get(route).json()
        assert receipt["completed"] is True and receipt["slot_code"] == "M-04"
        assert receipt["completed_at"] and receipt["wrong_item_out"] is False
        history = client.get("/api/retrieval-sessions/history")
        assert history.status_code == 200 and history.json()[0]["slot_code"] == "M-04"
        app.dependency_overrides[get_current_user] = lambda: UserResponse(
            id=str(other_id)
        )
        assert client.get("/api/retrieval-sessions/history").json() == []
        app.dependency_overrides[get_current_user] = lambda: UserResponse(
            id=str(admin_id), role="admin"
        )
        logs = client.get("/api/retrieval-sessions/admin/logs")
        assert logs.status_code == 200 and logs.json()[0]["slot_code"] == "M-04"
        assert logs.json()[0]["completion_source"] == "web_simulation"


def test_live_status_works_before_the_additive_rpc_migration_is_applied():
    """An existing project can sync phone and kiosk during migration rollout."""
    session_id, claimant_id, slot_id = uuid4(), uuid4(), uuid4()
    status = "validated"
    wrong_item_out = True

    class Query:
        def __init__(self, table):
            self.table = table
            self.filters = {}

        def select(self, *_args):
            return self

        def eq(self, column, value):
            self.filters[column] = value
            return self

        def order(self, *_args, **_kwargs):
            return self

        def limit(self, *_args):
            return self

        def execute(self):
            if self.table == "retrieval_sessions":
                assert self.filters == {
                    "id": str(session_id),
                    "claimant_user_id": str(claimant_id),
                }
                rows = [
                    {
                        "claimant_display_name": "Claimant",
                        "wrong_item_out": wrong_item_out,
                        "validated_at": "2026-10-11T01:00:00Z",
                        "completed_at": None,
                    }
                ]
            elif self.table == "retrieval_events":
                assert self.filters["retrieval_session_id"] == str(session_id)
                assert self.filters["event_type"] == "qr_validated"
                rows = [{"storage_slot_id": str(slot_id)}]
            else:
                assert self.table == "storage_slots" and self.filters["id"] == str(
                    slot_id
                )
                rows = [{"code": "P-07", "size_class": "pocket"}]
            return SimpleNamespace(data=rows)

    repo = SupabaseFoundItemRepository(Settings())
    repo.client = SimpleNamespace(table=lambda name: Query(name))

    async def old_rpc(_name, _params):
        return {
            "id": str(session_id),
            "status": status,
            "issued_at": "2026-10-11T00:00:00Z",
            "expires_at": "2026-10-11T03:00:00Z",
            "item_summary": "Gold watch",
            "can_replace": False,
            "completed": status == "completed",
        }

    repo.retrieval_rpc = old_rpc
    live = asyncio.run(repo.retrieval_status(session_id, claimant_id))
    assert live["slot_code"] == "P-07" and live["section"] == "pocket"
    assert live["wrong_item_out"] is True and live["retriever"] == "Claimant"
    wrong_item_out = False
    status = "completed"
    receipt = asyncio.run(repo.retrieval_status(session_id, claimant_id))
    assert receipt["wrong_item_out"] is False and receipt["slot_code"] == "P-07"


def test_production_requires_a_real_pepper():
    with pytest.raises(ValueError, match="RETRIEVAL_TOKEN_PEPPER"):
        Settings(environment="production", retrieval_token_pepper=None)
    with pytest.raises(ValueError, match="RETRIEVAL_TOKEN_PEPPER"):
        Settings(
            environment="production",
            retrieval_token_pepper="<long-random-server-only-secret-at-least-32-characters>",
        )
    assert (
        Settings(
            environment="production", retrieval_token_pepper="r" * 48
        ).retrieval_token_pepper
        == "r" * 48
    )


def test_migration_enforces_one_active_qr_and_atomic_slot_release():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "token_hash text not null unique" in sql
    assert "where status in ('issued','validated')" in sql
    assert "for update" in sql
    assert "status = 'retrieved'" in sql
    assert "status = 'available',current_found_item_id = null" in sql
    assert "retrieval_session_id uuid not null unique" in sql
    assert "revoke all on public.retrieval_sessions" in sql
    assert "from public,anon,authenticated" in sql
    live_sql = LIVE_STATUS_MIGRATION.read_text(encoding="utf-8").lower()
    assert "v_session.status in ('validated','completed')" in live_sql
    assert "'wrong_item_out'" in live_sql
    assert "'slot_code',v_slot_code" in live_sql
    assert "from public,anon,authenticated" in live_sql


def test_completed_retrieval_resolves_only_its_accepted_report_and_backfills_prior_sessions():
    sql = RESOLVED_REPORT_MIGRATION.read_text(encoding="utf-8").lower()
    assert "after update of status on public.retrieval_sessions" in sql
    assert "new.status = 'completed' and old.status is distinct from new.status" in sql
    assert "candidate.id = new.match_candidate_id" in sql
    assert "candidate.found_item_id = new.found_item_id" in sql
    assert "report.claimant_user_id = new.claimant_user_id" in sql
    assert "candidate.decision = 'accepted'" in sql
    assert "report.status = 'matched'" in sql
    assert "set status = 'resolved'" in sql
    assert "session.status = 'completed'" in sql
    assert "item.status = 'retrieved'" in sql
