"""Authenticated, private FastAPI-to-Pi hardware transport."""

import asyncio
import base64
import binascii
import hashlib
import hmac
import json
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

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
        self._used_grants: dict[str, int] = {}

    @staticmethod
    def _encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    @staticmethod
    def _decode(value: str) -> bytes:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

    def issue_unlock_grant(self, device: dict, authorization: dict, *,
                           workflow_id: str, operation: str) -> str:
        endpoint = self._endpoint(device["id"])
        now = int(time.time())
        action = authorization["action"]
        claims = {
            "v": 1, "jti": str(authorization["command_id"]),
            "device_id": str(device["id"]), "unit_id": str(device["unit_id"]),
            "workflow_id": str(workflow_id), "operation": operation,
            "door": action.removeprefix("pulse_"),
            "slot": authorization["assigned_slot"],
            "expected_slots": authorization["expected_slots"],
            "iat": now, "exp": now + self.settings.hardware_unlock_grant_ttl_seconds,
        }
        payload = self._encode(json.dumps(
            claims, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        signature = self._encode(hmac.new(
            endpoint.token.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest())
        return f"{payload}.{signature}"

    def verify_unlock_grant(self, device: dict, grant: str, *,
                            workflow_id: str, operation: str,
                            consume: bool = False) -> dict:
        if not isinstance(grant, str) or not 80 <= len(grant) <= 8192:
            raise ServiceError("INVALID_UNLOCK_GRANT", "The door authorization is invalid.", 403)
        try:
            payload, supplied = grant.split(".", 1)
            endpoint = self._endpoint(device["id"])
            expected = self._encode(hmac.new(
                endpoint.token.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest())
            if not hmac.compare_digest(supplied, expected):
                raise ValueError("signature")
            claims = json.loads(self._decode(payload))
            UUID(claims["jti"])
            UUID(claims["device_id"])
            UUID(claims["unit_id"])
            UUID(claims["workflow_id"])
        except (ValueError, KeyError, TypeError, json.JSONDecodeError, binascii.Error) as exc:
            raise ServiceError("INVALID_UNLOCK_GRANT", "The door authorization is invalid.", 403) from exc
        now = int(time.time())
        if claims.get("v") != 1 or type(claims.get("iat")) is not int or type(claims.get("exp")) is not int:
            raise ServiceError("INVALID_UNLOCK_GRANT", "The door authorization is invalid.", 403)
        if claims["exp"] <= now or claims["iat"] > now + 5:
            raise ServiceError("UNLOCK_GRANT_EXPIRED", "The door authorization expired. Request a new authorization.", 409)
        if (claims["device_id"] != str(device["id"])
                or claims["unit_id"] != str(device["unit_id"])):
            raise ServiceError("UNLOCK_GRANT_DEVICE_MISMATCH", "The authorization belongs to another kiosk.", 403)
        if claims["workflow_id"] != str(workflow_id) or claims.get("operation") != operation:
            raise ServiceError("UNLOCK_GRANT_WORKFLOW_MISMATCH", "The authorization belongs to another workflow.", 403)
        slot = claims.get("slot")
        door = claims.get("door")
        expected_slots = claims.get("expected_slots")
        if (door not in {"pocket", "medium"} or not isinstance(slot, str)
                or slot.startswith("P-") != (door == "pocket")
                or not isinstance(expected_slots, list) or len(expected_slots) != 12):
            raise ServiceError("INVALID_UNLOCK_GRANT", "The door authorization is invalid.", 403)
        self._used_grants = {key: expiry for key, expiry in self._used_grants.items()
                             if expiry > now}
        if consume:
            if claims["jti"] in self._used_grants:
                raise ServiceError("UNLOCK_GRANT_REPLAYED", "This door authorization was already used.", 409)
            self._used_grants[claims["jti"]] = claims["exp"]
        return claims

    async def command_from_grant(self, device: dict, grant: str, *,
                                 workflow_id: str, operation: str) -> dict:
        claims = self.verify_unlock_grant(
            device, grant, workflow_id=workflow_id, operation=operation, consume=True)
        command = {
            "id": claims["jti"], "device_id": claims["device_id"],
            "action": f"pulse_{claims['door']}",
            "expires_at": datetime.fromtimestamp(claims["exp"], UTC).isoformat(),
            "assigned_slot": claims["slot"],
            "expected_slots": claims["expected_slots"],
            "transport": "direct", "grant": grant,
        }
        return await self.command(device["id"], command)

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
