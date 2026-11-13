"""Service-role access to registered units and short-lived kiosk identities."""

import asyncio
import hashlib
import logging
import secrets
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
from postgrest.exceptions import APIError
from starlette.concurrency import run_in_threadpool

from app.core.errors import ServiceError

log = logging.getLogger("sauli.kiosks")


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

    async def _read_identity(self, fetch):
        def retry():
            # Identity queries are reads; retry a dropped connection before
            # reporting that Supabase is temporarily unavailable.
            for attempt in range(3):
                try:
                    return fetch()
                except (httpx.TransportError, APIError) as exc:
                    if attempt == 2:
                        log.warning("Kiosk identity lookup failed after retries (%s)", type(exc).__name__)
                        raise ServiceError("SUPABASE_UNAVAILABLE",
                                           "Kiosk service is temporarily unavailable. Please try again.", 503) from exc
                    time.sleep(0.2 * (attempt + 1))
        return await run_in_threadpool(retry)

    async def rpc(self, name: str, params: dict):
        try:
            return await run_in_threadpool(
                lambda: self.client().rpc(name, params).execute().data
            )
        except (httpx.TransportError, APIError) as exc:
            log.warning("Kiosk database RPC unavailable: %s (%s)", name, type(exc).__name__)
            raise ServiceError("SUPABASE_UNAVAILABLE",
                               "Kiosk service is temporarily unavailable. Please try again.", 503) from exc

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
        return await self._read_identity(fetch)

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
        try:
            await run_in_threadpool(lambda: self.client().table("kiosk_browser_bootstraps")
                .insert({"device_id": device_id, "code_hash": digest(code),
                         "expires_at": expires.isoformat()}).execute())
        except (httpx.TransportError, APIError) as exc:
            log.warning("Kiosk bootstrap write unavailable (%s)", type(exc).__name__)
            raise ServiceError("SUPABASE_UNAVAILABLE",
                               "Kiosk service is temporarily unavailable. Please try again.", 503) from exc
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
        return await self._read_identity(fetch)

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
        try:
            await run_in_threadpool(lambda: self.client().table("kiosk_devices")
                .update({"last_seen_at": datetime.now(UTC).isoformat(),
                         "controller_version": version}).eq("id", device["id"]).execute())
        except (httpx.TransportError, APIError) as exc:
            log.warning("Kiosk heartbeat write unavailable (%s)", type(exc).__name__)
            raise ServiceError("SUPABASE_UNAVAILABLE",
                               "Kiosk service is temporarily unavailable. Please try again.", 503) from exc

    async def hardware_heartbeat(self, device: dict, snapshot: dict) -> None:
        result = await self.rpc("sauli_reconcile_hardware_workflow", {
            "p_device_id": device["id"], "p_snapshot": snapshot,
        })
        if result.get("error"):
            raise ServiceError("HARDWARE_RECONCILIATION_FAILED", "Hardware state could not be reconciled.", 503)

    async def apply_hardware_presence(self, device: dict, event: dict) -> dict:
        return await self.rpc("sauli_apply_hardware_presence", {
            "p_device_id": device["id"], "p_event_id": event["event_id"],
            "p_boot_id": event["boot_id"], "p_sequence": event["seq"],
            "p_slot_code": event["slot"], "p_kind": event["kind"],
            "p_present": event["present"],
        })

    async def hardware_guidance(self, device: dict) -> dict:
        return await self.rpc("sauli_hardware_guidance", {"p_unit_id": device["unit_id"]})

    async def rearm_unopened_hardware_review(
        self, unit_id: UUID, actor_id: UUID, reason: str,
    ) -> dict:
        result = await self.rpc("sauli_rearm_unopened_hardware_review", {
            "p_unit_id": str(unit_id), "p_actor_id": str(actor_id),
            "p_reason": reason.strip(),
        })
        if not isinstance(result, dict) or result.get("error"):
            raise ServiceError("REVIEW_REARM_DENIED",
                               "Review could not be cleared. Check current hardware state.", 409)
        return result

    async def enqueue_workflow_unlock(self, device: dict, *,
                                      item_id: str | None = None,
                                      session_id: str | None = None) -> dict:
        result = await self.rpc("sauli_queue_workflow_unlock", {
            "p_device_id": device["id"], "p_item_id": item_id,
            "p_session_id": session_id,
        })
        if not isinstance(result, dict) or result.get("error"):
            code = result.get("error", "HARDWARE_UNAVAILABLE") if isinstance(result, dict) else "HARDWARE_UNAVAILABLE"
            raise ServiceError(code, "The door could not be requested. Check the hardware and try again.", 503)
        if result.get("status") == "failed":
            raise ServiceError("UNLOCK_FAILED", "The unlock signal failed. Ask an operator to check the door.", 503)
        return result

    async def hardware_workflow(self, device: dict, *, item_id: str | None,
                                session_id: str | None) -> dict:
        def fetch():
            client = self.client()
            item = None
            session = None
            if item_id:
                rows = (client.table("found_items").select("id,unit_id,placement_status")
                    .eq("id", item_id).eq("unit_id", device["unit_id"]).limit(1).execute().data or [])
                item = rows[0] if rows else None
            if session_id:
                rows = (client.table("retrieval_sessions").select("id,found_item_id,status")
                    .eq("id", session_id).limit(1).execute().data or [])
                if rows:
                    owned = (client.table("found_items").select("id").eq("id", rows[0]["found_item_id"])
                        .eq("unit_id", device["unit_id"]).limit(1).execute().data or [])
                    session = rows[0] if owned else None
            if (item_id and item is None) or (session_id and session is None):
                raise ServiceError("HARDWARE_WORKFLOW_NOT_FOUND", "Workflow not found for this kiosk.", 404)
            incidents = (client.table("sauli_hardware_incidents").select("slot_id,kind")
                .eq("unit_id", device["unit_id"]).eq("active", True)
                .execute().data or []) if (item_id or session_id) else []
            codes = {}
            if incidents:
                slots = (client.table("storage_slots").select("id,code")
                    .eq("unit_id", device["unit_id"]).execute().data or [])
                codes = {row["id"]: row["code"] for row in slots}
            snapshots = (client.table("sauli_hardware_snapshots").select("received_at,snapshot")
                .eq("unit_id", device["unit_id"]).order("received_at", desc=True)
                .limit(1).execute().data or [])
            transaction_rows = (client.table("sauli_hardware_transactions")
                .select("phase,last_door,found_item_id,retrieval_session_id,command_id")
                .eq("unit_id", device["unit_id"]).limit(1).execute().data or [])
            transaction = next((row for row in transaction_rows
                if (item_id and row["found_item_id"] == item_id) or
                   (session_id and row["retrieval_session_id"] == session_id)), None)
            unlock_retry_available = False
            if transaction and transaction["phase"] == "awaiting_door_open" and transaction.get("command_id"):
                commands = (client.table("sauli_hardware_commands")
                    .select("status,expires_at").eq("id", transaction["command_id"])
                    .eq("unit_id", device["unit_id"]).limit(1).execute().data or [])
                if commands and commands[0]["status"] == "pending":
                    expires_at = datetime.fromisoformat(commands[0]["expires_at"].replace("Z", "+00:00"))
                    unlock_retry_available = expires_at <= datetime.now(UTC)
            online = False
            last_unlock = None
            observed_door = "unknown"
            if snapshots:
                age = (datetime.now(UTC) - datetime.fromisoformat(
                    snapshots[0]["received_at"].replace("Z", "+00:00"))).total_seconds()
                snapshot = snapshots[0]["snapshot"] or {}
                online = age <= 5 and ((snapshot.get("esp") or {}).get("connection") == "online")
                if transaction:
                    reported = snapshot.get("last_unlock") or {}
                    if reported.get("command_id") == transaction.get("command_id"):
                        last_unlock = {"status": reported.get("status"),
                                       "activated_at": reported.get("activated_at"),
                                       "deactivated_at": reported.get("deactivated_at")}
                    if age <= 5 and transaction.get("last_door") in ("open", "closed"):
                        observed_door = transaction["last_door"]
            return {"placement_status": item["placement_status"] if item else None,
                    "retrieval_status": session["status"] if session else None,
                    "wrong_slots": [codes.get(row["slot_id"], "unknown") for row in incidents],
                    "hardware_online": online,
                    "phase": transaction["phase"] if transaction else "awaiting_door_open",
                    "door": observed_door,
                    "last_unlock": last_unlock,
                    "unlock_retry_available": unlock_retry_available}
        return await run_in_threadpool(fetch)

    async def claim_hardware_commands(self, device: dict) -> list[dict]:
        rows = await self.rpc("sauli_claim_hardware_commands", {
            "p_device_id": device["id"], "p_unit_id": device["unit_id"]})
        return [{"id": row["id"], "device_id": row["device_id"],
                 "action": row["action"], "expires_at": row["expires_at"],
                 "created_at": row["created_at"]}
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

    async def enqueue_capture_light(self, device: dict, enabled: bool) -> dict:
        expires = datetime.now(UTC) + timedelta(seconds=10)
        rows = await run_in_threadpool(lambda: self.client().table("sauli_hardware_commands")
            .insert({"device_id": device["id"], "unit_id": device["unit_id"],
                     "action": "capture_light_on" if enabled else "capture_light_off",
                     "expires_at": expires.isoformat()})
            .select("id,status").execute().data or [])
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
                "last_unlock": snapshot.get("last_unlock"),
                "esp": {"connection": esp.get("connection", "offline"),
                        "frame_errors": esp.get("frame_errors", 0),
                        "error": esp.get("error"), "slots": telemetry.get("slots", [])},
                "events": snapshot.get("events", [])[:10],
            })
        return {"units": result}
