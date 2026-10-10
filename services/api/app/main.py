import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Settings
from app.core.errors import ServiceError
from app.integrations.ollama import OllamaGateway
from app.repositories.supabase_found_items import SupabaseFoundItemRepository
from app.routes import found_items, health, matches, me, ollama

log = logging.getLogger("sauli.api")


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as auth_http:
            gateway = OllamaGateway(config.ollama_base_url, config.ollama_timeout_seconds)
            app.state.auth_http = auth_http
            app.state.ollama = gateway
            try:
                yield
            finally:
                await gateway.close()

    app = FastAPI(title="SAULI API", lifespan=lifespan)
    app.state.settings = config
    app.state.items = SupabaseFoundItemRepository(config)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Idempotency-Key"],
    )
    @app.exception_handler(ServiceError)
    async def service_error(_request: Request, exc: ServiceError):
        return JSONResponse({"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _exc: RequestValidationError):
        return JSONResponse({"error": {"code": "INVALID_REQUEST", "message": "Check the submitted fields and try again."}}, status_code=422)

    @app.exception_handler(Exception)
    async def unexpected_error(_request: Request, _exc: Exception):
        log.exception("Unexpected API error")
        return JSONResponse({"error": {"code": "INTERNAL_SERVICE_FAILURE", "message": "The service could not complete the request. Please try again."}}, status_code=500)

    app.include_router(health.router)
    app.include_router(me.router)
    app.include_router(ollama.router)
    app.include_router(found_items.router)
    app.include_router(matches.router)
    return app


app = create_app()
