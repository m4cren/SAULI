"""Server-only Supabase data and private Storage access."""

import logging
import time
from datetime import UTC, datetime
from uuid import UUID

import httpx
from starlette.concurrency import run_in_threadpool
from supabase import Client, create_client

from app.config import Settings
from app.core.errors import ServiceError

log = logging.getLogger("sauli.supabase")
SEARCH_ITEM_COLUMNS = (
    "id,status,placement_status,created_at,found_at,generic_name,object_name,alternative_names,category,subcategory,"
    "colors,materials,brand,model_or_variant,visible_markings,functional_components,condition,"
    "condition_details,patterns,distinctive_features,short_description,extraction_summary,"
    "found_location,document_kind,front_image_path"
)


class SupabaseFoundItemRepository:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client: Client | None = None
        if settings.supabase_url and settings.supabase_service_role_key:
            self.client = create_client(settings.supabase_url, settings.supabase_service_role_key)

    def require(self) -> Client:
        if self.client is None:
            raise ServiceError("SUPABASE_UNAVAILABLE", "Item storage is not configured. Please try again later.", 503)
        return self.client

    async def database_health(self) -> bool:
        try:
            client = self.require()
            await run_in_threadpool(lambda: client.table("found_items").select("id").limit(1).execute())
            return True
        except Exception:
            log.warning("Supabase database health failed", exc_info=True)
            return False

    async def storage_health(self) -> bool:
        try:
            client = self.require()
            bucket = await run_in_threadpool(lambda: client.storage.get_bucket(self.settings.supabase_storage_bucket))
            return bucket is not None
        except Exception:
            log.warning("Supabase Storage health failed", exc_info=True)
            return False

    async def find_by_key(self, key: UUID) -> dict | None:
        try:
            client = self.require()
            response = await run_in_threadpool(lambda: client.table("found_items").select("id,status,storage_size,placement_status,extraction_summary,found_location,found_at").eq("idempotency_key", str(key)).maybe_single().execute())
            return response.data if response is not None else None
        except ServiceError:
            raise
        except Exception as exc:
            log.exception("Found item idempotency lookup failed")
            raise ServiceError("SUPABASE_UNAVAILABLE", "Item storage is unavailable. Please try again.", 503) from exc

    async def insert_item(self, row: dict) -> dict:
        try:
            client = self.require()
            response = await run_in_threadpool(lambda: client.table("found_items").insert(row).execute())
            if not response.data:
                raise RuntimeError("No inserted row")
            return response.data[0]
        except Exception as exc:
            log.exception("Found item database insert failed")
            raise ServiceError("DATABASE_INSERT_FAILED", "The item could not be saved. Please try again.", 503) from exc

    async def reserve_item(self, row: dict, size: str) -> dict:
        try:
            client = self.require()
            result = await run_in_threadpool(lambda: client.rpc("reserve_sauli_storage_slot", {"p_item": row, "p_size": size}).execute())
            return result.data
        except Exception as exc:
            if "NO_AVAILABLE_STORAGE_SLOT" in str(exc):
                raise ServiceError("NO_AVAILABLE_STORAGE_SLOT", f"The {size}-size section is full.", 409,
                                   {"requested_size": size}) from exc
            if "INVALID_STORAGE_SIZE" in str(exc):
                raise ServiceError("INVALID_STORAGE_SIZE", "Choose a supported storage size.", 422) from exc
            log.exception("Atomic storage assignment failed")
            raise ServiceError("DATABASE_INSERT_FAILED", "The item could not be assigned. Please try again.", 503) from exc

    async def simulate_placement(self, item_id: UUID, slot_code: str) -> dict:
        try:
            client = self.require()
            result = await run_in_threadpool(lambda: client.rpc("simulate_sauli_placement", {
                "p_item_id": str(item_id), "p_slot_code": slot_code}).execute())
            return result.data
        except Exception as exc:
            if "SLOT_RESERVATION_MISMATCH" in str(exc):
                raise ServiceError("SLOT_RESERVATION_MISMATCH", "This position is no longer reserved for the item.", 409) from exc
            log.exception("Placement simulation failed")
            raise ServiceError("SUPABASE_UNAVAILABLE", "Placement could not be recorded. Please try again.", 503) from exc

    async def get_slot_for_item(self, item_id: UUID) -> dict | None:
        client = self.require()
        try:
            result = await run_in_threadpool(lambda: client.table("storage_slots").select("*").eq("current_found_item_id", str(item_id)).maybe_single().execute())
            return result.data if result else None
        except Exception as exc:
            log.exception("Item slot lookup failed")
            raise ServiceError("SUPABASE_UNAVAILABLE", "Storage position is unavailable. Please try again.", 503) from exc

    async def list_slots(self, include_items: bool = False) -> list[dict]:
        client = self.require()
        try:
            def fetch():
                # PostgREST retries some HTTP status codes, but a dropped
                # connection raises before it receives any response. These
                # two queries are reads, so a brief transport retry is safe.
                for attempt in range(3):
                    try:
                        result = client.table("storage_slots").select("*").execute()
                        rows = result.data or []
                        rows.sort(key=lambda row: (0 if row["size_class"] == "pocket" else 1, row["ordinal"]))
                        if include_items:
                            ids = [row["current_found_item_id"] for row in rows if row.get("current_found_item_id")]
                            summaries = {}
                            if ids:
                                items = client.table("found_items").select("id,object_name").in_("id", ids).execute().data or []
                                summaries = {item["id"]: item["object_name"] for item in items}
                            for row in rows:
                                row["item_summary"] = summaries.get(row.get("current_found_item_id"))
                        return rows
                    except httpx.TransportError:
                        if attempt == 2:
                            raise
                        time.sleep(0.2 * (attempt + 1))
            return await run_in_threadpool(fetch)
        except Exception as exc:
            log.exception("Storage slot listing failed")
            raise ServiceError("SUPABASE_UNAVAILABLE", "Container status is unavailable. Please try again.", 503) from exc

    async def occupied_item_ids(self) -> set[str]:
        rows = await self.list_slots()
        return {str(row["current_found_item_id"]) for row in rows
                if row["status"] == "occupied" and row.get("current_found_item_id")}

    async def decide_match(self, candidate_id: UUID, user_id: UUID, decision: str) -> dict:
        try:
            client = self.require()
            result = await run_in_threadpool(lambda: client.rpc("decide_sauli_match", {
                "p_candidate_id": str(candidate_id), "p_user_id": str(user_id), "p_decision": decision}).execute())
            return result.data
        except Exception as exc:
            message = str(exc)
            if "MATCH_NOT_FOUND" in message:
                raise ServiceError("MATCH_NOT_FOUND", "This match does not belong to your search.", 404) from exc
            if "MATCH_NO_LONGER_AVAILABLE" in message or "MATCH_DECISION_CONFLICT" in message:
                raise ServiceError("MATCH_NO_LONGER_AVAILABLE", "This item is no longer available to confirm.", 409) from exc
            log.exception("Match decision failed")
            raise ServiceError("SUPABASE_UNAVAILABLE", "The item could not be confirmed. Please try again.", 503) from exc

    async def upload(self, path: str, data: bytes, mime: str) -> None:
        try:
            client = self.require()
            await run_in_threadpool(lambda: client.storage.from_(self.settings.supabase_storage_bucket).upload(path, data, {"content-type": mime, "upsert": "false"}))
        except Exception as exc:
            log.exception("Private image upload failed")
            raise ServiceError("STORAGE_UPLOAD_FAILED", "The item images could not be saved. Please try again.", 503) from exc

    async def remove(self, paths: list[str]) -> None:
        if not paths:
            return
        try:
            client = self.require()
            await run_in_threadpool(lambda: client.storage.from_(self.settings.supabase_storage_bucket).remove(paths))
        except Exception:
            log.exception("Storage cleanup failed for %s object(s)", len(paths))

    async def signed_url(self, path: str | None) -> str | None:
        if not path:
            return None
        try:
            client = self.require()
            result = await run_in_threadpool(lambda: client.storage.from_(self.settings.supabase_storage_bucket).create_signed_url(path, self.settings.supabase_signed_url_ttl_seconds))
            return result.get("signedURL") or result.get("signedUrl") or result.get("signed_url")
        except Exception:
            log.warning("Signed image URL unavailable", exc_info=True)
            return None

    async def get_item(self, item_id: UUID) -> dict | None:
        try:
            client = self.require()
            result = await run_in_threadpool(lambda: client.table("found_items").select("id,status,placement_status,generic_name,object_name,extraction_summary,category,colors,visible_markings,condition,found_location,found_at,created_at,front_image_path,back_image_path,document_kind").eq("id", str(item_id)).maybe_single().execute())
            if result is None or not result.data:
                return None
            slot = await self.get_slot_for_item(item_id)
            return {**result.data, "slot_status": slot.get("status") if slot else None}
        except Exception as exc:
            log.exception("Found item lookup failed")
            raise ServiceError("SUPABASE_UNAVAILABLE", "Item details are unavailable. Please try again.", 503) from exc

    async def eligible_items(self, last_seen_at: str | None, limit: int = 50) -> list[dict]:
        try:
            client = self.require()
            def fetch():
                slots = client.table("storage_slots").select("current_found_item_id").eq("status", "occupied").execute().data or []
                ids = [slot["current_found_item_id"] for slot in slots if slot.get("current_found_item_id")]
                if not ids:
                    return []
                query = client.table("found_items").select(SEARCH_ITEM_COLUMNS).eq("status", "available")
                query = query.eq("placement_status", "placed").in_("id", ids)
                if last_seen_at:
                    query = query.gte("created_at", last_seen_at)
                rows = query.order("created_at", desc=True).limit(min(max(limit, 1), 100)).execute().data or []
                return [{**row, "slot_status": "occupied"} for row in rows]

            result = await run_in_threadpool(fetch)
            return result
        except Exception as exc:
            log.exception("Eligible item query failed")
            raise ServiceError("SUPABASE_UNAVAILABLE", "Item search is unavailable. Please try again.", 503) from exc

    async def find_search_by_key(self, key: UUID) -> dict | None:
        try:
            client = self.require()
            result = await run_in_threadpool(lambda: client.table("search_requests").select("id,user_id,query_analysis,last_seen_location").eq("idempotency_key", str(key)).maybe_single().execute())
            return result.data if result is not None else None
        except Exception as exc:
            log.exception("Search idempotency lookup failed")
            raise ServiceError("SUPABASE_UNAVAILABLE", "Item search is unavailable. Please try again.", 503) from exc

    async def search_candidates(self, search_id: str) -> list[dict]:
        try:
            client = self.require()
            result = await run_in_threadpool(lambda: client.table("match_candidates").select("id,decision,rank,rank_score,score_breakdown,matched_attributes,differences,explanation,found_item_id").eq("search_request_id", search_id).order("rank").execute())
            return result.data or []
        except Exception as exc:
            log.exception("Search candidate lookup failed")
            raise ServiceError("SUPABASE_UNAVAILABLE", "Search results are unavailable. Please try again.", 503) from exc

    async def create_search(self, row: dict, candidates: list[dict]) -> None:
        client = self.require()
        try:
            await run_in_threadpool(lambda: client.rpc("record_sauli_search", {"p_search": row, "p_candidates": candidates}).execute())
        except Exception as exc:
            log.exception("Atomic search audit insert failed")
            raise ServiceError("DATABASE_INSERT_FAILED", "The search could not be recorded. Please try again.", 503) from exc

    async def report_rpc(self, name: str, params: dict | None = None):
        try:
            client = self.require()
            response = await run_in_threadpool(lambda: client.rpc(name, params or {}).execute())
            return response.data
        except ServiceError:
            raise
        except Exception as exc:
            log.exception("Missing-report database operation failed: %s", name)
            raise ServiceError("REPORT_STORAGE_UNAVAILABLE", "Missing-item monitoring is temporarily unavailable.", 503) from exc

    async def create_missing_report(self, search_id: UUID, user_id: UUID, email: str,
                                    enabled: bool, name: str, key: UUID) -> dict:
        return await self.report_rpc("sauli_create_missing_report", {
            "p_search_id": str(search_id), "p_user_id": str(user_id), "p_email": email,
            "p_enabled": enabled, "p_name": name, "p_key": str(key)})

    async def get_missing_report(self, report_id: UUID, user_id: UUID | None = None) -> dict | None:
        try:
            client = self.require()
            def fetch():
                query = client.table("missing_reports").select("*").eq("id", str(report_id))
                if user_id is not None:
                    query = query.eq("claimant_user_id", str(user_id))
                response = query.maybe_single().execute()
                return response.data if response else None
            return await run_in_threadpool(fetch)
        except Exception as exc:
            log.exception("Missing-report lookup failed")
            raise ServiceError("REPORT_STORAGE_UNAVAILABLE", "The missing-item report is unavailable.", 503) from exc

    async def list_missing_reports(self, user_id: UUID) -> list[dict]:
        try:
            client = self.require()
            response = await run_in_threadpool(lambda: client.table("missing_reports")
                .select("id,search_request_id,summary,notification_email,email_notifications_enabled,status,created_at")
                .eq("claimant_user_id", str(user_id)).order("created_at", desc=True).execute())
            return response.data or []
        except Exception as exc:
            log.exception("Missing-report list failed")
            raise ServiceError("REPORT_STORAGE_UNAVAILABLE", "Missing-item reports are unavailable.", 503) from exc

    async def get_match_decision(self, candidate_id: UUID) -> str | None:
        try:
            client = self.require()
            response = await run_in_threadpool(lambda: client.table("match_candidates")
                .select("decision").eq("id", str(candidate_id)).maybe_single().execute())
            return response.data["decision"] if response and response.data else None
        except Exception as exc:
            log.exception("Match decision lookup failed")
            raise ServiceError("REPORT_STORAGE_UNAVAILABLE", "The match is unavailable.", 503) from exc

    async def active_missing_reports(self) -> list[dict]:
        try:
            client = self.require()
            return await run_in_threadpool(lambda: client.table("missing_reports").select("*")
                .eq("status", "active").execute().data or [])
        except Exception as exc:
            log.exception("Active report lookup failed")
            raise ServiceError("REPORT_STORAGE_UNAVAILABLE", "Missing-item monitoring is unavailable.", 503) from exc

    async def search_request(self, search_id: UUID) -> dict | None:
        try:
            client = self.require()
            response = await run_in_threadpool(lambda: client.table("search_requests")
                .select("id,user_id,description,category,color,last_seen_location,last_seen_at,filters,query_analysis,search_summary")
                .eq("id", str(search_id)).maybe_single().execute())
            return response.data if response else None
        except Exception as exc:
            log.exception("Report search lookup failed")
            raise ServiceError("REPORT_STORAGE_UNAVAILABLE", "Search details are unavailable.", 503) from exc

    async def store_report_matches(self, report_id: UUID, job_id: UUID,
                                   candidates: list[dict], min_score: float) -> dict:
        return await self.report_rpc("sauli_store_report_matches", {
            "p_report_id": str(report_id), "p_job_id": str(job_id),
            "p_matches": candidates, "p_min_score": min_score})

    async def claim_matching_job(self) -> dict | None:
        return await self.report_rpc("sauli_claim_matching_job")

    async def finish_matching_job(self, job_id: UUID, status: str, error: str | None = None) -> None:
        await self.report_rpc("sauli_finish_matching_job", {
            "p_id": str(job_id), "p_status": status, "p_error": error})

    async def claim_email_notification(self) -> dict | None:
        return await self.report_rpc("sauli_claim_email_notification")

    async def finish_email_notification(self, notification_id: UUID, status: str,
                                        error: str | None = None, response: str | None = None) -> None:
        await self.report_rpc("sauli_finish_email_notification", {
            "p_id": str(notification_id), "p_status": status,
            "p_error": error, "p_response": response})

    async def retry_unconfigured_email(self) -> int:
        return await self.report_rpc("sauli_retry_unconfigured_email")

    async def retry_provider_denied_email(self, report_id: UUID) -> int:
        """Requeue a known pre-delivery 403 once an admin fixes EmailJS access."""
        report = await self.get_missing_report(report_id)
        if not report or report["status"] != "active" or not report["email_notifications_enabled"]:
            return 0
        try:
            client = self.require()
            response = await run_in_threadpool(lambda: client.table("email_notifications")
                .update({"status": "pending", "next_attempt_at": datetime.now(UTC).isoformat(),
                         "last_error": None, "provider_response": None})
                .eq("missing_report_id", str(report_id)).eq("status", "failed")
                .eq("last_error", "Provider HTTP 403").eq("provider_response", "403")
                .select("id").execute())
            return len(response.data or [])
        except Exception as exc:
            log.exception("Denied EmailJS notification retry failed")
            raise ServiceError("REPORT_STORAGE_UNAVAILABLE", "The notification could not be requeued.", 503) from exc

    async def retrieval_rpc(self, name: str, params: dict) -> dict:
        try:
            client = self.require()
            response = await run_in_threadpool(lambda: client.rpc(name, params).execute())
            if not isinstance(response.data, dict):
                raise ValueError("Unexpected retrieval response")
            return response.data
        except ServiceError:
            raise
        except Exception as exc:
            log.exception("Retrieval transaction failed: %s", name)
            raise ServiceError("RETRIEVAL_UNAVAILABLE", "Retrieval is unavailable. Please try again.", 503) from exc

    async def issue_retrieval(self, candidate_id: UUID, user_id: UUID, digest: str,
                              ttl_minutes: int, display_name: str) -> dict:
        return await self.retrieval_rpc("sauli_issue_retrieval", {"p_candidate_id": str(candidate_id),
            "p_user_id": str(user_id), "p_token_hash": digest, "p_ttl_minutes": ttl_minutes,
            "p_display_name": display_name})

    async def retrieval_status(self, session_id: UUID, user_id: UUID) -> dict:
        row = await self.retrieval_rpc("sauli_retrieval_status", {"p_session_id": str(session_id),
            "p_user_id": str(user_id)})
        if row.get("error") or "wrong_item_out" in row:
            return row
        # Keep phones in sync while the additive live-status migration is being
        # applied. The old RPC already verified claimant ownership.
        try:
            client = self.require()
            def fetch_live_fields():
                session_rows = (client.table("retrieval_sessions")
                    .select("claimant_display_name,wrong_item_out,validated_at,completed_at")
                    .eq("id", str(session_id)).eq("claimant_user_id", str(user_id))
                    .limit(1).execute().data or [])
                if not session_rows:
                    return {"error": "RETRIEVAL_NOT_FOUND"}
                session = session_rows[0]
                live = {"validated_at": session["validated_at"],
                    "completed_at": session["completed_at"],
                    "wrong_item_out": row["status"] == "validated" and session["wrong_item_out"],
                    "retriever": session["claimant_display_name"],
                    "slot_code": None, "section": None}
                if row["status"] in ("validated", "completed"):
                    events = (client.table("retrieval_events")
                        .select("storage_slot_id").eq("retrieval_session_id", str(session_id))
                        .eq("event_type", "qr_validated").order("id", desc=True)
                        .limit(1).execute().data or [])
                    if events and events[0]["storage_slot_id"]:
                        slots = (client.table("storage_slots").select("code,size_class")
                            .eq("id", events[0]["storage_slot_id"]).limit(1).execute().data or [])
                        if slots:
                            live["slot_code"] = slots[0]["code"]
                            live["section"] = slots[0]["size_class"]
                return live
            return {**row, **await run_in_threadpool(fetch_live_fields)}
        except Exception as exc:
            log.exception("Retrieval live status lookup failed")
            raise ServiceError("RETRIEVAL_UNAVAILABLE", "Retrieval status is unavailable. Please try again.", 503) from exc

    async def replace_retrieval(self, session_id: UUID, user_id: UUID, digest: str,
                                ttl_minutes: int) -> dict:
        return await self.retrieval_rpc("sauli_replace_retrieval", {"p_session_id": str(session_id),
            "p_user_id": str(user_id), "p_token_hash": digest, "p_ttl_minutes": ttl_minutes})

    async def validate_retrieval(self, digest: str, action_digest: str) -> dict:
        return await self.retrieval_rpc("sauli_validate_retrieval", {"p_token_hash": digest,
            "p_action_hash": action_digest})

    async def simulate_retrieval(self, session_id: UUID, action_digest: str, event: str) -> dict:
        return await self.retrieval_rpc("sauli_simulate_retrieval", {"p_session_id": str(session_id),
            "p_action_hash": action_digest, "p_event": event})

    async def retrieval_logs(self, claimant_user_id: UUID | None = None) -> list[dict]:
        try:
            client = self.require()
            def fetch():
                rows = []
                offset = 0
                while True:
                    query = client.table("retrieval_logs").select(
                        "id,retrieval_session_id,retriever,item_summary,slot_code,retrieved_at,completion_source"
                    )
                    if claimant_user_id is not None:
                        query = query.eq("claimant_user_id", str(claimant_user_id))
                    response = (query.order("retrieved_at", desc=True).order("id", desc=True)
                        .range(offset, offset + 499).execute())
                    batch = response.data or []
                    rows.extend(batch)
                    if len(batch) < 500:
                        return rows
                    offset += 500
            return await run_in_threadpool(fetch)
        except Exception as exc:
            log.exception("Retrieval log lookup failed")
            raise ServiceError("RETRIEVAL_UNAVAILABLE", "Retrieval logs are unavailable. Please try again.", 503) from exc

    async def claimant_retrieval_logs(self, user_id: UUID) -> list[dict]:
        return await self.retrieval_logs(user_id)
