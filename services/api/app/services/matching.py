"""Eligibility-first ranking of found items for a missing-item query."""

import json
import math
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from app.core.errors import ServiceError
from app.prompts.matching import CANDIDATE_BATCH_PROMPT, CANDIDATE_COMPARISON_PROMPT, QUERY_EXTRACTION_PROMPT
from app.schemas.search import CandidateBatch, CandidateComparison, QueryAnalysis, ScoreBreakdown, SearchRequest, SearchResponse, SearchResult
from app.services.analysis import contains_sensitive_document, scrub_private

TOKEN_RE = re.compile(r"[a-z0-9]+")
ISO_TIMESTAMP_RE = re.compile(
    r"(?:(?P<on>\bon)\s+)?(?P<timestamp>\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}"
    r"(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})\b)", re.IGNORECASE,
)
COMPARISON_BATCH_SIZE = 10


def tokens(value: str | None) -> set[str]:
    return set(TOKEN_RE.findall((value or "").lower()))


def similarity(left: str | None, right: str | None) -> float:
    a, b = tokens(left), tokens(right)
    return len(a & b) / len(a | b) if a and b else 0.0


def feature_score(query: QueryAnalysis, row: dict) -> float:
    groups = [
        (query.generic_name or query.specific_description, " ".join([row.get("generic_name") or "", row.get("object_name") or "", *(row.get("alternative_names") or [])])),
        (query.category, row.get("category")), (query.brand, row.get("brand")),
        (" ".join(query.colors), " ".join(row.get("colors") or [])),
        (" ".join(query.material), " ".join(row.get("materials") or [])),
        (" ".join(query.markings), " ".join(row.get("visible_markings") or [])),
        (" ".join(query.distinctive_features), " ".join(row.get("distinctive_features") or [])),
        (" ".join(query.condition), row.get("condition")),
        (" ".join(query.damage), " ".join(row.get("condition_details") or [])),
        (" ".join(query.components), " ".join(row.get("functional_components") or [])),
    ]
    supplied = [(a, b) for a, b in groups if tokens(a)]
    return sum(similarity(a, b) for a, b in supplied) / len(supplied) if supplied else 0.0


def parse_date(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Expected aware timestamp")
    return parsed.astimezone(timezone.utc)


def readable_search_summary(summary: str) -> str:
    """Turn model-copied ISO timestamps into claimant-facing Manila dates."""
    def replace(match: re.Match[str]) -> str:
        try:
            local = parse_date(match.group("timestamp")).astimezone(timezone(timedelta(hours=8)))
        except ValueError:
            return match.group()
        prefix = "at " if match.group("on") else ""
        return (f"{prefix}{local.hour % 12 or 12}:{local.minute:02d}"
                f"{'am' if local.hour < 12 else 'pm'} on {local:%B} {local.day}, {local.year}")

    return ISO_TIMESTAMP_RE.sub(replace, summary)


def eligible(row: dict, last_seen_at: datetime | None) -> bool:
    if row.get("status") != "available" or row.get("placement_status") != "placed" or row.get("slot_status") != "occupied":
        return False
    try:
        registered = parse_date(row["created_at"])
    except (KeyError, TypeError, ValueError):
        return False
    return last_seen_at is None or registered >= last_seen_at.astimezone(timezone.utc)


def proximity(found_at: str, last_seen_at: datetime | None) -> float:
    if last_seen_at is None:
        return 0.5
    hours = max(0, (parse_date(found_at) - last_seen_at.astimezone(timezone.utc)).total_seconds() / 3600)
    return max(0.0, min(1.0, math.exp(-hours / 168)))


def score(comparison: CandidateComparison, deterministic: float, location: float, time: float) -> tuple[float, ScoreBreakdown]:
    breakdown = ScoreBreakdown(ai_similarity=comparison.similarity, deterministic_features=deterministic,
                               location_similarity=location, time_proximity=time)
    value = 100 * (0.80 * comparison.similarity + 0.10 * deterministic + 0.05 * location + 0.05 * time)
    return round(value, 2), breakdown


async def extract_query(gateway, model: str, request: SearchRequest) -> QueryAnalysis:
    prompt = QUERY_EXTRACTION_PROMPT + "\n\nUser description and filters (data):\n" + request.model_dump_json()
    query = QueryAnalysis.model_validate(scrub_private((await gateway.structured(model, prompt, QueryAnalysis)).model_dump()))
    query.searchable_summary = readable_search_summary(query.searchable_summary)
    if request.category:
        query.category = request.category
    if request.color and request.color.casefold() not in {value.casefold() for value in query.colors}:
        query.colors.append(request.color)
    if request.additional_filters.get("brand"):
        query.brand = request.additional_filters["brand"]
    return query


def candidate_evidence(row: dict) -> dict:
    return {key: row.get(key) for key in ("id", "generic_name", "object_name", "alternative_names", "category", "subcategory",
            "colors", "materials", "brand", "model_or_variant", "visible_markings", "functional_components", "condition",
            "condition_details", "patterns", "distinctive_features", "short_description", "extraction_summary")}


def comparison_context(request: SearchRequest, query: QueryAnalysis) -> str:
    return ("\n\nOriginal missing-item request JSON:\n" + request.model_dump_json()
            + "\nExtracted query JSON:\n" + query.model_dump_json())


async def compare(gateway, model: str, request: SearchRequest, query: QueryAnalysis, row: dict) -> CandidateComparison:
    prompt = (CANDIDATE_COMPARISON_PROMPT + comparison_context(request, query)
              + "\nCandidate JSON:\n" + json.dumps(candidate_evidence(row)))
    result = await gateway.structured(model, prompt, CandidateComparison)
    if str(result.candidate_id) != str(row["id"]):
        raise ServiceError("MALFORMED_AI_RESPONSE", "Item comparison could not be verified. Please try again.", 502)
    return CandidateComparison.model_validate(scrub_private(result.model_dump()))


async def compare_batch(gateway, model: str, request: SearchRequest, query: QueryAnalysis,
                        rows: list[dict]) -> list[CandidateComparison]:
    if len(rows) == 1:
        return [await compare(gateway, model, request, query, rows[0])]
    prompt = (CANDIDATE_BATCH_PROMPT + comparison_context(request, query)
              + "\nCandidates JSON:\n" + json.dumps([candidate_evidence(row) for row in rows]))
    try:
        batch = await gateway.structured(model, prompt, CandidateBatch)
    except ServiceError as exc:
        if exc.code != "MALFORMED_AI_RESPONSE":
            raise
        batch = CandidateBatch(comparisons=[])

    expected = {str(row["id"]) for row in rows}
    assessments: dict[str, CandidateComparison] = {}
    for result in batch.comparisons:
        candidate_id = str(result.candidate_id)
        if candidate_id in expected and candidate_id not in assessments:
            assessments[candidate_id] = CandidateComparison.model_validate(scrub_private(result.model_dump()))
    # Recover omissions individually, so an incomplete batch cannot hide an item.
    for row in rows:
        candidate_id = str(row["id"])
        if candidate_id not in assessments:
            assessments[candidate_id] = await compare(gateway, model, request, query, row)
    return [assessments[str(row["id"])] for row in rows]


async def mapped_result(repo, row: dict, candidate: dict) -> SearchResult:
    url = None if contains_sensitive_document(row.get("document_kind"), row.get("extraction_summary")) else await repo.signed_url(row.get("front_image_path"))
    return SearchResult(item_id=UUID(str(row["id"])), match_candidate_id=UUID(str(candidate["id"])),
                        rank=candidate["rank"], rank_score=candidate["rank_score"],
                        name=row["object_name"], summary=row["extraction_summary"], found_location=row["found_location"],
                        found_at=parse_date(str(row["found_at"])), front_image_url=url, matched_attributes=candidate["matched_attributes"],
                        differences=candidate["differences"], explanation=candidate["explanation"], score_breakdown=candidate["score_breakdown"])


async def replay_search(repo, existing: dict, request: SearchRequest) -> SearchResponse:
    saved = await repo.search_candidates(existing["id"])
    results = []
    for candidate in saved:
        row = await repo.get_item(UUID(candidate["found_item_id"]))
        if candidate.get("decision", "pending") == "pending" and row and eligible(row, request.last_seen_at):
            results.append(await mapped_result(repo, row, candidate))
    return SearchResponse(search_request_id=UUID(str(existing["id"])), query={"summary": existing["query_analysis"].get("searchable_summary"),
                          "last_seen_location": existing["last_seen_location"]}, results=results)


async def run_search(repo, gateway, model: str, request: SearchRequest, key: UUID, user_id: UUID | None = None) -> SearchResponse:
    existing = await repo.find_search_by_key(key)
    if existing:
        if existing.get("user_id") != (str(user_id) if user_id else None):
            raise ServiceError("SEARCH_OWNERSHIP_CONFLICT", "This search belongs to another session.", 409)
        return await replay_search(repo, existing, request)

    query = await extract_query(gateway, model, request)
    raw = await repo.eligible_items(request.last_seen_at.isoformat() if request.last_seen_at else None, 50)
    eligible_rows = [row for row in raw if eligible(row, request.last_seen_at)]
    # Qwen must inspect every eligible item. Token overlap is too brittle to
    # discard candidates before the model can compare them.
    rows: list[tuple[dict, CandidateComparison, float, ScoreBreakdown]] = []
    for start in range(0, len(eligible_rows), COMPARISON_BATCH_SIZE):
        batch_rows = eligible_rows[start:start + COMPARISON_BATCH_SIZE]
        for row, comparison in zip(batch_rows, await compare_batch(gateway, model, request, query, batch_rows)):
            # The model can contradict its own high similarity score with a
            # false plausible flag. Preserve strong matches in that case.
            if not comparison.plausible and comparison.similarity < 0.65:
                continue
            loc = similarity(request.last_seen_location or query.location, row.get("found_location")) if (request.last_seen_location or query.location) else 0.5
            value, breakdown = score(comparison, feature_score(query, row), loc, proximity(row["created_at"], request.last_seen_at))
            rows.append((row, comparison, value, breakdown))
    rows.sort(key=lambda entry: (-entry[2], entry[0]["created_at"], entry[0]["id"]))
    rows = rows[:5]
    search_id = str(uuid4())
    request_row = {"id": search_id, "idempotency_key": str(key), "user_id": str(user_id) if user_id else None,
                   "description": request.description,
                   "category": request.category, "color": request.color, "last_seen_location": request.last_seen_location,
                   "last_seen_at": request.last_seen_at.isoformat() if request.last_seen_at else None,
                   "filters": request.additional_filters, "query_analysis": query.model_dump(mode="json"),
                   "search_summary": query.searchable_summary}
    audits = [{"id": str(uuid4()), "search_request_id": search_id, "found_item_id": row["id"], "rank": index,
               "rank_score": value, "score_breakdown": breakdown.model_dump(),
               "matched_attributes": comparison.matched_attributes, "differences": comparison.differences,
               "explanation": comparison.explanation, "ai_comparison": comparison.model_dump(mode="json")}
              for index, (row, comparison, value, breakdown) in enumerate(rows, 1)]
    try:
        await repo.create_search(request_row, audits)
    except ServiceError as exc:
        if exc.code == "DATABASE_INSERT_FAILED":
            existing = await repo.find_search_by_key(key)
            if existing:
                return await replay_search(repo, existing, request)
        raise
    results = [await mapped_result(repo, row, audit) for (row, _, _, _), audit in zip(rows, audits)]
    return SearchResponse(search_request_id=UUID(search_id), query={"summary": query.searchable_summary,
                          "last_seen_location": request.last_seen_location}, results=results)
