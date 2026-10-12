"""Stable browser-safe service errors."""

from dataclasses import dataclass


@dataclass
class ServiceError(Exception):
    code: str
    message: str
    status_code: int = 400
    details: dict | None = None

    def __str__(self) -> str:
        return self.code


def unavailable(code: str, message: str) -> ServiceError:
    return ServiceError(code, message, 503)
