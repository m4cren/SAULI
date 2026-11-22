"""Authenticated, private FastAPI-to-Pi hardware transport."""

import asyncio
from typing import Any

import httpx

from app.config import Settings
from app.core.errors import ServiceError


class DirectHardwareGateway:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = httpx.AsyncClient(
            timeout=settings.hardware_direct_timeout_seconds,
            follow_redirects=False,
        )

    def configured(self, device_id: str) -> bool:
        return device_id in self.settings.hardware_direct_devices

    async def close(self) -> None:
        await self._client.aclose()

    def _endpoint(self, device_id: str):
        endpoint = self.settings.hardware_direct_devices.get(device_id)
        if endpoint is None:
            raise ServiceError(
                "HARDWARE_ENDPOINT_NOT_CONFIGURED",
                "This kiosk has no private hardware endpoint configured.",
                503,
            )
        return endpoint

    async def _request(self, device_id: str, method: str, path: str,
                       payload: dict | None = None) -> dict[str, Any]:
        endpoint = self._endpoint(device_id)
        try:
            response = await self._client.request(
                method,
                endpoint.url + path,
                json=payload,
                headers={"Authorization": f"Bearer {endpoint.token}"},
            )
        except httpx.TransportError as exc:
            raise ServiceError(
                "HARDWARE_UNAVAILABLE",
                "The private hardware controller is unavailable.",
                503,
            ) from exc
        try:
            body = response.json()
        except ValueError as exc:
            raise ServiceError(
                "INVALID_HARDWARE_RESPONSE",
                "The private hardware controller returned an invalid response.",
                503,
            ) from exc
        if response.status_code in {401, 403}:
            raise ServiceError(
                "HARDWARE_AUTHENTICATION_FAILED",
                "The private hardware controller rejected API authentication.",
                503,
            )
        if response.status_code >= 400 or not isinstance(body, dict):
            raise ServiceError(
                "HARDWARE_UNAVAILABLE",
                "The private hardware controller rejected the request.",
                503,
            )
        return body

    async def command(self, device_id: str, command: dict) -> dict:
        result = await self._request(device_id, "POST", "/v1/commands", command)
        if result.get("id") != command.get("id"):
            raise ServiceError(
                "INVALID_HARDWARE_RESPONSE",
                "The hardware response did not match the authorized command.",
                503,
            )
        return result

    async def state(self, device_id: str) -> dict:
        return await self._request(device_id, "GET", "/v1/state")

    async def states(self, device_ids: list[str]) -> dict[str, dict]:
        async def fetch(device_id: str):
            try:
                return device_id, await self.state(device_id)
            except ServiceError:
                return device_id, {}

        return dict(await asyncio.gather(*(fetch(value) for value in device_ids)))
