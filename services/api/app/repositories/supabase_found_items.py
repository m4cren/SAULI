"""Server-only Supabase data and private Storage access."""

import logging
from uuid import UUID

from starlette.concurrency import run_in_threadpool
from supabase import Client, create_client

from app.config import Settings
from app.core.errors import ServiceError

log = logging.getLogger("sauli.supabase")


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
            response = await run_in_threadpool(lambda: client.table("found_items").select("id,status,extraction_summary,found_location,found_at").eq("idempotency_key", str(key)).maybe_single().execute())
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
            result = await run_in_threadpool(lambda: client.table("found_items").select("id,status,object_name,extraction_summary,category,colors,visible_markings,condition,found_location,found_at,front_image_path,back_image_path,document_kind").eq("id", str(item_id)).maybe_single().execute())
            return result.data if result is not None else None
        except Exception as exc:
            log.exception("Found item lookup failed")
            raise ServiceError("SUPABASE_UNAVAILABLE", "Item details are unavailable. Please try again.", 503) from exc

    async def eligible_items(self, last_seen_at: str | None, limit: int = 50) -> list[dict]:
        try:
            client = self.require()
            result = await run_in_threadpool(lambda: client.rpc("get_eligible_found_items", {"p_last_seen_at": last_seen_at, "p_limit": limit}).execute())
            return result.data or []
        except Exception as exc:
            log.exception("Eligible item query failed")
            raise ServiceError("SUPABASE_UNAVAILABLE", "Item search is unavailable. Please try again.", 503) from exc

    async def find_search_by_key(self, key: UUID) -> dict | None:
        try:
            client = self.require()
            result = await run_in_threadpool(lambda: client.table("search_requests").select("id,query_analysis,last_seen_location").eq("idempotency_key", str(key)).maybe_single().execute())
            return result.data if result is not None else None
        except Exception as exc:
            log.exception("Search idempotency lookup failed")
            raise ServiceError("SUPABASE_UNAVAILABLE", "Item search is unavailable. Please try again.", 503) from exc

    async def search_candidates(self, search_id: str) -> list[dict]:
        try:
            client = self.require()
            result = await run_in_threadpool(lambda: client.table("match_candidates").select("rank,rank_score,score_breakdown,matched_attributes,differences,explanation,found_item_id").eq("search_request_id", search_id).order("rank").execute())
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
