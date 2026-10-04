from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials

from app.integrations.supabase import bearer_scheme, verify_supabase_user
from app.schemas.auth import UserResponse


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> UserResponse:
    return await verify_supabase_user(request, credentials)
