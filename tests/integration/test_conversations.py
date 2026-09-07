from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.db.provision import provision
from app.main import create_app


def test_conversation_api(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    user_id, other_id = uuid4(), uuid4()
    monkeypatch.setenv("AUTH_TOKEN", "a" * 32)
    monkeypatch.setenv("AUTH_USER_ID", str(user_id))
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    headers = {"Authorization": "Bearer " + "a" * 32}
    with TestClient(app) as client:
        assert client.post("/conversations", headers=headers).status_code == 404
        provision(session, user_id)
        created = client.post("/conversations", headers=headers)
        assert created.status_code == 201
        conversation_id = created.json()["id"]
        assert client.get("/conversations", headers=headers).json() == [created.json()]
        path = f"/conversations/{conversation_id}/messages"
        assert client.get(path, headers=headers).json() == []
        assert client.get(path).status_code == 401
        assert client.get("/conversations?limit=101", headers=headers).status_code == 422
        app.state.settings.auth_user_id = other_id
        assert client.get(path, headers=headers).status_code == 404
        assert client.get("/conversations", headers=headers).json() == []
