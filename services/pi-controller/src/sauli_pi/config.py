"""Per-device configuration. No long-term credential is stored in this file."""

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class Config:
    backend_url: str
    frontend_url: str
    device_code: str
    unit_code: str
    credential_file: Path
    heartbeat_seconds: int = 30
    browser: str = "chromium"

    @classmethod
    def load(cls, path: Path) -> "Config":
        raw = json.loads(path.read_text(encoding="utf-8"))
        config = cls(
            backend_url=raw["backend_url"].rstrip("/"),
            frontend_url=raw["frontend_url"].rstrip("/"),
            device_code=raw["device_code"],
            unit_code=raw["unit_code"],
            credential_file=Path(raw["credential_file"]),
            heartbeat_seconds=int(raw.get("heartbeat_seconds", 30)),
            browser=raw.get("browser", "chromium"),
        )
        for url in (config.backend_url, config.frontend_url):
            parsed = urlparse(url)
            if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
                raise ValueError("Backend and frontend must use HTTPS origins")
        if not 10 <= config.heartbeat_seconds <= 300:
            raise ValueError("heartbeat_seconds must be between 10 and 300")
        if not config.credential_file.is_absolute():
            raise ValueError("credential_file must be an absolute path")
        return config


def save_credential(path: Path, credential: str) -> None:
    """Replace the credential atomically with owner-only permissions."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, pending_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    pending = Path(pending_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="ascii") as stream:
            stream.write(credential)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, path)
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise
    finally:
        if pending.exists():
            pending.unlink()


def read_credential(path: Path) -> str:
    if path.stat().st_mode & 0o077:
        raise PermissionError("Credential file must be mode 0600")
    return path.read_text(encoding="ascii").strip()
