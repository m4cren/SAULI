"""Eligibility-first ranking of found items for a missing-item query."""

import json
import math
import re
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.core.errors import ServiceError
from app.prompts.matching import CANDIDATE_COMPARISON_PROMPT, QUERY_EXTRACTION_PROMPT
from app.schemas.search import CandidateComparison, QueryAnalysis, ScoreBreakdown, SearchRequest, SearchResponse, SearchResult
from app.services.analysis import contains_sensitive_document, scrub_private

TOKEN_RE = re.compile(r"[a-z0-9]+")


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


def eligible(row: dict, last_seen_at: datetime | None) -> bool:
    if row.get("status") != "available":
        return False
    try:
        found = parse_date(row["found_at"])
    except (KeyError, TypeError, ValueError):
        return False
    return last_seen_at is None or found >= last_seen_at.astimezone(timezone.utc)


def proximity(found_at: str, last_seen_at: datetime | None) -> float:
    if last_seen_at is None:
        return 0.5
    hours = max(0, (parse_date(found_at) - last_seen_at.astimezone(timezone.utc)).total_seconds() / 3600)
    return max(0.0, min(1.0, math.exp(-hours / 168)))


def score(comparison: CandidateComparison, deterministic: float, location: float, time: float) -> tuple[float, ScoreBreakdown]:
    breakdown = ScoreBreakdown(ai_similarity=comparison.similarity, deterministic_features=deterministic,
                               location_similarity=location, time_proximity=time)
    value = 100 * (0.55 * comparison.similarity + 0.20 * deterministic + 0.15 * location + 0.10 * time)
    return round(value, 2), breakdown


async def extract_query(gateway, model: str, request: SearchRequest) -> QueryAnalysis:
    prompt = QUERY_EXTRACTION_PROMPT + "\n\nUser description and filters (data):\n" + request.model_dump_json()
    query = QueryAnalysis.model_validate(scrub_private((await gateway.structured(model, prompt, QueryAnalysis)).model_dump()))
    if request.category:
        query.category = request.category
    if request.color and request.color.casefold() not in {value.casefold() for value in query.colors}:
        query.colors.append(request.color)
    if request.additional_filters.get("brand"):
        query.brand = request.additional_filters["brand"]
    return query


async def compare(gateway, model: str, query: QueryAnalysis, row: dict) -> CandidateComparison:
    safe = {key: row.get(key) for key in ("id", "generic_name", "object_name", "alternative_names", "category", "subcategory",
            "colors", "materials", "brand", "model_or_variant", "visible_markings", "functional_components", "condition",
            "condition_details", "patterns", "distinctive_features", "short_description", "extraction_summary")}
    prompt = CANDIDATE_COMPARISON_PROMPT + "\n\nQuery JSON:\n" + query.model_dump_json() + "\nCandidate JSON:\n" + json.dumps(safe)
    result = await gateway.structured(model, prompt, CandidateComparison)
    if str(result.candidate_id) != str(row["id"]):
        raise ServiceError("MALFORMED_AI_RESPONSE", "Item comparison could not be verified. Please try again.", 502)
    return CandidateComparison.model_validate(scrub_private(result.model_dump()))


async def mapped_result(repo, row: dict, candidate: dict) -> SearchResult:
    url = None if contains_sensitive_document(row.get("document_kind"), row.get("extraction_summary")) else await repo.signed_url(row.get("front_image_path"))
    return SearchResult(item_id=UUID(str(row["id"])), rank=candidate["rank"], rank_score=candidate["rank_score"],
                        name=row["object_name"], summary=row["extraction_summary"], found_location=row["found_location"],
                        found_at=parse_date(str(row["found_at"])), front_image_url=url, matched_attributes=candidate["matched_attributes"],
                        differences=candidate["differences"], explanation=candidate["explanation"], score_breakdown=candidate["score_breakdown"])


async def replay_search(repo, existing: dict, request: SearchRequest) -> SearchResponse:
    saved = await repo.search_candidates(existing["id"])
    results = []
    for candidate in saved:
        row = await repo.get_item(UUID(candidate["found_item_id"]))
        if row and eligible(row, request.last_seen_at):
            results.append(await mapped_result(repo, row, candidate))
    return SearchResponse(search_request_id=UUID(str(existing["id"])), query={"summary": existing["query_analysis"].get("searchable_summary"),
                          "last_seen_location": existing["last_seen_location"]}, results=results)


async def run_search(repo, gateway, model: str, request: SearchRequest, key: UUID) -> SearchResponse:
    existing = await repo.find_search_by_key(key)
    if existing:
        return await replay_search(repo, existing, request)

    query = await extract_query(gateway, model, request)
    raw = await repo.eligible_items(request.last_seen_at.isoformat() if request.last_seen_at else None, 50)
    eligible_rows = [row for row in raw if eligible(row, request.last_seen_at)]
    ranked = sorted(eligible_rows, key=lambda row: (-feature_score(query, row), row["found_at"], row["id"]))[:5]
    rows: list[tuple[dict, CandidateComparison, float, ScoreBreakdown]] = []
    for row in ranked:
        comparison = await compare(gateway, model, query, row)
        if not comparison.plausible:
            continue
        loc = similarity(request.last_seen_location or query.location, row.get("found_location")) if (request.last_seen_location or query.location) else 0.5
        value, breakdown = score(comparison, feature_score(query, row), loc, proximity(row["found_at"], request.last_seen_at))
        rows.append((row, comparison, value, breakdown))
    rows.sort(key=lambda entry: (-entry[2], entry[0]["found_at"], entry[0]["id"]))
    search_id = str(uuid4())
    request_row = {"id": search_id, "idempotency_key": str(key), "description": request.description,
                   "category": request.category, "color": request.color, "last_seen_location": request.last_seen_location,
                   "last_seen_at": request.last_seen_at.isoformat() if request.last_seen_at else None,
                   "filters": request.additional_filters, "query_analysis": query.model_dump(mode="json"),
                   "search_summary": query.searchable_summary}
    audits = [{"search_request_id": search_id, "found_item_id": row["id"], "rank": index,
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
