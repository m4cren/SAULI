"""Storage-slot API contracts."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime

from app.schemas.found_items import StrictModel

SizeClass = Literal["pocket", "medium"]
SlotStatus = Literal["available", "reserved", "occupied", "out_of_service"]


class StorageSlotResponse(StrictModel):
    id: UUID
    code: str
    size_class: SizeClass
    ordinal: int
    status: SlotStatus
    current_found_item_id: UUID | None
    item_summary: str | None
    reserved_at: AwareDatetime | None
    occupied_at: AwareDatetime | None
    updated_at: AwareDatetime


class StorageSlotImagesResponse(StrictModel):
    item_id: UUID
    front_image_url: str | None
    back_image_url: str | None


class AvailabilityResponse(StrictModel):
    size_class: SizeClass
    available: int
    reserved: int
    occupied: int
    can_assign: bool
