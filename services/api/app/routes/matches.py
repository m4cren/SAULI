from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials

from app.auth.dependencies import get_current_user
from app.integrations.supabase import bearer_scheme, verify_supabase_user
from app.routes.found_items import required_key
from app.schemas.auth import UserResponse
from app.schemas.search import ClaimDecisionResponse, SearchRequest, SearchResponse
from app.services.matching import run_search

router = APIRouter(prefix="/api/matches", tags=["matches"])


@router.post("/search", response_model=SearchResponse)
async def search(request: Request, payload: SearchRequest, x_idempotency_key: str | None = Header(None),
                 credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None):
    user = await verify_supabase_user(request, credentials) if credentials else None
    return await run_search(request.app.state.items, request.app.state.ollama,
                            request.app.state.settings.ollama_model, payload, required_key(x_idempotency_key),
                            UUID(user.id) if user else None)


@router.post("/{candidate_id}/confirm", response_model=ClaimDecisionResponse)
async def confirm_match(request: Request, candidate_id: UUID,
                        user: Annotated[UserResponse, Depends(get_current_user)]):
    result = await request.app.state.items.decide_match(candidate_id, UUID(user.id), "accepted")
    return ClaimDecisionResponse(match_candidate_id=candidate_id, decision="accepted",
        item_id=UUID(str(result["candidate"]["found_item_id"])))


@router.post("/{candidate_id}/reject", response_model=ClaimDecisionResponse)
async def reject_match(request: Request, candidate_id: UUID,
                       user: Annotated[UserResponse, Depends(get_current_user)]):
    await request.app.state.items.decide_match(candidate_id, UUID(user.id), "rejected")
    return ClaimDecisionResponse(match_candidate_id=candidate_id, decision="rejected")
