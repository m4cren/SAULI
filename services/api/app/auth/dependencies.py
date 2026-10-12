from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials

from app.integrations.supabase import bearer_scheme, verify_supabase_user
from app.schemas.auth import UserResponse


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> UserResponse:
    return await verify_supabase_user(request, credentials)


async def get_claimant_user(user: Annotated[UserResponse, Depends(get_current_user)]) -> UserResponse:
    if user.role == "admin" or user.auth_provider != "facebook":
        raise HTTPException(403, "Facebook sign-in is required for claimant access.")
    return user


async def get_admin_user(request: Request, user: Annotated[UserResponse, Depends(get_current_user)]) -> UserResponse:
    admin_id = request.app.state.settings.sauli_admin_user_id
    if not admin_id or user.id != admin_id or user.role != "admin":
        raise HTTPException(403, "This account does not have administrator access.")
    return user
