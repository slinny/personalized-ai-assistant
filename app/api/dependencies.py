from collections.abc import Generator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.auth import current_user_id
from app.providers import GenerationProvider, StreamingProvider


def get_session(
    request: Request, user_id: Annotated[UUID, Depends(current_user_id)]
) -> Generator[Session, None, None]:
    # Authentication runs before a session is opened. Close rolls back uncommitted work.
    with request.app.state.session_factory() as session:
        yield session


def get_provider(request: Request) -> GenerationProvider:
    provider: GenerationProvider | None = getattr(request.app.state, "provider", None)
    if provider is None:
        raise HTTPException(503, "Generation provider is not configured")
    return provider


def get_streaming_provider(request: Request) -> "StreamingProvider":
    provider: StreamingProvider | None = getattr(request.app.state, "streaming_provider", None)
    if provider is None:
        raise HTTPException(503, "Generation provider is not configured")
    return provider
