import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from ollama import ResponseError

from app.auth.dependencies import get_current_user
from app.schemas.ollama import OllamaStatusResponse

router = APIRouter(prefix="/api/v1")


@router.get("/ollama/status", response_model=OllamaStatusResponse, dependencies=[Depends(get_current_user)])
async def ollama_status(request: Request) -> OllamaStatusResponse:
    try:
        models = await request.app.state.ollama.list_model_names()
    except (httpx.TimeoutException, TimeoutError) as exc:
        raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, "Ollama did not respond in time") from exc
    except (ConnectionError, httpx.RequestError, ResponseError) as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Ollama is unavailable") from exc
    return OllamaStatusResponse(models=models)
