"""Explicit opt-in, fake-provider server for browser regression tests.

Requires TEST_DATABASE_URL pointing to disposable PostgreSQL ending in _test.
Run with python -m tests.ui_server; never use this fixture as the actual assistant.
"""

import asyncio
import os
from collections.abc import AsyncIterator
from uuid import UUID

import uvicorn
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from alembic import command
from app.api.dependencies import get_provider, get_streaming_provider
from app.core.config import Settings
from app.db.provision import provision
from app.providers import GenerationRequest, GenerationResult, StreamCompleted, TextDelta
from app.schemas.theme import Theme

TOKEN = "browser-test-token-000000000000000000"
USER_ID = UUID("f367bf59-431a-44ea-839e-371dbf4a26f9")


class PreviewProvider:
    def generate(self, request: GenerationRequest) -> GenerationResult:
        if "interface theme" in request.messages[0].content:
            if "invalid" in request.messages[-1].content:
                return GenerationResult('{"accent":"#ffffff"}')
            return GenerationResult(
                Theme(
                    background="#f4efe5",
                    surface="#fffdf7",
                    text="#302e24",
                    accent="#35533c",
                    font="serif",
                    font_size=18,
                ).model_dump_json()
            )
        return GenerationResult("Start with one manageable task. This is a test-provider sample.")


class ChatProvider:
    async def stream(
        self, request: GenerationRequest
    ) -> AsyncIterator[TextDelta | StreamCompleted]:
        if "slow" in request.messages[-1].content:
            for _ in range(60):
                yield TextDelta("Thinking… ")
                await asyncio.sleep(0.15)
        else:
            yield TextDelta("Here is a test response. ")
            await asyncio.sleep(0.1)
            yield TextDelta("Your conversation is ready.")
        yield StreamCompleted()


def main() -> None:
    url = os.environ["TEST_DATABASE_URL"]
    parsed = make_url(url)
    if parsed.drivername != "postgresql+psycopg" or not (parsed.database or "").endswith("_test"):
        raise ValueError("Use a disposable PostgreSQL *_test database")
    Settings.model_config["env_file"] = None
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ.update(
        DATABASE_URL=url,
        AUTH_USER_ID=str(USER_ID),
        AUTH_TOKEN=TOKEN,
        OPENAI_MODEL="test-model",
        CONTEXT_MODEL_BUDGETS='{"test-model":{"context_window_tokens":32768}}',
    )
    command.upgrade(Config("alembic.ini"), "head")
    engine = create_engine(url)
    with Session(engine) as session, session.begin():
        provision(session, USER_ID)
    engine.dispose()
    from app.main import create_app

    app = create_app()
    app.dependency_overrides[get_provider] = PreviewProvider
    app.dependency_overrides[get_streaming_provider] = ChatProvider
    uvicorn.run(app, host="127.0.0.1", port=8011)


if __name__ == "__main__":
    main()
