"""Storage-slot state mapping and advisory availability."""

from datetime import datetime
from uuid import UUID

from app.core.errors import ServiceError
from app.schemas.storage_slots import AvailabilityResponse, StorageSlotImagesResponse, StorageSlotResponse, SizeClass


def timestamp(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def slot_response(row: dict) -> StorageSlotResponse:
    return StorageSlotResponse(
        id=UUID(str(row["id"])), code=row["code"], size_class=row["size_class"],
        ordinal=row["ordinal"], status=row["status"],
        current_found_item_id=UUID(str(row["current_found_item_id"])) if row.get("current_found_item_id") else None,
        item_summary=row.get("item_summary"), reserved_at=timestamp(row.get("reserved_at")),
        occupied_at=timestamp(row.get("occupied_at")), updated_at=timestamp(row["updated_at"]),
    )


def availability(rows: list[dict], size: SizeClass) -> AvailabilityResponse:
    relevant = [row for row in rows if row["size_class"] == size]
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
