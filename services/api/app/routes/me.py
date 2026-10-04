from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user
from app.schemas.auth import UserResponse

router = APIRouter(prefix="/api/v1")


@router.get("/me", response_model=UserResponse)
async def me(user: Annotated[UserResponse, Depends(get_current_user)]) -> UserResponse:
    return user
