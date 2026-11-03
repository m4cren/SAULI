"""Storage-slot state mapping and advisory availability."""

from datetime import datetime
from uuid import UUID

from app.core.errors import ServiceError
from app.schemas.storage_slots import AvailabilityResponse, StorageSlotImagesResponse, StorageSlotResponse, SizeClass

ACTIVE_SLOT_CODES = {
    "pocket": {f"P-{number:02}" for number in range(1, 9)},
    "medium": {f"M-{number:02}" for number in range(1, 5)},
}


def is_active_slot(row: dict) -> bool:
    return bool(row.get("is_active", True)) and row.get("code") in ACTIVE_SLOT_CODES.get(row.get("size_class"), set())


def timestamp(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def slot_response(row: dict) -> StorageSlotResponse:
    return StorageSlotResponse(
        id=UUID(str(row["id"])), unit_id=UUID(str(row["unit_id"])), code=row["code"], size_class=row["size_class"],
        ordinal=row["ordinal"], status=row["status"], is_active=is_active_slot(row),
        current_found_item_id=UUID(str(row["current_found_item_id"])) if row.get("current_found_item_id") else None,
        item_summary=row.get("item_summary"), reserved_at=timestamp(row.get("reserved_at")),
        occupied_at=timestamp(row.get("occupied_at")), updated_at=timestamp(row["updated_at"]),
    )


def availability(rows: list[dict], size: SizeClass) -> AvailabilityResponse:
    relevant = [row for row in rows if row["size_class"] == size and is_active_slot(row)]
    counts = {status: sum(row["status"] == status for row in relevant)
              for status in ("available", "reserved", "occupied")}
    return AvailabilityResponse(size_class=size, **counts, can_assign=counts["available"] > 0)


async def item_images(repo, item_id: UUID) -> StorageSlotImagesResponse:
    row = await repo.get_item(item_id)
    if not row or not row.get("slot_status"):
        raise ServiceError("ITEM_NOT_FOUND", "No item is assigned to this compartment.", 404)
    return StorageSlotImagesResponse(
        item_id=item_id,
        front_image_url=await repo.signed_url(row.get("front_image_path")),
        back_image_url=await repo.signed_url(row.get("back_image_path")),
    )
