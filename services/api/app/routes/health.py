import logging

from fastapi import APIRouter, Request

router = APIRouter()


log = logging.getLogger("sauli.health")


@router.get("/health")
async def health(request: Request) -> dict[str, str]:
    settings = request.app.state.settings
    try:
        models = await request.app.state.ollama.list_model_names()
        ollama = "ready"
        model = "ready" if settings.ollama_model in models else "missing"
    except Exception:
        log.warning("Ollama health failed", exc_info=True)
        ollama, model = "unavailable", "unavailable"
    database = "ready" if await request.app.state.items.database_health() else "unavailable"
    storage = "ready" if await request.app.state.items.storage_health() else "unavailable"
    return {"status": "ok" if all(value == "ready" for value in (ollama, model, database, storage)) else "degraded",
            "api": "ready", "ollama": ollama, "ollama_model": settings.ollama_model,
            "ollama_model_status": model, "supabase_database": database,
            "supabase_storage": storage, "storage_bucket": settings.supabase_storage_bucket}
