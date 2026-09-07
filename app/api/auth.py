import secrets
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings

bearer = HTTPBearer(auto_error=False)


def current_user_id(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> UUID:
    settings: Settings = request.app.state.settings
    if settings.auth_token is None or settings.auth_user_id is None:
        raise HTTPException(503, "Authentication is not configured")
    if credentials is None or not secrets.compare_digest(
        credentials.credentials.encode(), settings.auth_token.get_secret_value().encode()
    ):
        raise HTTPException(
            401, "Invalid bearer credentials", headers={"WWW-Authenticate": "Bearer"}
        )
    return settings.auth_user_id
