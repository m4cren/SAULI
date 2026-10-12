"""EmailJS delivery from a database outbox; never callable from a browser."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from uuid import UUID

import httpx
from pydantic import ValidationError

from app.core.errors import ServiceError
from app.schemas.email_notifications import EmailJSTemplateParams
from app.services.missing_reports import process_matching_job

log = logging.getLogger("sauli.email_notifications")


MANILA_TIME = timezone(timedelta(hours=8))


def template_params(report: dict, item: dict, base_url: str) -> EmailJSTemplateParams:
    found = datetime.fromisoformat(str(item["found_at"]).replace("Z", "+00:00"))
    if found.tzinfo is None:
        raise ValueError("Found date must have a timezone")
    local_time = found.astimezone(MANILA_TIME)
    readable_date = (
        f"{local_time.strftime('%B')} {local_time.day}, {local_time.year} "
        f"at {local_time.hour % 12 or 12}:{local_time.minute:02d} "
        f"{'AM' if local_time.hour < 12 else 'PM'}"
    )
    return EmailJSTemplateParams.model_validate(
        {
            "to_email": report["notification_email"],
            "recipient_name": report.get("claimant_name") or "SAULI user",
            # Generic name avoids giving away distinctive markings or serial data.
            "item_summary": f"Possible matching {item.get('generic_name') or 'item'}",
            "found_location": item["found_location"],
            "found_date": readable_date,
            "match_url": f"{base_url.rstrip('/')}/missing/reports/{quote(str(report['id']), safe='')}",
        }
    )


class EmailJSClient:
    def __init__(self, settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self.client = client or httpx.AsyncClient(
            timeout=settings.emailjs_timeout_seconds, follow_redirects=False
        )
        self.owns_client = client is None

    async def close(self) -> None:
        if self.owns_client:
            await self.client.aclose()

    async def send(self, params: EmailJSTemplateParams) -> int:
        payload = {
            "service_id": self.settings.emailjs_service_id,
            "template_id": self.settings.emailjs_template_id,
            "user_id": self.settings.emailjs_public_key,
            "template_params": params.model_dump(),
        }
        if self.settings.emailjs_private_key:
            payload["accessToken"] = self.settings.emailjs_private_key
        response = await self.client.post(
            self.settings.emailjs_api_url,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        return response.status_code


async def deliver_one(repo, settings, sender: EmailJSClient) -> bool:
    notice = await repo.claim_email_notification()
    if not notice:
        return False
    notification_id = UUID(notice["id"])
    if not settings.emailjs_enabled:
        await repo.finish_email_notification(notification_id, "skipped_disabled")
        return True
    if not settings.emailjs_configured:
        log.warning("EmailJS configuration incomplete or frontend link is not public")
        await repo.finish_email_notification(
            notification_id, "skipped_unconfigured", "Configuration incomplete"
        )
        return True
    try:
        report = await repo.get_missing_report(UUID(notice["missing_report_id"]))
        item = await repo.get_item(UUID(notice["found_item_id"]))
        decision = await repo.get_match_decision(UUID(notice["match_candidate_id"]))
    except ServiceError:
        result = (
            "retry_pending"
            if notice["attempt_count"] < settings.emailjs_max_retries
            else "failed"
        )
        await repo.finish_email_notification(
            notification_id, result, "Delivery details temporarily unavailable"
        )
        return True
    if not report or not item:
        await repo.finish_email_notification(
            notification_id, "failed", "Report or item unavailable"
        )
        return True
    if (
        report["status"] != "active"
        or not report["email_notifications_enabled"]
        or decision != "pending"
        or item["status"] != "available"
        or item["placement_status"] != "placed"
        or item["slot_status"] != "occupied"
    ):
        await repo.finish_email_notification(notification_id, "cancelled")
        return True
    try:
        params = template_params(report, item, settings.frontend_base_url)
    except (KeyError, TypeError, ValueError, ValidationError):
        await repo.finish_email_notification(
            notification_id, "failed", "Invalid notification details"
        )
        return True
    try:
        status = await sender.send(params)
    except httpx.ConnectError:
        result = (
            "retry_pending"
            if notice["attempt_count"] < settings.emailjs_max_retries
            else "failed"
        )
        await repo.finish_email_notification(
            notification_id, result, "Connection failed before delivery"
        )
        return True
    except (httpx.TimeoutException, httpx.RequestError):
        # A request may have reached EmailJS. Preserve at-most-once behavior
        # until an operator checks the provider history.
        await repo.finish_email_notification(
            notification_id, "delivery_unknown", "Delivery outcome unknown"
        )
        return True
    if status == 200:
        await repo.finish_email_notification(notification_id, "sent", response="200")
    elif status == 429 and notice["attempt_count"] < settings.emailjs_max_retries:
        await repo.finish_email_notification(
            notification_id, "retry_pending", "Rate limited", str(status)
        )
    elif status >= 500:
        await repo.finish_email_notification(
            notification_id, "delivery_unknown", "Provider outcome unknown", str(status)
        )
    else:
        await repo.finish_email_notification(
            notification_id, "failed", f"Provider HTTP {status}", str(status)
        )
    return True


async def process_once(repo, gateway, settings, sender: EmailJSClient) -> bool:
    did_work = False
    job = await repo.claim_matching_job()
    if job:
        did_work = True
        try:
            await process_matching_job(repo, gateway, settings, job)
        except ServiceError as exc:
            status = "failed" if exc.code == "SEARCH_NOT_FOUND" else "retry_pending"
            await repo.finish_matching_job(UUID(job["id"]), status, exc.code)
        except Exception:
            log.exception("Missing-item matching job failed")
            await repo.finish_matching_job(
                UUID(job["id"]), "retry_pending", "MATCH_PROCESSING_FAILED"
            )
        else:
            await repo.finish_matching_job(UUID(job["id"]), "completed")
    return await deliver_one(repo, settings, sender) or did_work


async def run_worker(repo, gateway, settings, sender: EmailJSClient) -> None:
    while True:
        try:
            worked = await process_once(repo, gateway, settings, sender)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Missing-item worker could not reach its durable queue")
            worked = False
        await asyncio.sleep(1 if worked else 5)
