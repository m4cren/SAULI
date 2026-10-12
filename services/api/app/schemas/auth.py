from pydantic import BaseModel


class UserResponse(BaseModel):
    id: str
    email: str | None = None
    name: str | None = None
    avatar_url: str | None = None
    role: str | None = None
    auth_provider: str | None = None
