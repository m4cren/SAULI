import asyncio
import json
from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from ollama import ResponseError
from PIL import Image

from app.config import Settings
from app.core.errors import ServiceError
from app.integrations.ollama import OllamaGateway, first_json_object, response_payload
from app.main import create_app
from app.repositories.supabase_found_items import SupabaseFoundItemRepository
from app.schemas.found_items import FoundItemAnalysis
from app.schemas.search import CandidateComparison, QueryAnalysis, SearchRequest
from app.services.analysis import reconcile, safe_analysis
from app.services.found_items import confirm_item, public_details
from app.services.images import validate_image
from app.services.matching import eligible, run_search, score


def png(width=2, height=2):
    stream = BytesIO()
    Image.new("RGB", (width, height), "blue").save(stream, format="PNG")
    return stream.getvalue()


def analysis():
    return FoundItemAnalysis.model_validate({
        "views_consistent": True, "generic_name": "bottle", "object_name": "Blue bottle",
        "alternative_names": [], "object_count": 1, "component_counts": [], "count_is_estimate": False,
        "count_confidence": "high", "counting_notes": [], "category": "drinkware", "subcategory": "bottle",
        "document_kind": "none", "document_owner_name": None, "colors": ["blue"], "material": ["metal"],
        "brand": None, "model_or_variant": None, "visible_markings": [], "functional_components": [],
        "condition": "good", "condition_visibility": "two sides", "condition_confidence": "medium",
        "surface_assessments": [], "condition_details": [], "patterns": [], "distinctive_features": [],
        "likely_use": "carrying water", "short_description": "Blue bottle", "confidence": "medium",
        "needs_review": False, "uncertainty_notes": [], "extraction_summary": "Blue metal bottle",
        "received_view_count": 2,
        "view_observations": [{"image_index": index, "visible_region": "side", "image_quality": "clear",
                               "damage_observations": [], "notes": []} for index in (1, 2)],
    })


class FakeGateway:
    def __init__(self, answer=None):
        self.answer = answer or analysis()
        self.images = None
        self.calls = 0

    async def structured(self, _model, _prompt, _schema, images=None):
        self.calls += 1
        self.images = images
        return self.answer


class FakeRepo:
    def __init__(self):
        self.items = {}
        self.uploaded = []
        self.removed = []
        self.fail_upload_at = None
        self.fail_insert = False
        self.rows = []
        self.search_row = None
        self.audits = []

    async def find_by_key(self, key):
        return self.items.get(str(key))

    async def upload(self, path, data, mime):
        if len(self.uploaded) + 1 == self.fail_upload_at:
            raise ServiceError("STORAGE_UPLOAD_FAILED", "Upload failed", 503)
        self.uploaded.append((path, data, mime))

    async def remove(self, paths):
        self.removed.extend(paths)

    async def insert_item(self, row):
        if self.fail_insert:
            raise ServiceError("DATABASE_INSERT_FAILED", "Insert failed", 503)
        self.items[row["idempotency_key"]] = row
        return row

    async def find_search_by_key(self, _key):
        return None

    async def eligible_items(self, _last_seen, _limit):
        return self.rows

    async def create_search(self, row, candidates):
        self.search_row, self.audits = row, candidates

    async def signed_url(self, _path):
        return None


def test_image_validation_rejects_mismatch_damage_limits_and_animation():
    settings = Settings(max_image_bytes=1000, max_image_pixels=4)
    assert validate_image(png(), "image/png", settings).extension == "png"
    for data, mime, code in ((png(), "image/jpeg", "INVALID_IMAGE"), (b"bad", "image/png", "INVALID_IMAGE"),
                             (png(), "image/gif", "UNSUPPORTED_FORMAT"), (b"x" * 1001, "image/png", "IMAGE_TOO_LARGE"),
                             (png(3, 3), "image/png", "EXCESSIVE_DIMENSIONS")):
        with pytest.raises(ServiceError) as error:
            validate_image(data, mime, settings)
        assert error.value.code == code
    stream = BytesIO()
    Image.new("RGB", (2, 2), "red").save(stream, format="WEBP", save_all=True,
        append_images=[Image.new("RGB", (2, 2), "blue")], duration=100, loop=0)
    with pytest.raises(ServiceError, match="INVALID_IMAGE"):
        validate_image(stream.getvalue(), "image/webp", Settings())


def test_ollama_wrappers_repair_and_timeout():
    assert first_json_object('prefix ```json\n{"a":1}\n```')["a"] == 1
    assert response_payload({"message": {"content": "", "thinking": '{"a":2}'}})["a"] == 2

    class Client:
        calls = 0
        async def chat(self, **_kwargs):
            self.calls += 1
            return {"message": {"content": "bad" if self.calls == 1 else analysis().model_dump_json()}}

    gateway = OllamaGateway("http://localhost:11434", 1)
    gateway.client = Client()
    result = asyncio.run(gateway.structured("model", "prompt", FoundItemAnalysis, [b"front", b"back"]))
    assert result.object_name == "Blue bottle" and gateway.client.calls == 2

    class Timeout:
        async def chat(self, **_kwargs):
            raise httpx.ReadTimeout("private host")
    gateway.client = Timeout()
    with pytest.raises(ServiceError, match="OLLAMA_TIMEOUT"):
        asyncio.run(gateway.structured("model", "prompt", FoundItemAnalysis))

    class MissingModel:
        async def chat(self, **_kwargs):
            raise ResponseError("private model detail", 404)
    gateway.client = MissingModel()
    with pytest.raises(ServiceError, match="OLLAMA_MODEL_MISSING"):
        asyncio.run(gateway.structured("model", "prompt", FoundItemAnalysis))

    class Disconnected:
        async def chat(self, **_kwargs):
            raise ConnectionError("private host")
    gateway.client = Disconnected()
    with pytest.raises(ServiceError, match="OLLAMA_UNAVAILABLE"):
        asyncio.run(gateway.structured("model", "prompt", FoundItemAnalysis))

    class Invalid:
        calls = 0
        async def chat(self, **_kwargs):
            self.calls += 1
            return {"message": {"content": "not JSON"}}
    gateway.client = Invalid()
    with pytest.raises(ServiceError, match="MALFORMED_AI_RESPONSE"):
        asyncio.run(gateway.structured("model", "prompt", FoundItemAnalysis))
    assert gateway.client.calls == 2


def test_analyze_api_preserves_order_and_safe_missing_images():
    app = create_app(Settings())
    with TestClient(app) as client:
        gateway = FakeGateway()
        app.state.ollama = gateway
        missing = client.post("/api/found-items/analyze", data={"found_location": "Library"})
        assert missing.status_code == 400 and missing.json()["error"]["code"] == "MISSING_IMAGE"
        front, back = png(), png(3, 3)
        result = client.post("/api/found-items/analyze", data={"found_location": "Library"}, files={
            "front_image": ("front.png", front, "image/png"), "back_image": ("back.png", back, "image/png")})
        assert result.status_code == 200
        assert gateway.images == [front, back]
        extra = client.post("/api/found-items/analyze", data={"found_location": "Library"}, files={
            "front_image": ("front.png", front, "image/png"), "back_image": ("back.png", back, "image/png"),
            "third_image": ("third.png", front, "image/png")})
        assert extra.status_code == 422 and extra.json()["error"]["code"] == "INVALID_REQUEST"
        missing_back = client.post("/api/found-items/analyze", data={"found_location": "Library"},
            files={"front_image": ("front.png", front, "image/png")})
        assert missing_back.json()["error"]["code"] == "MISSING_IMAGE"


def test_confirmation_idempotency_and_cleanup(caplog):
    repo = FakeRepo()
    front = validate_image(png(), "image/png", Settings())
    key = uuid4()
    saved = asyncio.run(confirm_item(repo, key, front, front, "Library", None, analysis()))
    duplicate = asyncio.run(confirm_item(repo, key, front, front, "Library", None, analysis()))
    assert saved.item_id == duplicate.item_id and len(repo.uploaded) == 2
    repo = FakeRepo()
    repo.fail_upload_at = 2
    with pytest.raises(ServiceError, match="STORAGE_UPLOAD_FAILED"):
        asyncio.run(confirm_item(repo, uuid4(), front, front, "Library", None, analysis()))
    assert len(repo.removed) == 1
    repo = FakeRepo()
    repo.fail_insert = True
    with pytest.raises(ServiceError, match="DATABASE_INSERT_FAILED"):
        asyncio.run(confirm_item(repo, uuid4(), front, front, "Library", None, analysis()))
    assert len(repo.removed) == 2
    class CleanupFails(FakeRepo):
        async def remove(self, _paths):
            raise OSError("private cleanup error")
    repo = CleanupFails()
    repo.fail_upload_at = 2
    with pytest.raises(ServiceError, match="STORAGE_UPLOAD_FAILED"):
        asyncio.run(confirm_item(repo, uuid4(), front, front, "Library", None, analysis()))
    assert "cleanup failed" in caplog.text.lower()


def test_confirm_and_store_route_accepts_reviewed_analysis():
    app = create_app(Settings())
    repo = FakeRepo()
    app.state.items = repo
    key = str(uuid4())

    def submit(client):
        return client.post("/api/found-items/confirm-and-store", headers={"X-Idempotency-Key": key},
            data={"found_location": "Canteen", "notes": "Minor dent on top", "analysis_json": analysis().model_dump_json()},
            files={"front_image": ("front.png", png(), "image/png"),
                   "back_image": ("back.png", png(), "image/png")})

    with TestClient(app) as client:
        first = submit(client)
        repeated = submit(client)

    assert first.status_code == repeated.status_code == 200
    assert first.json()["item_id"] == repeated.json()["item_id"]
    assert len(repo.uploaded) == 2


def test_correction_rejects_unchanged_result_and_redacts_documents():
    from app.schemas.found_items import ReconcileRequest
    current = analysis()
    request = ReconcileRequest(analysis=current, found_location="Library", correction_notes="It is green, not blue")
    with pytest.raises(ServiceError, match="INVALID_ANALYSIS"):
        asyncio.run(reconcile(FakeGateway(current), "model", request))
    revised = current.model_copy(update={"colors": ["green"], "extraction_summary": "Green metal bottle"})
    result = asyncio.run(reconcile(FakeGateway(revised), "model", request))
    assert result.summary == "Green metal bottle"
    document = current.model_copy(update={"document_kind": "school ID", "document_owner_name": "Jane Doe",
        "visible_markings": ["123456789"], "extraction_summary": "Jane Doe school ID 123456789"})
    protected = safe_analysis(document)
    assert "Jane" not in protected.model_dump_json() and "123456789" not in protected.model_dump_json()


@pytest.mark.parametrize("returned_indices", [(1,), (), (1, 1)])
def test_correction_keeps_both_captured_views_when_model_drops_one(returned_indices):
    from app.schemas.found_items import ReconcileRequest

    current = analysis()
    current.view_observations[1].damage_observations = ["No dents observed"]
    current.view_observations[1].notes = ["Looks plastic"]
    updated_views = [current.view_observations[index - 1].model_copy(deep=True) for index in returned_indices]
    revised = current.model_copy(update={
        "material": ["metal"],
        "condition_details": ["Finder reports a minor dent on top"],
        "extraction_summary": "Blue metal bottle with a minor dent on top",
        "received_view_count": len(returned_indices),
        "view_observations": updated_views,
    })
    request = ReconcileRequest(analysis=current, found_location="Canteen", correction_notes="It is metal and has a minor dent on top")
    result = asyncio.run(reconcile(FakeGateway(revised), "model", request))

    assert result.analysis.received_view_count == 2
    assert [view.image_index for view in result.analysis.view_observations] == [1, 2]
    assert result.analysis.material == ["metal"]
    assert "dent on top" in result.summary
    if 2 not in returned_indices:
        assert result.analysis.view_observations[1].damage_observations == []
        assert result.analysis.view_observations[1].notes == []


def test_correction_rejects_missing_original_capture_view():
    from app.schemas.found_items import ReconcileRequest

    current = analysis().model_copy(update={"view_observations": analysis().view_observations[:1]})
    revised = analysis().model_copy(update={"extraction_summary": "Corrected bottle"})
    request = ReconcileRequest(analysis=current, found_location="Canteen", correction_notes="It has a dent")
    with pytest.raises(ServiceError, match="INVALID_ANALYSIS"):
        asyncio.run(reconcile(FakeGateway(revised), "model", request))


def test_correction_does_not_count_repaired_view_metadata_as_a_change():
    from app.schemas.found_items import ReconcileRequest

    current = analysis()
    current.view_observations[1].notes = ["Blue cap"]
    dropped_view = current.model_copy(update={"received_view_count": 1,
                                              "view_observations": current.view_observations[:1]})
    request = ReconcileRequest(analysis=current, found_location="Canteen", correction_notes="It is not plastic")
    with pytest.raises(ServiceError, match="INVALID_ANALYSIS"):
        asyncio.run(reconcile(FakeGateway(dropped_view), "model", request))


def test_public_details_allowlist_and_private_image_fallback():
    class DetailsRepo:
        async def get_item(self, item_id):
            return {"id": str(item_id), "status": "available", "object_name": "school ID",
                "extraction_summary": "school ID; sensitive identifying details withheld.", "category": "Document",
                "colors": ["blue"], "visible_markings": [], "condition": "good", "found_location": "Library",
                "found_at": datetime.now(timezone.utc).isoformat(), "front_image_path": "private/front.png",
                "document_kind": "school ID", "analysis_json": {"private": "123456789"}}
        async def signed_url(self, _path):
            raise AssertionError("Sensitive document image must not be signed")
    details = asyncio.run(public_details(DetailsRepo(), uuid4())).model_dump()
    assert details["front_image_url"] is None and "analysis_json" not in details


def test_signed_url_is_short_lived_and_failure_returns_placeholder():
    class Bucket:
        fail = False
        def create_signed_url(self, path, ttl):
            assert path == "private/front.png" and ttl == 900
            if self.fail:
                raise OSError("private storage failure")
            return {"signedURL": "https://example.invalid/signed"}
    bucket = Bucket()
    class Storage:
        def from_(self, _name): return bucket
    class Client:
        storage = Storage()
    repo = SupabaseFoundItemRepository(Settings())
    repo.client = Client()
    assert asyncio.run(repo.signed_url("private/front.png")) == "https://example.invalid/signed"
    bucket.fail = True
    assert asyncio.run(repo.signed_url("private/front.png")) is None


@pytest.mark.parametrize("response", [None, SimpleNamespace(data={"id": "existing"})])
def test_optional_supabase_lookups_handle_no_row(response):
    class Query:
        def select(self, _columns): return self
        def eq(self, _column, _value): return self
        def maybe_single(self): return self
        def execute(self): return response

    class Client:
        def table(self, _name): return Query()

    repo = SupabaseFoundItemRepository(Settings())
    repo.client = Client()
    expected = response.data if response is not None else None
    assert asyncio.run(repo.find_by_key(uuid4())) == expected
    assert asyncio.run(repo.get_item(uuid4())) == expected
    assert asyncio.run(repo.find_search_by_key(uuid4())) == expected


def test_search_hard_eligibility_limit_and_audit():
    now = datetime.now(timezone.utc).isoformat()
    last_seen = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert not eligible({"status": "claimed", "found_at": now}, last_seen)
    assert not eligible({"status": "available", "found_at": "2025-01-01T00:00:00+00:00"}, last_seen)
    candidate_id = uuid4()
    comparison = CandidateComparison(candidate_id=candidate_id, similarity=0.9, matched_attributes=["blue"],
                                     differences=[], explanation="Blue bottle matches", plausible=True)
    repo = FakeRepo()
    repo.rows = [{"id": str(candidate_id), "status": "available", "found_at": now, "generic_name": "bottle",
                  "object_name": "Blue bottle", "category": "drinkware", "colors": ["blue"], "materials": ["metal"],
                  "found_location": "Library", "extraction_summary": "Blue bottle", "document_kind": "none",
                  "front_image_path": "private/front.png"},
                 {"id": str(uuid4()), "status": "claimed", "found_at": now}]

    class SearchGateway:
        async def structured(self, _model, _prompt, schema, images=None):
            if schema is QueryAnalysis:
                return QueryAnalysis(generic_name="bottle", specific_description="blue bottle", alternative_names=[],
                    category="drinkware", colors=["blue"], material=[], brand=None, model=None, markings=[],
                    distinctive_features=[], condition=[], damage=[], components=[], location="Library",
                    last_seen_at=None, searchable_summary="Blue bottle", uncertainty=[])
            return comparison

    request = SearchRequest(description="I lost a blue bottle", last_seen_location="Library", last_seen_at=last_seen)
    result = asyncio.run(run_search(repo, SearchGateway(), "model", request, uuid4()))
    assert len(result.results) == len(repo.audits) == 1
    assert result.results[0].rank_score == repo.audits[0]["rank_score"]
    assert repo.search_row["query_analysis"]["generic_name"] == "bottle"
    value, _ = score(comparison, 1, 1, 1)
    assert value == 94.5
