from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.assistant import router as assistant_router
from app.api.health import router
from app.core.config import Settings
from app.db.session import build_engine, build_session_factory


def create_app() -> FastAPI:
    settings = Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        engine = build_engine(settings)
        application.state.session_factory = build_session_factory(engine)
        try:
            yield
        finally:
            engine.dispose()

    application = FastAPI(title=settings.app_name, lifespan=lifespan)
    application.state.settings = settings
    application.include_router(router)
    application.include_router(assistant_router)
    return application


app = create_app()
