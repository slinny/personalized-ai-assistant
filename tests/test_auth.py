from typing import Annotated
from uuid import UUID, uuid4

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.auth import current_user_id
from app.core.config import Settings
from app.main import create_app


def private_route(user: Annotated[UUID, Depends(current_user_id)]) -> str:
    return str(user)


def test_authentication(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid4()
    monkeypatch.setenv("AUTH_TOKEN", "a" * 32)
    monkeypatch.setenv("AUTH_USER_ID", str(user_id))
    app = create_app()
    app.get("/private")(private_route)
    with TestClient(app) as client:
        for header in ["", "Basic abc", "Bearer", "Bearer wrong", "Bearer " + "b" * 32]:
            response = client.get("/private", headers={"Authorization": header})
            assert response.status_code == 401
            assert response.headers["www-authenticate"] == "Bearer"
        assert client.get(
            "/private", headers={"Authorization": "Bearer " + "a" * 32}
        ).json() == str(user_id)
        assert client.get("/health").status_code == 200


def test_disabled_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTH_TOKEN", raising=False)
    monkeypatch.delenv("AUTH_USER_ID", raising=False)
    app = create_app()
    app.get("/private")(private_route)
    with TestClient(app) as client:
        assert client.get("/private").status_code == 503


@pytest.mark.parametrize(
    "token,user",
    [("short", str(uuid4())), ("a" * 32, None), (None, str(uuid4())), ("a" * 32, "invalid")],
)
def test_invalid_auth_settings(token: str | None, user: str | None) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, auth_token=token, auth_user_id=user)  # type: ignore[call-arg, arg-type]
