"""Advisory availability and administrator container status."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.auth.dependencies import get_admin_user
from app.schemas.auth import UserResponse
from app.schemas.storage_slots import AvailabilityResponse, SizeClass, StorageSlotImagesResponse, StorageSlotResponse
from app.services.storage_slots import availability, item_images, slot_response

router = APIRouter(prefix="/api/storage-slots", tags=["storage-slots"])


@router.get("/availability", response_model=AvailabilityResponse)
async def get_availability(request: Request, size_class: SizeClass):
    return availability(await request.app.state.items.list_slots(), size_class)


@router.get("", response_model=list[StorageSlotResponse])
async def list_storage_slots(request: Request, _admin: Annotated[UserResponse, Depends(get_admin_user)]):
    rows = await request.app.state.items.list_slots(include_items=True)
    return [slot_response(row) for row in rows]


@router.get("/items/{item_id}/images", response_model=StorageSlotImagesResponse)
async def get_storage_item_images(request: Request, item_id: UUID, _admin: Annotated[UserResponse, Depends(get_admin_user)]):
    return await item_images(request.app.state.items, item_id)
