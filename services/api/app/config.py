import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator


class Settings(BaseModel):
    supabase_url: str | None = None
    supabase_publishable_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    ollama_timeout_seconds: float = Field(default=5.0, gt=0)
    cors_origins: tuple[str, ...] = ("http://localhost:3000",)

    @field_validator("supabase_url")
    @classmethod
    def require_https_supabase(cls, value: str | None) -> str | None:
        if value and (urlparse(value).scheme != "https" or not urlparse(value).netloc):
            raise ValueError("SUPABASE_URL must be a valid HTTPS URL")
        return value.rstrip("/") if value else None

    @field_validator("ollama_base_url")
    @classmethod
    def valid_ollama_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("OLLAMA_BASE_URL must be an HTTP or HTTPS URL")
        return value.rstrip("/")

    @field_validator("cors_origins")
    @classmethod
    def explicit_origins(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or any(origin == "*" for origin in value):
            raise ValueError("CORS_ORIGINS must list explicit origins")
        return value

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
        origins = os.getenv("CORS_ORIGINS", "http://localhost:3000")
        return cls(
            supabase_url=os.getenv("SUPABASE_URL") or None,
            supabase_publishable_key=os.getenv("SUPABASE_PUBLISHABLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or None,
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            ollama_timeout_seconds=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "5")),
            cors_origins=tuple(origin.strip() for origin in origins.split(",") if origin.strip()),
        )
