"""Two-image analysis, correction, explicit save and safe item details."""

from uuid import UUID

from fastapi import APIRouter, File, Form, Header, Request, UploadFile
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.core.errors import ServiceError
from app.schemas.found_items import (AnalysisResponse, ConfirmedItemResponse, FoundItemDetailsResponse, SimulatePlacementRequest,
                                      ReconcileRequest, normalize_location_notes, strict_analysis_json)
from app.services.analysis import analyze, reconcile, safe_analysis
from app.services.found_items import confirm_item, public_details
from app.services.images import read_upload

router = APIRouter(prefix="/api/found-items", tags=["found-items"])


def location_notes(location: str, notes: str | None) -> tuple[str, str | None]:
    try:
        return normalize_location_notes(location, notes)
    except ValueError as exc:
        raise ServiceError("INVALID_REQUEST", str(exc), 422) from exc


def required_key(value: str | None) -> UUID:
    try:
        if value is None:
            raise ValueError("Missing key")
        return UUID(value)
    except ValueError as exc:
        raise ServiceError("INVALID_REQUEST", "A valid UUID X-Idempotency-Key is required.", 422) from exc


async def exact_image_pair(request: Request) -> None:
    form = await request.form()
    names = [name for name, value in form.multi_items() if isinstance(value, StarletteUploadFile)]
    if len(names) != 2 or sorted(names) != ["back_image", "front_image"]:
        if "front_image" not in names:
            raise ServiceError("MISSING_IMAGE", "The front image is required.", 400)
        if "back_image" not in names:
            raise ServiceError("MISSING_IMAGE", "The back image is required.", 400)
        raise ServiceError("INVALID_REQUEST", "Submit exactly one front image and one back image.", 422)


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_item(request: Request, front_image: UploadFile | None = File(None), back_image: UploadFile | None = File(None),
                       found_location: str = Form(""), notes: str | None = Form(None)):
    location, normalized_notes = location_notes(found_location, notes)
    await exact_image_pair(request)
    settings = request.app.state.settings
    front = await read_upload(front_image, "front", settings)
    back = await read_upload(back_image, "back", settings)
    return await analyze(request.app.state.ollama, settings.ollama_model, front, back, location, normalized_notes)


@router.post("/reconcile-review", response_model=AnalysisResponse)
async def reconcile_item(request: Request, payload: ReconcileRequest):
    return await reconcile(request.app.state.ollama, request.app.state.settings.ollama_model, payload)


@router.post("/confirm-and-store", response_model=ConfirmedItemResponse)
async def confirm_and_store(request: Request, front_image: UploadFile | None = File(None), back_image: UploadFile | None = File(None),
                            found_location: str = Form(""), notes: str | None = Form(None), analysis_json: str = Form(""),
                            storage_size: str = Form(""),
                            x_idempotency_key: str | None = Header(None)):
    key = required_key(x_idempotency_key)
    location, normalized_notes = location_notes(found_location, notes)
    existing = await request.app.state.items.find_by_key(key)
    if existing:
        from app.services.found_items import confirmed
        slot = await request.app.state.items.get_slot_for_item(UUID(str(existing["id"])))
        if not slot:
            raise ServiceError("STORAGE_STATE_CONFLICT", "The assigned position is unavailable. Please try again.", 409)
        return confirmed(existing, slot)
    await exact_image_pair(request)
    settings = request.app.state.settings
    front = await read_upload(front_image, "front", settings)
    back = await read_upload(back_image, "back", settings)
    try:
        analysis = safe_analysis(strict_analysis_json(analysis_json))
    except (ValueError, TypeError) as exc:
        raise ServiceError("INVALID_ANALYSIS", "The item analysis is incomplete or invalid. Please analyze it again.", 422) from exc
    return await confirm_item(request.app.state.items, key, front, back, location, normalized_notes, analysis, storage_size)


@router.post("/{item_id}/simulate-placement", response_model=ConfirmedItemResponse)
async def simulate_placement(request: Request, item_id: UUID, payload: SimulatePlacementRequest):
    from app.services.found_items import confirmed
    result = await request.app.state.items.simulate_placement(item_id, payload.slot_code)
    return confirmed(result["item"], result["slot"])


@router.get("/{item_id}", response_model=FoundItemDetailsResponse)
async def get_found_item(request: Request, item_id: UUID):
    return await public_details(request.app.state.items, item_id)
