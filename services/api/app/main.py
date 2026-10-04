from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.integrations.ollama import OllamaGateway
from app.routes import health, me, ollama


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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.cors_origins),
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(health.router)
    app.include_router(me.router)
    app.include_router(ollama.router)
    return app


app = create_app()
