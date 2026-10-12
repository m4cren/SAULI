"""Missing-report matching and EmailJS behavior without live external services."""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.config import Settings
from app.core.errors import ServiceError
from app.main import create_app
from app.repositories.supabase_found_items import SupabaseFoundItemRepository
from app.schemas.auth import UserResponse
from app.schemas.search import CandidateBatch, CandidateComparison
from app.services.email_notifications import EmailJSClient, deliver_one, template_params
from app.services.missing_reports import (
    evaluate_report,
    process_matching_job,
    report_detail,
)


class ReportRepo:
    def __init__(self, user_id):
        self.user_id = user_id
        self.rows = {}

    async def create_missing_report(
        self, search_id, user_id, email, enabled, name, key
    ):
        assert user_id == self.user_id and name == "Claimant"
        if search_id in self.rows:
            return self.rows[search_id]
        row = {
            "id": str(uuid4()),
            "idempotency_key": str(key),
            "search_request_id": str(search_id),
            "claimant_user_id": str(user_id),
            "claimant_name": name,
            "summary": "AI summary reused from the original search",
            "notification_email": email,
            "email_notifications_enabled": enabled,
            "status": "active",
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        self.rows[search_id] = row
        return row

    async def get_missing_report(self, report_id, user_id):
        return next((row for row in self.rows.values()
                     if row["id"] == str(report_id)
                     and row["claimant_user_id"] == str(user_id)), None)

    async def list_missing_reports(self, user_id):
        return sorted((row for row in self.rows.values()
                       if row["claimant_user_id"] == str(user_id)),
                      key=lambda row: row["created_at"], reverse=True)

    async def search_candidates(self, _search_id):
        return []


def test_posting_report_requires_claimant_authentication():
    app = create_app(Settings())
    with TestClient(app) as client:
        response = client.post(
            "/api/missing-reports",
            json={
                "search_request_id": str(uuid4()),
                "notification_email": "owner@example.com",
                "email_notifications_enabled": True,
            },
            headers={"X-Idempotency-Key": str(uuid4())},
        )
    assert response.status_code == 401


def test_authenticated_report_post_reuses_search_and_is_idempotent():
    user_id, search_id = uuid4(), uuid4()
    app = create_app(Settings())
    repo = ReportRepo(user_id)
    app.state.items = repo
    app.dependency_overrides[get_current_user] = lambda: UserResponse(
        id=str(user_id), name="Claimant", auth_provider="facebook"
    )
    with TestClient(app) as client:
        payload = {
            "search_request_id": str(search_id),
            "notification_email": "  User@Example.com  ",
            "email_notifications_enabled": True,
        }
        first = client.post(
            "/api/missing-reports",
            json=payload,
            headers={"X-Idempotency-Key": str(uuid4())},
        )
        second = client.post(
            "/api/missing-reports",
            json=payload,
            headers={"X-Idempotency-Key": str(uuid4())},
        )
        assert first.status_code == second.status_code == 200
        assert first.json()["id"] == second.json()["id"]
        assert len(repo.rows) == 1
        assert first.json()["notification_email"] == "user@example.com"
        assert first.json()["summary"] == "AI summary reused from the original search"
        assert set(first.json()) == {
            "id", "search_request_id", "summary", "notification_email",
            "email_notifications_enabled", "status", "created_at",
        }
        detail = client.get(f"/api/missing-reports/{first.json()['id']}")
        assert detail.status_code == 200
        assert detail.json()["candidate"] is None
        assert "claimant_user_id" not in detail.json()
        assert "idempotency_key" not in detail.json()
        listed = client.get("/api/missing-reports")
        assert listed.status_code == 200
        assert listed.json() == [first.json()]
        app.dependency_overrides[get_current_user] = lambda: UserResponse(
            id=str(uuid4()), name="Another claimant", auth_provider="facebook"
        )
        assert client.get("/api/missing-reports").json() == []
        assert client.get(f"/api/missing-reports/{first.json()['id']}").status_code == 404
        app.dependency_overrides[get_current_user] = lambda: UserResponse(
            id=str(user_id), name="Claimant", auth_provider="facebook"
        )
        assert (
            client.post(
                "/api/missing-reports",
                json={**payload, "notification_email": "bad"},
                headers={"X-Idempotency-Key": str(uuid4())},
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/missing-reports",
                json={**payload, "notification_email": ""},
                headers={"X-Idempotency-Key": str(uuid4())},
            ).status_code
            == 422
        )


def test_admin_and_non_facebook_accounts_cannot_post_or_view_claimant_reports():
    user_id, search_id = uuid4(), uuid4()
    app = create_app(Settings())
    repo = ReportRepo(user_id)
    app.state.items = repo
    payload = {
        "search_request_id": str(search_id),
        "notification_email": "owner@example.com",
        "email_notifications_enabled": True,
    }
    with TestClient(app) as client:
        for user in (
            UserResponse(id=str(user_id), role="admin", auth_provider="email"),
            UserResponse(id=str(user_id), auth_provider="email"),
        ):
            app.dependency_overrides[get_current_user] = lambda user=user: user
            response = client.post(
                "/api/missing-reports", json=payload,
                headers={"X-Idempotency-Key": str(uuid4())},
            )
            assert response.status_code == 403
            assert client.get("/api/missing-reports").status_code == 403
            assert client.get(f"/api/missing-reports/{uuid4()}").status_code == 403
    assert repo.rows == {}


class MatchingRepo:
    def __init__(self, rows):
        self.rows = rows
        self.stored = []
        self.report_id = uuid4()
        self.search_id = uuid4()
        self.report = {
            "id": str(self.report_id),
            "search_request_id": str(self.search_id),
            "status": "active",
        }

    async def search_request(self, _id):
        return {
            "description": "black leather wallet with silver logo",
            "category": "wallet",
            "color": None,
            "last_seen_location": "Library",
            "last_seen_at": "2026-10-10T00:00:00Z",
            "filters": {},
            "query_analysis": {
                "generic_name": "wallet",
                "specific_description": "black leather wallet",
                "alternative_names": [],
                "category": "wallet",
                "colors": ["black"],
                "material": ["leather"],
                "brand": None,
                "model": None,
                "markings": [],
                "distinctive_features": [],
                "condition": [],
                "damage": [],
                "components": [],
                "location": "Library",
                "last_seen_at": "2026-10-10T00:00:00Z",
                "searchable_summary": "Missing black leather wallet",
                "uncertainty": [],
            },
        }

    async def eligible_items(self, *_args):
        return self.rows

    async def store_report_matches(self, report_id, job_id, candidates, threshold):
        assert report_id == self.report_id and threshold == 65
        self.stored.append((job_id, candidates))
        return {"queued": bool(candidates)}

    async def get_missing_report(self, _id):
        return self.report

    async def active_missing_reports(self):
        return [self.report]


class ComparisonGateway:
    def __init__(self):
        self.seen = []

    async def structured(self, _model, prompt, _schema):
        payload = (
            json.loads(prompt.split("Candidates JSON:\n", 1)[1])
            if "Candidates JSON:\n" in prompt
            else [json.loads(prompt.split("Candidate JSON:\n", 1)[1])]
        )
        self.seen.extend(row["id"] for row in payload)
        comparisons = [
            CandidateComparison(
                candidate_id=UUID(row["id"]),
                similarity=0.94,
                matched_attributes=["wallet", "black"],
                differences=[],
                explanation="Physical details align",
                plausible=True,
            )
            for row in payload
        ]
        return (
            CandidateBatch(comparisons=comparisons)
            if len(payload) > 1
            else comparisons[0]
        )


def item(
    *, placed=True, occupied=True, created="2026-10-11T00:00:00Z", category="wallet"
):
    return {
        "id": str(uuid4()),
        "status": "available",
        "placement_status": "placed" if placed else "reserved",
        "slot_status": "occupied" if occupied else "reserved",
        "created_at": created,
        "found_at": created,
        "generic_name": "wallet",
        "object_name": "Black wallet",
        "category": category,
        "colors": ["black"],
        "materials": ["leather"],
        "found_location": "Library",
    }


def test_report_posting_checks_only_eligible_existing_items_and_queues_best():
    valid = item()
    repo = MatchingRepo(
        [
            valid,
            item(placed=False),
            item(occupied=False),
            item(created="2026-10-09T00:00:00Z"),
            item(category="helmet"),
        ]
    )
    gateway = ComparisonGateway()
    result = asyncio.run(
        evaluate_report(repo, gateway, Settings(), repo.report, uuid4())
    )
    assert result["queued"] is True
    assert gateway.seen == [valid["id"]]
    assert len(repo.stored[0][1]) == 1
    assert repo.stored[0][1][0]["rank_score"] >= 65


def test_placement_job_checks_only_its_occupied_item():
    valid, other = item(), item()
    repo = MatchingRepo([valid, other])
    gateway = ComparisonGateway()
    job = {"id": str(uuid4()), "kind": "item_placed", "found_item_id": valid["id"]}
    asyncio.run(process_matching_job(repo, gateway, Settings(), job))
    assert gateway.seen == [valid["id"]]
    assert len(repo.stored) == 1
    repo = MatchingRepo([item(placed=False)])
    gateway = ComparisonGateway()
    asyncio.run(process_matching_job(repo, gateway, Settings(), job))
    assert gateway.seen == [] and repo.stored == []


def test_report_review_hides_low_scoring_search_candidates():
    class ReviewRepo:
        def __init__(self):
            self.lookups = []

        async def search_candidates(self, _id):
            return [
                {
                    "id": str(uuid4()),
                    "found_item_id": str(uuid4()),
                    "rank_score": 45,
                    "decision": "pending",
                },
                {
                    "id": str(uuid4()),
                    "found_item_id": str(uuid4()),
                    "rank_score": 80,
                    "decision": "rejected",
                },
            ]

        async def get_item(self, item_id):
            self.lookups.append(item_id)

    repo = ReviewRepo()
    report = {"id": str(uuid4()), "search_request_id": str(uuid4()), "status": "active"}
    detail = asyncio.run(report_detail(repo, report, 65))
    assert detail["candidate"] is None
    assert detail["candidate_decision"] == "rejected"
    assert repo.lookups == []


def test_report_detail_serializes_a_pending_candidate_without_a_500():
    user_id, search_id, report_id, item_id, candidate_id = (uuid4() for _ in range(5))

    class PendingRepo(ReportRepo):
        async def search_candidates(self, _search_id):
            return [{
                "id": str(candidate_id), "found_item_id": str(item_id),
                "rank": 1, "rank_score": 77.33, "decision": "pending",
                "matched_attributes": ["blue"], "differences": [],
                "explanation": "Visible details align",
                "score_breakdown": {"ai_similarity": 0.9, "deterministic_features": 0.7,
                                    "location_similarity": 0.5, "time_proximity": 0.5},
            }]

        async def get_item(self, _item_id):
            return {
                **item(), "id": str(item_id), "object_name": "Blue bottle",
                "extraction_summary": "Blue reusable water bottle",
            }

        async def signed_url(self, _path):
            return None

    app = create_app(Settings())
    repo = PendingRepo(user_id)
    repo.rows[search_id] = {
        "id": str(report_id), "search_request_id": str(search_id),
        "claimant_user_id": str(user_id), "summary": "Lost blue bottle",
        "notification_email": "owner@example.com", "email_notifications_enabled": True,
        "status": "active", "created_at": datetime.now(UTC).isoformat(),
    }
    app.state.items = repo
    app.dependency_overrides[get_current_user] = lambda: UserResponse(
        id=str(user_id), name="Claimant", auth_provider="facebook"
    )
    with TestClient(app) as client:
        response = client.get(f"/api/missing-reports/{report_id}")
    assert response.status_code == 200
    assert response.json()["candidate"]["item_id"] == str(item_id)
    assert response.json()["candidate"]["match_candidate_id"] == str(candidate_id)
    assert response.json()["candidate"]["found_at"].endswith("Z")


class EmailRepo:
    def __init__(self):
        self.notice = {
            "id": str(uuid4()),
            "missing_report_id": str(uuid4()),
            "found_item_id": str(uuid4()),
            "match_candidate_id": str(uuid4()),
            "attempt_count": 1,
        }
        self.final = []

    async def claim_email_notification(self):
        notice, self.notice = self.notice, None
        return notice

    async def finish_email_notification(
        self, notice_id, status, error=None, response=None
    ):
        self.final.append((notice_id, status, error, response))

    async def get_missing_report(self, _id):
        return {
            "id": str(uuid4()),
            "claimant_name": "Claimant",
            "notification_email": "owner@example.com",
            "status": "active",
            "email_notifications_enabled": True,
        }

    async def get_match_decision(self, _id):
        return "pending"

    async def get_item(self, _id):
        return {
            "generic_name": "wallet",
            "found_location": "Library",
            "found_at": "2026-10-12T00:00:00Z",
            "extraction_summary": "PRIVATE SERIAL 123",
            "status": "available",
            "placement_status": "placed",
            "slot_status": "occupied",
        }


def send_with_status(code, settings, repo):
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(code, text="provider response")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    sender = EmailJSClient(settings, client)
    try:
        asyncio.run(deliver_one(repo, settings, sender))
    finally:
        asyncio.run(client.aclose())
    return seen


def test_disabled_and_unconfigured_email_never_call_provider():
    repo = EmailRepo()
    seen = send_with_status(200, Settings(emailjs_enabled=False), repo)
    assert seen == [] and repo.final[0][1] == "skipped_disabled"
    repo = EmailRepo()
    seen = send_with_status(
        200,
        Settings(
            emailjs_enabled=True,
            emailjs_service_id=None,
            emailjs_template_id=None,
            emailjs_public_key=None,
            emailjs_private_key=None,
        ),
        repo,
    )
    assert seen == [] and repo.final[0][1] == "skipped_unconfigured"


def test_rejected_candidate_is_cancelled_without_email_request():
    class RejectedRepo(EmailRepo):
        async def get_match_decision(self, _id):
            return "rejected"

    repo = RejectedRepo()
    settings = Settings(
        emailjs_enabled=True,
        emailjs_service_id="service",
        emailjs_template_id="template",
        emailjs_public_key="public",
        emailjs_private_key="private",
    )
    assert send_with_status(200, settings, repo) == []
    assert repo.final[0][1] == "cancelled"


def test_database_failure_before_email_send_is_retryable():
    class UnavailableRepo(EmailRepo):
        async def get_missing_report(self, _id):
            raise ServiceError("SUPABASE_UNAVAILABLE", "Temporary outage", 503)

    repo = UnavailableRepo()
    settings = Settings(
        emailjs_enabled=True,
        emailjs_service_id="service",
        emailjs_template_id="template",
        emailjs_public_key="public",
        emailjs_private_key="private",
    )
    assert send_with_status(200, settings, repo) == []
    assert repo.final[0][1] == "retry_pending"


def test_emailjs_payload_success_retry_and_permanent_failure():
    settings = Settings(
        emailjs_enabled=True,
        emailjs_service_id="service",
        emailjs_template_id="template",
        emailjs_public_key="public",
        emailjs_private_key="private",
    )
    repo = EmailRepo()
    seen = send_with_status(200, settings, repo)
    assert repo.final[0][1] == "sent"
    assert seen[0]["service_id"] == "service" and seen[0]["accessToken"] == "private"
    params = seen[0]["template_params"]
    assert set(params) == {
        "to_email",
        "recipient_name",
        "item_summary",
        "found_location",
        "found_date",
        "match_url",
    }
    assert params["to_email"] == "owner@example.com"
    assert params["found_date"] == "October 12, 2026 at 8:00 AM"
    assert params["match_url"].startswith("http://localhost:3000/missing/reports/")
    assert "PRIVATE SERIAL" not in str(params) and "P-" not in str(params)
    assert "private" not in str(repo.final)
    repo = EmailRepo()
    assert send_with_status(429, settings, repo) and repo.final[0][1] == "retry_pending"
    repo = EmailRepo()
    assert send_with_status(400, settings, repo) and repo.final[0][1] == "failed"
    repo = EmailRepo()
    assert send_with_status(403, settings, repo) and repo.final[0][1:] == (
        "failed", "Provider HTTP 403", "403"
    )
    repo = EmailRepo()
    assert (
        send_with_status(503, settings, repo) and repo.final[0][1] == "delivery_unknown"
    )


def test_private_key_is_optional_and_template_id_comes_from_config():
    settings = Settings(
        emailjs_enabled=True,
        emailjs_service_id="gmail-service",
        emailjs_template_id="saved-dashboard-template",
        emailjs_public_key="public",
        emailjs_private_key=None,
        frontend_base_url="https://sauli.example.com/",
    )
    repo = EmailRepo()
    seen = send_with_status(200, settings, repo)
    assert settings.emailjs_configured
    assert seen[0]["service_id"] == "gmail-service"
    assert seen[0]["template_id"] == "saved-dashboard-template"
    assert "accessToken" not in seen[0]
    assert seen[0]["template_params"]["match_url"].startswith(
        "https://sauli.example.com/missing/reports/"
    )
    assert "//missing" not in seen[0]["template_params"]["match_url"]


def test_invalid_recipient_and_localhost_production_url_never_send():
    class InvalidEmailRepo(EmailRepo):
        async def get_missing_report(self, report_id):
            report = await super().get_missing_report(report_id)
            report["notification_email"] = "not-an-email"
            return report

    settings = Settings(
        emailjs_enabled=True,
        emailjs_service_id="service",
        emailjs_template_id="template",
        emailjs_public_key="public",
    )
    repo = InvalidEmailRepo()
    assert send_with_status(200, settings, repo) == []
    assert (
        repo.final[0][1] == "failed"
        and repo.final[0][2] == "Invalid notification details"
    )

    production = Settings(
        emailjs_enabled=True,
        emailjs_service_id="service",
        emailjs_template_id="template",
        emailjs_public_key="public",
        environment="production",
        retrieval_token_pepper="x" * 48,
    )
    repo = EmailRepo()
    assert not production.emailjs_configured
    assert send_with_status(200, production, repo) == []
    assert repo.final[0][1] == "skipped_unconfigured"


def test_missing_display_name_falls_back_and_timezone_is_formatted():
    report = {
        "id": str(uuid4()),
        "claimant_name": "",
        "notification_email": "USER@example.com",
    }
    item = {
        "found_at": "2026-10-12T09:00:00Z",
        "generic_name": "wallet",
        "found_location": "LSPU-SPCC Library",
        "extraction_summary": "PRIVATE SERIAL 123",
    }
    params = template_params(report, item, "https://sauli.example.com/").model_dump()
    assert params["recipient_name"] == "SAULI user"
    assert params["to_email"] == "user@example.com"
    assert params["found_date"] == "October 12, 2026 at 5:00 PM"
    assert params["found_location"] == "LSPU-SPCC Library"
    assert "PRIVATE SERIAL" not in str(params)


def test_provider_timeout_keeps_unknown_delivery_out_of_automatic_retry():
    settings = Settings(
        emailjs_enabled=True,
        emailjs_service_id="service",
        emailjs_template_id="template",
        emailjs_public_key="public",
    )
    repo = EmailRepo()

    def handler(_request):
        raise httpx.ReadTimeout("request may have reached EmailJS")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        asyncio.run(deliver_one(repo, settings, EmailJSClient(settings, client)))
    finally:
        asyncio.run(client.aclose())
    assert repo.final[0][1] == "delivery_unknown"


def test_same_claimed_notification_is_not_sent_twice():
    settings = Settings(
        emailjs_enabled=True,
        emailjs_service_id="service",
        emailjs_template_id="template",
        emailjs_public_key="public",
    )
    repo = EmailRepo()
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, text="OK")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    sender = EmailJSClient(settings, client)
    try:
        assert asyncio.run(deliver_one(repo, settings, sender)) is True
        assert asyncio.run(deliver_one(repo, settings, sender)) is False
    finally:
        asyncio.run(client.aclose())
    assert len(requests) == 1
    assert repo.final[0][1] == "sent"


def test_admin_can_requeue_only_the_known_provider_denial_for_one_report():
    report_id, admin_id = uuid4(), uuid4()
    settings = Settings(
        emailjs_enabled=True, emailjs_service_id="service", emailjs_template_id="template",
        emailjs_public_key="public", sauli_admin_user_id=str(admin_id),
    )
    app = create_app(settings)

    class RetryRepo:
        def __init__(self):
            self.requested = []

        async def retry_provider_denied_email(self, requested_id):
            self.requested.append(requested_id)
            return 1

    repo = RetryRepo()
    app.state.items = repo
    app.dependency_overrides[get_current_user] = lambda: UserResponse(
        id=str(admin_id), role="admin", auth_provider="email"
    )
    with TestClient(app) as client:
        response = client.post(f"/api/missing-reports/admin/retry-provider-denied-email/{report_id}")
        assert response.status_code == 200
        assert response.json() == {"queued": 1}
        app.dependency_overrides[get_current_user] = lambda: UserResponse(
            id=str(uuid4()), auth_provider="facebook"
        )
        assert client.post(f"/api/missing-reports/admin/retry-provider-denied-email/{report_id}").status_code == 403
    assert repo.requested == [report_id]


def test_provider_denial_retry_filters_to_failed_403_and_active_report():
    report_id = uuid4()

    class FakeClient:
        def __init__(self):
            self.filters = []
            self.payload = None

        def table(self, name):
            assert name == "email_notifications"
            return self

        def update(self, payload):
            self.payload = payload
            return self

        def eq(self, field, value):
            self.filters.append((field, value))
            return self

        def select(self, field):
            assert field == "id"
            return self

        def execute(self):
            return SimpleNamespace(data=[{"id": str(uuid4())}])

    repo = SupabaseFoundItemRepository(Settings())
    fake_client = FakeClient()
    repo.client = fake_client

    async def active_report(_report_id):
        return {"status": "active", "email_notifications_enabled": True}

    repo.get_missing_report = active_report
    assert asyncio.run(repo.retry_provider_denied_email(report_id)) == 1
    assert set(fake_client.filters) == {
        ("missing_report_id", str(report_id)), ("status", "failed"),
        ("last_error", "Provider HTTP 403"), ("provider_response", "403"),
    }
    assert fake_client.payload["status"] == "pending"

    async def closed_report(_report_id):
        return {"status": "matched", "email_notifications_enabled": True}

    repo.get_missing_report = closed_report
    assert asyncio.run(repo.retry_provider_denied_email(report_id)) == 0


def test_sql_outbox_claims_and_reset_cover_new_tables():
    root = Path(__file__).resolve().parents[3] / "supabase"
    sql = (
        (root / "migrations/202610120001_sauli_email_notifications.sql")
        .read_text()
        .lower()
    )
    reset = (root / "reset_sauli_data.sql").read_text().lower()
    assert "unique(matching_job_id,missing_report_id)" in sql
    assert "for update skip locked" in sql
    assert "interval '1 second'" in sql
    assert "v_candidate.decision <> 'pending'" in sql
    assert "status = 'occupied'" in sql
    assert "status = 'matched'" in sql
    assert "public.email_notifications" in reset and "public.matching_jobs" in reset
