import httpx
from fastapi import HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.schemas.auth import UserResponse

bearer_scheme = HTTPBearer(auto_error=False)


async def verify_supabase_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
) -> UserResponse:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")

    settings = request.app.state.settings
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Authentication service is not configured")

    try:
        response = await request.app.state.auth_http.get(
            f"{settings.supabase_url}/auth/v1/user",
            headers={
                "apikey": settings.supabase_publishable_key,
                "Authorization": f"Bearer {credentials.credentials}",
            },
        )
    except (httpx.RequestError, TimeoutError) as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Authentication service unavailable") from exc

    if response.status_code in (400, 401, 403):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if response.status_code != 200:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Authentication service unavailable")

    try:
        payload = response.json()
        user_id = payload["id"]
        if not isinstance(user_id, str) or not user_id:
            raise ValueError("Missing user id")
        metadata = payload.get("user_metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        name = metadata.get("full_name") or metadata.get("name")
        avatar = metadata.get("avatar_url") or metadata.get("picture")
        return UserResponse(
            id=user_id,
            email=payload.get("email") or None,
            name=name if isinstance(name, str) else None,
            avatar_url=avatar if isinstance(avatar, str) else None,
        )
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Authentication service unavailable") from exc
