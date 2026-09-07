from collections.abc import Generator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.api.auth import current_user_id


def get_session(
    request: Request, user_id: Annotated[UUID, Depends(current_user_id)]
) -> Generator[Session, None, None]:
    # Authentication runs before a session is opened. Close rolls back uncommitted work.
    with request.app.state.session_factory() as session:
        yield session
