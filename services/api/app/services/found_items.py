"""Found-item confirmation and public allowlisted detail mapping."""

import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.core.errors import ServiceError
from app.services.analysis import contains_sensitive_document
from app.schemas.found_items import ConfirmedItemResponse, FoundItemAnalysis, FoundItemDetailsResponse
from app.services.images import ImageData

log = logging.getLogger("sauli.found_items")


def confirmed(row: dict, slot: dict) -> ConfirmedItemResponse:
    return ConfirmedItemResponse(item_id=UUID(str(row["id"])), status="available", summary=row["extraction_summary"],
        found_location=row["found_location"], found_at=datetime.fromisoformat(str(row["found_at"]).replace("Z", "+00:00")),
        storage_size=row["storage_size"], slot_code=slot["code"],
        section="Pocket-size" if slot["size_class"] == "pocket" else "Medium-size",
        slot_status=slot["status"], placement_status=row["placement_status"])


def normalized_search_document(analysis: FoundItemAnalysis, location: str, notes: str | None) -> str:
    parts = [analysis.generic_name, analysis.object_name, *analysis.alternative_names, analysis.category,
             analysis.subcategory, *analysis.colors, *analysis.material, analysis.brand or "",
             analysis.model_or_variant or "", *analysis.visible_markings, *analysis.distinctive_features,
             analysis.short_description, analysis.extraction_summary, location, notes or ""]
    return " ".join(" ".join(parts).lower().split())[:8000]


async def confirm_item(repo, key: UUID, front: ImageData, back: ImageData, location: str, notes: str | None,
                       analysis: FoundItemAnalysis, storage_size: str) -> ConfirmedItemResponse:
    if storage_size not in ("pocket", "medium"):
        raise ServiceError("INVALID_STORAGE_SIZE", "Choose pocket-size or medium-size storage before confirming.", 422)
    prior = await repo.find_by_key(key)
    if prior:
        slot = await repo.get_slot_for_item(UUID(str(prior["id"])))
        if not slot:
            raise ServiceError("STORAGE_STATE_CONFLICT", "The assigned position is unavailable. Please try again.", 409)
        return confirmed(prior, slot)
    item_id = uuid4()
    front_path = f"found-items/{item_id}/front.{front.extension}"
    back_path = f"found-items/{item_id}/back.{back.extension}"
    uploaded: list[str] = []
    try:
        await repo.upload(front_path, front.data, front.content_type)
        uploaded.append(front_path)
        await repo.upload(back_path, back.data, back.content_type)
        uploaded.append(back_path)
        row = {
            "id": str(item_id), "idempotency_key": str(key), "status": "available", "found_location": location,
            "finder_notes": notes, "found_at": datetime.now(timezone.utc).isoformat(),
            "generic_name": analysis.generic_name, "object_name": analysis.object_name,
            "alternative_names": analysis.alternative_names, "category": analysis.category,
            "subcategory": analysis.subcategory, "document_kind": analysis.document_kind,
            "document_owner_name": None, "colors": analysis.colors, "materials": analysis.material,
            "brand": analysis.brand, "model_or_variant": analysis.model_or_variant,
            "visible_markings": analysis.visible_markings, "functional_components": analysis.functional_components,
            "condition": analysis.condition, "condition_details": analysis.condition_details,
            "patterns": analysis.patterns, "distinctive_features": analysis.distinctive_features,
            "short_description": analysis.short_description, "extraction_summary": analysis.extraction_summary,
            "confidence": analysis.confidence, "needs_review": analysis.needs_review,
            "uncertainty_notes": analysis.uncertainty_notes, "analysis_json": analysis.model_dump(mode="json"),
            "search_document": normalized_search_document(analysis, location, notes),
            "front_image_path": front_path, "back_image_path": back_path,
        }
        assigned = await repo.reserve_item(row, storage_size)
        return confirmed(assigned["item"], assigned["slot"])
    except Exception as exc:
        if isinstance(exc, ServiceError) and exc.code == "DATABASE_INSERT_FAILED":
            prior = await repo.find_by_key(key)
            if prior:
                slot = await repo.get_slot_for_item(UUID(str(prior["id"])))
                if slot:
                    return confirmed(prior, slot)
        if uploaded:
            try:
                await repo.remove(uploaded)
            except Exception:
                log.exception("Private image cleanup failed for %s object(s)", len(uploaded))
        if isinstance(exc, ServiceError):
            raise
        log.exception("Unexpected found-item save failure")
        raise ServiceError("INTERNAL_SERVICE_FAILURE", "The item could not be saved. Please try again.", 500) from exc


async def public_details(repo, item_id: UUID) -> FoundItemDetailsResponse:
    row = await repo.get_item(item_id)
    if not row:
        raise ServiceError("ITEM_NOT_FOUND", "This item could not be found.", 404)
    sensitive = contains_sensitive_document(row.get("document_kind"), row.get("extraction_summary"))
    front_url = None if sensitive else await repo.signed_url(row.get("front_image_path"))
    back_url = None if sensitive else await repo.signed_url(row.get("back_image_path"))
    return FoundItemDetailsResponse(
        item_id=UUID(str(row["id"])), status=row["status"], name=row["object_name"], summary=row["extraction_summary"],
        category=row["category"], colors=row["colors"], visible_markings=row["visible_markings"],
        condition=row["condition"], found_location=row["found_location"], found_at=datetime.fromisoformat(str(row["found_at"]).replace("Z", "+00:00")),
        front_image_url=front_url, back_image_url=back_url,
    )
