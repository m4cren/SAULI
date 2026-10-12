"""Reuse search evidence for durable, qualified missing-item matching."""

from uuid import UUID, uuid4

from app.core.errors import ServiceError
from app.schemas.search import QueryAnalysis, SearchRequest
from app.services.matching import (
    COMPARISON_BATCH_SIZE,
    compare_batch,
    eligible,
    feature_score,
    mapped_result,
    proximity,
    score,
    similarity,
)


def request_from_search(row: dict) -> SearchRequest:
    return SearchRequest.model_validate({
        "description": row["description"], "category": row.get("category"),
        "color": row.get("color"), "last_seen_location": row.get("last_seen_location"),
        "last_seen_at": row.get("last_seen_at"),
        "additional_filters": row.get("filters") or {},
    })


async def evaluate_report(repo, gateway, settings, report: dict,
                          job_id: UUID, only_item_id: str | None = None) -> dict:
    search = await repo.search_request(UUID(str(report["search_request_id"])))
    if not search:
        raise ServiceError("SEARCH_NOT_FOUND", "The original missing-item search is unavailable.", 404)
    request = request_from_search(search)
    query = QueryAnalysis.model_validate(search["query_analysis"])
    rows = await repo.eligible_items(request.last_seen_at.isoformat() if request.last_seen_at else None, 50)
    rows = [row for row in rows if eligible(row, request.last_seen_at)
            and (only_item_id is None or str(row["id"]) == only_item_id)
            and (not request.category or request.category.casefold() == str(row.get("category") or "").casefold())]
    candidates = []
    for start in range(0, len(rows), COMPARISON_BATCH_SIZE):
        batch = rows[start:start + COMPARISON_BATCH_SIZE]
        comparisons = await compare_batch(gateway, settings.ollama_model, request, query, batch)
        for row, comparison in zip(batch, comparisons):
            if not comparison.plausible and comparison.similarity < 0.65:
                continue
            location = similarity(request.last_seen_location or query.location,
                                  row.get("found_location")) if (request.last_seen_location or query.location) else 0.5
            value, breakdown = score(comparison, feature_score(query, row), location,
                                     proximity(row["created_at"], request.last_seen_at))
            if value < settings.match_notification_min_score:
                continue
            candidates.append({"id": str(uuid4()), "found_item_id": str(row["id"]),
                               "rank_score": value, "score_breakdown": breakdown.model_dump(),
                               "matched_attributes": comparison.matched_attributes,
                               "differences": comparison.differences, "explanation": comparison.explanation,
                               "ai_comparison": comparison.model_dump(mode="json")})
    candidates.sort(key=lambda entry: -entry["rank_score"])
    return await repo.store_report_matches(UUID(str(report["id"])), job_id, candidates,
                                           settings.match_notification_min_score)


async def process_matching_job(repo, gateway, settings, job: dict) -> None:
    if job["kind"] == "report_posted":
        report = await repo.get_missing_report(UUID(job["missing_report_id"]))
        if report and report["status"] == "active":
            await evaluate_report(repo, gateway, settings, report, UUID(job["id"]))
    else:
        # Check the exact item after placement committed; a reserved item is
        # absent from this occupied-only query and cannot trigger an email.
        item_id = str(job["found_item_id"])
        occupied = await repo.eligible_items(None, 100)
        if not any(str(row["id"]) == item_id and eligible(row, None) for row in occupied):
            return
        for report in await repo.active_missing_reports():
            await evaluate_report(repo, gateway, settings, report, UUID(job["id"]), item_id)


async def report_detail(repo, report: dict, min_score: float) -> dict:
    candidates = await repo.search_candidates(str(report["search_request_id"]))
    candidates = [candidate for candidate in candidates
                  if float(candidate["rank_score"]) >= min_score or candidate["decision"] == "accepted"]
    candidates.sort(key=lambda row: -float(row["rank_score"]))
    if report["status"] == "active":
        for candidate in candidates:
            if candidate["decision"] != "pending":
                continue
            row = await repo.get_item(UUID(candidate["found_item_id"]))
            if row and eligible(row, None):
                result = await mapped_result(repo, row, candidate)
                return {**report, "candidate": result,
                        "candidate_decision": "pending"}
    reviewed = next((row for row in candidates if row["decision"] == "accepted"), None)
    reviewed = reviewed or next((row for row in candidates if row["decision"] == "rejected"), None)
    return {**report, "candidate": None,
            "candidate_decision": reviewed["decision"] if reviewed else None}
