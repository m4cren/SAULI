from fastapi import APIRouter, Header, Request

from app.routes.found_items import required_key
from app.schemas.search import SearchRequest, SearchResponse
from app.services.matching import run_search

router = APIRouter(prefix="/api/matches", tags=["matches"])


@router.post("/search", response_model=SearchResponse)
async def search(request: Request, payload: SearchRequest, x_idempotency_key: str | None = Header(None)):
    return await run_search(request.app.state.items, request.app.state.ollama,
                            request.app.state.settings.ollama_model, payload, required_key(x_idempotency_key))
