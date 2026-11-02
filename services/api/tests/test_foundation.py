from datetime import datetime, timedelta, timezone

import httpx
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app
from app.schemas.search import SearchRequest


class FakeAuthClient:
    def __init__(self, response: httpx.Response | Exception):
        self.response = response
        self.url = None
        self.headers = None

    async def get(self, url: str, *, headers: dict[str, str]):
        self.url = url
        self.headers = headers
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class FakeOllama:
    def __init__(self, result: list[str] | Exception):
        self.result = result

    async def list_model_names(self):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def make_app():
    return create_app(Settings(
        supabase_url="https://project.supabase.co",
        supabase_publishable_key="public-key",
    ))


def test_search_rejects_future_last_seen_time():
    future = datetime.now(timezone.utc) + timedelta(days=1)
    try:
        SearchRequest(description="Silver wristwatch", last_seen_at=future)
    except ValidationError as error:
        assert "Last-seen time cannot be in the future" in str(error)
    else:
        raise AssertionError("Future last-seen time was accepted")

    past = datetime.now(timezone.utc) - timedelta(days=1)
    assert SearchRequest(description="Silver wristwatch", last_seen_at=past).last_seen_at == past


def test_legacy_ollama_timeout_is_raised_for_vision():
    assert Settings(ollama_timeout_seconds=5).ollama_timeout_seconds == 180
    assert Settings(ollama_timeout_seconds=240).ollama_timeout_seconds == 240


def test_deployed_frontend_origin_is_normalized_for_cors_and_links():
    settings = Settings(
        frontend_origin="https://sauli-system.vercel.app/",
        frontend_base_url="https://sauli-system.vercel.app/",
        environment="production",
        retrieval_token_pepper="a" * 32,
    )
    assert settings.cors_origins == ("https://sauli-system.vercel.app",)
    assert settings.frontend_base_url == "https://sauli-system.vercel.app"
    with TestClient(create_app(settings)) as client:
        response = client.options(
            "/api/storage-slots",
            headers={
                "Origin": "https://sauli-system.vercel.app",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.headers["access-control-allow-origin"] == (
        "https://sauli-system.vercel.app"
    )


def test_local_frontend_can_preflight_found_item_analysis_in_development():
    settings = Settings(frontend_origin="https://sauli-system.vercel.app")
    assert settings.cors_origins == (
        "https://sauli-system.vercel.app",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    )
    with TestClient(create_app(settings)) as client:
        for origin in ("http://localhost:3000", "http://127.0.0.1:3000"):
            response = client.options(
                "/api/found-items/analyze",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
            )
            assert response.status_code == 200
            assert response.headers["access-control-allow-origin"] == origin


def test_production_cors_does_not_allow_localhost():
    settings = Settings(
        environment="production",
        retrieval_token_pepper="a" * 32,
    )
    with TestClient(create_app(settings)) as client:
        response = client.options(
            "/api/found-items/analyze",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_health_starts_without_supabase_or_ollama():
    with TestClient(create_app(Settings())) as client:
        health = client.get("/health").json()
        assert health["status"] == "degraded"
        assert health["api"] == "ready"
        assert health["supabase_database"] == "unavailable"


def test_missing_or_invalid_bearer_token():
    app = make_app()
    with TestClient(app) as client:
        assert client.get("/api/v1/me").status_code == 401
        assert client.get("/api/v1/me", headers={"Authorization": "Basic value"}).status_code == 401
        app.state.auth_http = FakeAuthClient(httpx.Response(401))
        assert client.get("/api/v1/me", headers={"Authorization": "Bearer invalid"}).status_code == 401


def test_me_uses_supabase_auth_user_endpoint():
    app = make_app()
    with TestClient(app) as client:
        auth = FakeAuthClient(httpx.Response(200, json={
            "id": "user-1", "email": None,
            "app_metadata": {"provider": "facebook"},
            "user_metadata": {"full_name": "Alex"},
        }))
        app.state.auth_http = auth
        result = client.get("/api/v1/me", headers={"Authorization": "Bearer app-access-token"})
        assert result.status_code == 200
        assert result.json() == {"id": "user-1", "email": None, "name": "Alex", "avatar_url": None, "role": None, "auth_provider": "facebook"}
        assert auth.url == "https://project.supabase.co/auth/v1/user"
        assert auth.headers == {"apikey": "public-key", "Authorization": "Bearer app-access-token"}


def test_sauli_admin_role_uses_trusted_app_metadata_without_changing_supabase_role():
    app = make_app()
    with TestClient(app) as client:
        app.state.auth_http = FakeAuthClient(httpx.Response(200, json={
            "id": "admin-1", "app_metadata": {"role": "authenticated", "sauli_role": "admin"},
        }))
        result = client.get("/api/v1/me", headers={"Authorization": "Bearer app-access-token"})
        assert result.status_code == 200
        assert result.json()["role"] == "admin"
        assert result.json()["auth_provider"] is None

        app.state.auth_http = FakeAuthClient(httpx.Response(200, json={
            "id": "user-1", "app_metadata": {"role": "authenticated"},
            "user_metadata": {"sauli_role": "admin"},
        }))
        result = client.get("/api/v1/me", headers={"Authorization": "Bearer app-access-token"})
        assert result.status_code == 200
        assert result.json()["role"] is None


def test_auth_service_failure_is_not_reported_as_bad_credentials():
    app = make_app()
    with TestClient(app) as client:
        app.state.auth_http = FakeAuthClient(httpx.ConnectError("private endpoint"))
        result = client.get("/api/v1/me", headers={"Authorization": "Bearer token"})
        assert result.status_code == 503
        assert "private endpoint" not in result.text


def test_ollama_status_success_and_connection_failure():
    app = make_app()
    with TestClient(app) as client:
        app.state.auth_http = FakeAuthClient(httpx.Response(200, json={"id": "user-1"}))
        app.state.ollama = FakeOllama(["model-one:latest"])
        headers = {"Authorization": "Bearer token"}
        result = client.get("/api/v1/ollama/status", headers=headers)
        assert result.status_code == 200
        assert result.json() == {"status": "connected", "models": ["model-one:latest"]}

        app.state.ollama = FakeOllama(ConnectionError("private host"))
        result = client.get("/api/v1/ollama/status", headers=headers)
        assert result.status_code == 503
        assert "private host" not in result.text

        app.state.ollama = FakeOllama(httpx.ReadTimeout("private host"))
        result = client.get("/api/v1/ollama/status", headers=headers)
        assert result.status_code == 504
        assert "private host" not in result.text
