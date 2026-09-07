from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from openai import OpenAI

from app.api.assistant import router as assistant_router
from app.api.conversations import router as conversations_router
from app.api.health import router
from app.core.config import Settings
from app.db.session import build_engine, build_session_factory
from app.providers.openai import OpenAIProvider


def create_app() -> FastAPI:
    settings = Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        engine = build_engine(settings)
        application.state.session_factory = build_session_factory(engine)
        client = (
            OpenAI(
                api_key=settings.openai_api_key.get_secret_value(),
                timeout=settings.openai_timeout_seconds,
                max_retries=0,
            )
            if settings.openai_api_key is not None
            else None
        )
        application.state.provider = (
            OpenAIProvider(client, settings.openai_max_output_tokens) if client else None
        )
        try:
            yield
        finally:
            if client is not None:
                client.close()
            engine.dispose()

    application = FastAPI(title=settings.app_name, lifespan=lifespan)
    application.state.settings = settings
    application.include_router(router)
    application.include_router(assistant_router)
    application.include_router(conversations_router)
    return application


app = create_app()
