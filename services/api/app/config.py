"""Server-only settings. Never serialize this model into an API response."""

from pathlib import Path
from ipaddress import ip_address, ip_network
import secrets
from typing import Literal
from urllib.parse import urlparse

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DirectHardwareEndpoint(BaseModel):
    """Private Pi endpoint reachable only through the SAULI tailnet."""

    model_config = ConfigDict(extra="forbid")
    url: str
    token: str = Field(min_length=32, repr=False)

    @field_validator("url")
    @classmethod
    def private_tailscale_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Direct hardware URL must be HTTP or HTTPS")
        if (parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in {"", "/"}):
            raise ValueError("Direct hardware URL must be an origin without credentials or path data")
        host = parsed.hostname.lower()
        private_host = host in {"127.0.0.1", "localhost", "::1"} or host.endswith(".ts.net")
        try:
            private_host = private_host or ip_address(host) in ip_network("100.64.0.0/10")
        except ValueError:
            pass
        if not private_host:
            raise ValueError("Direct hardware URL must use loopback or a private Tailscale address")
        return value.rstrip("/")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)
    _ephemeral_retrieval_pepper: str = PrivateAttr(
        default_factory=lambda: secrets.token_urlsafe(48)
    )

    supabase_url: str | None = None
    supabase_publishable_key: str | None = None
    supabase_service_role_key: str | None = None
    sauli_admin_user_id: str | None = None
    supabase_storage_bucket: str = "sauli-item-images"
    supabase_signed_url_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3.5:9b-q8_0"
    ollama_timeout_seconds: float = Field(default=180, gt=0)
    frontend_origin: str = "https://sauli-system.vercel.app"
    max_image_bytes: int = Field(default=10_485_760, ge=1)
    max_image_pixels: int = Field(default=20_000_000, ge=1)
    retrieval_qr_ttl_minutes: int = Field(default=180, ge=1, le=1440)
    retrieval_token_pepper: str | None = Field(default=None, repr=False)
    emailjs_enabled: bool = False
    emailjs_api_url: str = "https://api.emailjs.com/api/v1.0/email/send"
    emailjs_service_id: str | None = None
    emailjs_template_id: str | None = None
    emailjs_public_key: str | None = None
    emailjs_private_key: str | None = Field(default=None, repr=False)
    emailjs_timeout_seconds: float = Field(default=10, gt=0, le=60)
    emailjs_max_retries: int = Field(default=3, ge=1, le=10)
    frontend_base_url: str = "https://sauli-system.vercel.app"
    match_notification_min_score: float = Field(default=65, ge=0, le=100)
    environment: str = "development"
    hardware_test_enabled: bool = False
    hardware_transport: Literal["direct", "legacy"] = "direct"
    hardware_direct_devices: dict[str, DirectHardwareEndpoint] = Field(
        default_factory=dict, repr=False
    )
    hardware_direct_timeout_seconds: float = Field(default=4, gt=0, le=15)
    hardware_unlock_grant_ttl_seconds: int = Field(default=90, ge=15, le=300)
    # Operator switch simulation is explicitly opt-in and requires a secret
    # never shipped to the browser bundle.
    hardware_sensor_simulation_enabled: bool = False
    hardware_sensor_simulation_token: str | None = Field(default=None, repr=False, min_length=32)

    @model_validator(mode="after")
    def require_production_retrieval_pepper(self) -> "Settings":
        if self.environment.lower() in {"production", "staging"} and (
            not self.retrieval_token_pepper
            or len(self.retrieval_token_pepper) < 32
            or self.retrieval_token_pepper.startswith("<")
            or "replace" in self.retrieval_token_pepper.lower()
        ):
            raise ValueError(
                "RETRIEVAL_TOKEN_PEPPER must contain at least 32 characters in production"
            )
        for device_id in self.hardware_direct_devices:
            try:
                from uuid import UUID
                UUID(device_id)
            except ValueError as exc:
                raise ValueError("Hardware direct endpoint keys must be device UUIDs") from exc
        return self

    @field_validator("supabase_url")
    @classmethod
    def require_https_supabase(cls, value: str | None) -> str | None:
        if value and (urlparse(value).scheme != "https" or not urlparse(value).netloc):
            raise ValueError("SUPABASE_URL must be a valid HTTPS URL")
        return value.rstrip("/") if value else None

    @field_validator("ollama_host", "frontend_origin", "frontend_base_url")
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
        origins = [self.frontend_origin]
        if self.environment.lower() == "development":
            origins.extend(("http://localhost:3000", "http://127.0.0.1:3000"))
        return tuple(dict.fromkeys(origins))

    @property
    def ollama_base_url(self) -> str:
        """Compatibility with the existing status route and test doubles."""
        return self.ollama_host

    @field_validator("emailjs_api_url")
    @classmethod
    def valid_emailjs_api_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("EMAILJS_API_URL must be HTTPS")
        return value

    @property
    def emailjs_configured(self) -> bool:
        hostname = (urlparse(self.frontend_base_url).hostname or "").lower()
        if self.environment.lower() in {"production", "staging"} and hostname in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            return False
        return all(
            (self.emailjs_service_id, self.emailjs_template_id, self.emailjs_public_key)
        )
