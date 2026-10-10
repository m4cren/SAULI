"""Server-only settings. Never serialize this model into an API response."""

from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    supabase_url: str | None = None
    supabase_publishable_key: str | None = None
    supabase_service_role_key: str | None = None
    supabase_storage_bucket: str = "sauli-item-images"
    supabase_signed_url_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3.5:9b-q8_0"
    ollama_timeout_seconds: float = Field(default=180, gt=0)
    frontend_origin: str = "http://localhost:3000"
    max_image_bytes: int = Field(default=10_485_760, ge=1)
    max_image_pixels: int = Field(default=20_000_000, ge=1)

    @field_validator("supabase_url")
    @classmethod
    def require_https_supabase(cls, value: str | None) -> str | None:
        if value and (urlparse(value).scheme != "https" or not urlparse(value).netloc):
            raise ValueError("SUPABASE_URL must be a valid HTTPS URL")
        return value.rstrip("/") if value else None

    @field_validator("ollama_host", "frontend_origin")
    @classmethod
    def valid_http_url(cls, value: str) -> str:
        if "://" not in value:
            value = "http://" + value
        if value.startswith("http://0.0.0.0:"):
            value = value.replace("http://0.0.0.0:", "http://127.0.0.1:", 1)
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Expected an HTTP or HTTPS URL")
        return value.rstrip("/")

    @field_validator("ollama_timeout_seconds")
    @classmethod
    def allow_vision_analysis_time(cls, value: float) -> float:
        # Older local .env files used a 5-second status-check timeout. A two-image
        # model request needs substantially longer even when Ollama is healthy.
        return max(value, 180.0)

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
        return cls()

    @property
    def cors_origins(self) -> tuple[str, ...]:
        return (self.frontend_origin,)

    @property
    def ollama_base_url(self) -> str:
        """Compatibility with the existing status route and test doubles."""
        return self.ollama_host
