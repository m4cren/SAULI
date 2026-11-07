"""Service-role access to registered units and short-lived kiosk identities."""

import asyncio
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from starlette.concurrency import run_in_threadpool

from app.core.errors import ServiceError


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def secret() -> str:
    return secrets.token_urlsafe(48)


def valid_secret(value: str | None) -> bool:
    return bool(value and 50 <= len(value) <= 128 and value.isascii()
                and all(char.isalnum() or char in "-_" for char in value))


class SupabaseKioskRepository:
    def __init__(self, items):
        self.items = items

    def client(self):
        return self.items.require()

    async def rpc(self, name: str, params: dict):
        return await run_in_threadpool(
            lambda: self.client().rpc(name, params).execute().data
        )

    async def check_rate_limit(self, action: str, subject: str, maximum: int) -> None:
        allowed = await self.rpc("sauli_check_kiosk_rate_limit", {
            "p_action": action, "p_subject_hash": digest(subject),
            "p_max_attempts": maximum, "p_window_seconds": 300,
        })
        if not allowed:
            raise ServiceError("KIOSK_RATE_LIMITED", "Too many attempts. Try again later.", 429)

    async def locations(self) -> list[dict]:
        return await run_in_threadpool(lambda: self.client().table("sauli_units")
            .select("id,unit_code,display_name,campus_code,campus_name,building_name,floor,location_description")
            .eq("status", "active").order("unit_code").execute().data or [])

    async def units(self) -> list[dict]:
        return await run_in_threadpool(lambda: self.client().table("sauli_units")
            .select("*").order("unit_code").execute().data or [])

    async def devices(self) -> list[dict]:
        return await run_in_threadpool(lambda: self.client().table("kiosk_devices")
            .select("id,unit_id,device_code,hostname,hardware_type,status,is_primary,last_seen_at,controller_version,firmware_version,created_at,revoked_at")
            .order("created_at").execute().data or [])

    async def register_unit(self, data: dict) -> dict:
        return await self.rpc("sauli_register_unit", {"p_unit": data})

    async def edit_unit(self, unit_id: UUID, data: dict) -> dict | None:
        rows = await run_in_threadpool(lambda: self.client().table("sauli_units")
            .update(data).eq("id", str(unit_id)).select("*").execute().data or [])
        return rows[0] if rows else None

    async def set_unit_status(self, unit_id: UUID, status: str) -> dict | None:
        rows = await run_in_threadpool(lambda: self.client().table("sauli_units")
            .update({"status": status}).eq("id", str(unit_id)).select("*").execute().data or [])
        return rows[0] if rows else None

    async def register_device(self, unit_id: UUID, device_code: str,
                              hostname: str | None, hardware_type: str) -> dict:
        row = await self.rpc("sauli_register_kiosk_device", {
            "p_unit_id": str(unit_id), "p_device_code": device_code,
            "p_hostname": hostname, "p_hardware_type": hardware_type,
        })
        if not isinstance(row, dict) or row.get("error"):
            raise ServiceError("DEVICE_REGISTRATION_DENIED",
                               "The device cannot be registered for this unit.", 409)
        return row

    async def approve_pairing(self, device_id: UUID, admin_id: UUID) -> dict:
        code = secret()
        expires = datetime.now(UTC) + timedelta(minutes=10)
        row = await self.rpc("sauli_approve_kiosk_pairing", {
            "p_device_id": str(device_id), "p_request_hash": digest(code),
            "p_actor": str(admin_id), "p_expires_at": expires.isoformat(),
        })
        if not isinstance(row, dict) or row.get("error"):
            raise ServiceError("PAIRING_DENIED", "This device is not ready for enrollment.", 409)
        return {"pairing_code": code, "expires_at": expires.isoformat(),
                "request_id": row["request_id"]}

    async def enroll(self, device_code: str, pairing_code: str) -> dict:
        if not valid_secret(pairing_code):
            raise ServiceError("PAIRING_DENIED", "Enrollment was denied.", 403)
        credential = secret()
        row = await self.rpc("sauli_redeem_pairing", {
            "p_device_code": device_code, "p_request_hash": digest(pairing_code),
            "p_secret_hash": digest(credential)})
        if not isinstance(row, dict) or row.get("error"):
            raise ServiceError("PAIRING_DENIED", "Enrollment was denied.", 403)
        return {"device_credential": credential, **row}

    async def device_from_credential(self, credential: str | None) -> dict | None:
        if not valid_secret(credential):
            return None
        def fetch():
            rows = self.client().table("kiosk_device_credentials")
            rows = (rows.select("device_id,expires_at").eq("secret_hash", digest(credential))
                .is_("revoked_at", "null").limit(1).execute().data or [])
            if not rows:
                return None
            expires = rows[0]["expires_at"]
            if expires and datetime.fromisoformat(expires.replace("Z", "+00:00")) <= datetime.now(UTC):
                return None
            return self._active_device(rows[0]["device_id"])
        return await run_in_threadpool(fetch)

    def _active_device(self, device_id: str) -> dict | None:
        rows = (self.client().table("kiosk_devices").select("id,unit_id,device_code,status,revoked_at")
            .eq("id", device_id).limit(1).execute().data or [])
        if not rows or rows[0]["status"] != "active" or rows[0]["revoked_at"]:
            return None
        units = (self.client().table("sauli_units")
            .select("unit_code,status,display_name,campus_name,building_name,location_description")
            .eq("id", rows[0]["unit_id"]).limit(1).execute().data or [])
        if not units or units[0]["status"] != "active":
            return None
        return {**rows[0], "unit": units[0]}

    async def bootstrap(self, device_id: str) -> dict:
        code = secret()
        expires = datetime.now(UTC) + timedelta(seconds=60)
        await run_in_threadpool(lambda: self.client().table("kiosk_browser_bootstraps")
            .insert({"device_id": device_id, "code_hash": digest(code),
                     "expires_at": expires.isoformat()}).execute())
        return {"bootstrap_code": code, "expires_at": expires.isoformat()}

    async def redeem_bootstrap(self, code: str) -> dict:
        if not valid_secret(code):
            raise ServiceError("BOOTSTRAP_DENIED", "Kiosk authorization failed.", 403)
        token = secret()
        expires = datetime.now(UTC) + timedelta(hours=8)
        row = await self.rpc("sauli_redeem_browser_bootstrap", {
            "p_code_hash": digest(code), "p_session_hash": digest(token),
            "p_expires_at": expires.isoformat()})
        if not isinstance(row, dict) or row.get("error"):
            raise ServiceError("BOOTSTRAP_DENIED", "Kiosk authorization failed.", 403)
        return {"session_token": token, "expires_at": expires.isoformat(), **row}

    async def browser_session(self, token: str | None) -> dict | None:
        if not valid_secret(token):
            return None
        def fetch():
            rows = (self.client().table("kiosk_browser_sessions")
                .select("device_id,expires_at").eq("token_hash", digest(token))
                .is_("revoked_at", "null").limit(1).execute().data or [])
            if not rows or datetime.fromisoformat(rows[0]["expires_at"].replace("Z", "+00:00")) <= datetime.now(UTC):
                return None
            return self._active_device(rows[0]["device_id"])
        return await run_in_threadpool(fetch)

    async def rotate(self, device: dict, credential: str) -> dict:
        replacement = secret()
        ok = await self.rpc("sauli_rotate_device_credential", {
            "p_device_id": device["id"], "p_old_hash": digest(credential),
            "p_new_hash": digest(replacement)})
        if not ok:
            raise ServiceError("DEVICE_REVOKED", "Device access has ended.", 403)
        return {"device_credential": replacement}

    async def revoke(self, device_id: UUID, admin_id: UUID) -> bool:
        return bool(await self.rpc("sauli_revoke_device", {
            "p_device_id": str(device_id), "p_actor": str(admin_id)}))

    async def heartbeat(self, device: dict, version: str | None) -> None:
        await run_in_threadpool(lambda: self.client().table("kiosk_devices")
            .update({"last_seen_at": datetime.now(UTC).isoformat(),
                     "controller_version": version}).eq("id", device["id"]).execute())

    async def hardware_heartbeat(self, device: dict, snapshot: dict) -> None:
        now = datetime.now(UTC).isoformat()
        await run_in_threadpool(lambda: self.client().table("sauli_hardware_snapshots")
            .upsert({"device_id": device["id"], "unit_id": device["unit_id"],
                     "snapshot": snapshot, "received_at": now}, on_conflict="device_id").execute())

    async def claim_hardware_commands(self, device: dict) -> list[dict]:
        rows = await self.rpc("sauli_claim_hardware_commands", {
            "p_device_id": device["id"], "p_unit_id": device["unit_id"]})
        return [{"id": row["id"], "device_id": row["device_id"],
                 "action": row["action"], "expires_at": row["expires_at"]}
                for row in (rows or [])]

    async def ack_hardware_command(self, device: dict, command_id: str,
                                   status: str, code: str) -> bool:
        rows = await run_in_threadpool(lambda: self.client().table("sauli_hardware_commands")
            .update({"status": status, "result_code": code,
                     "acknowledged_at": datetime.now(UTC).isoformat()})
            .eq("id", command_id).eq("device_id", device["id"])
            .eq("unit_id", device["unit_id"]).eq("status", "claimed")
            .select("id").execute().data or [])
        return bool(rows)

    async def enqueue_hardware_test(self, device_id: str, action: str) -> dict:
        device = await run_in_threadpool(lambda: self._active_device(device_id))
        if device is None:
            raise ServiceError("DEVICE_ACCESS_DENIED", "Device is not active.", 403)
        expires = datetime.now(UTC) + timedelta(seconds=10)
        rows = await run_in_threadpool(lambda: self.client().table("sauli_hardware_commands")
            .insert({"device_id": device["id"], "unit_id": device["unit_id"],
                     "action": action, "expires_at": expires.isoformat()})
            .select("id,status,expires_at").execute().data or [])
        return rows[0]

    async def public_hardware_status(self) -> dict:
        rows, units, devices = await asyncio.gather(
            run_in_threadpool(lambda: self.client().table("sauli_hardware_snapshots")
                .select("device_id,unit_id,snapshot,received_at").order("received_at", desc=True)
                .limit(50).execute().data or []),
            self.locations(), self.devices())
        labels = {unit["id"]: unit["display_name"] for unit in units}
        active_devices = {device["id"] for device in devices
                          if device["status"] == "active" and not device["revoked_at"]}
        now = datetime.now(UTC)
        result = []
        for row in rows:
            if row["unit_id"] not in labels or row["device_id"] not in active_devices:
                continue
            snapshot = row.get("snapshot") or {}
            received = datetime.fromisoformat(row["received_at"].replace("Z", "+00:00"))
            age = (now - received).total_seconds()
            pi = snapshot.get("pi") or {}
            esp = snapshot.get("esp") or {}
            telemetry = esp.get("telemetry") or {}
            result.append({
                "unit_name": labels[row["unit_id"]],
                "received_at": row["received_at"],
                "sequence": snapshot.get("sequence"),
                "observed_at": snapshot.get("observed_at"),
                "connection": "online" if age <= 10 else "stale" if age <= 30 else "offline",
                "doors": pi.get("doors", {}), "outputs": pi.get("outputs", {}),
                "lock_feedback": "unavailable",
                "door_workflow": snapshot.get("door_workflow", {}),
                "esp": {"connection": esp.get("connection", "offline"),
                        "frame_errors": esp.get("frame_errors", 0),
                        "error": esp.get("error"), "slots": telemetry.get("slots", [])},
                "events": snapshot.get("events", [])[:10],
            })
        return {"units": result}
