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


def test_send_lifecycle(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.dependencies import get_provider
    from app.providers import GenerationResult, ProviderTimeout
    from app.providers.fake import FakeProvider

    user_id = uuid4()
    provision(session, user_id)
    monkeypatch.setenv("AUTH_TOKEN", "a" * 32)
    monkeypatch.setenv("AUTH_USER_ID", str(user_id))
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv(
        "CONTEXT_MODEL_BUDGETS",
        '{"test-model":{"context_window_tokens":32768},'
        '"new-model":{"context_window_tokens":16384}}',
    )
    app = create_app()
    fake = FakeProvider(GenerationResult("Hello"), ProviderTimeout("secret"))
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_provider] = lambda: fake
    headers = {"Authorization": "Bearer " + "a" * 32}
    with TestClient(app) as client:
        conversation_id = client.post("/conversations", headers=headers).json()["id"]
        path = f"/conversations/{conversation_id}/messages"
        response = client.post(path, headers=headers, json={"content": "Hi"})
        assert response.status_code == 201
        assert response.json()["assistant_message"]["content"] == "Hello"
        assert response.json()["assistant_message"]["status"] == "completed"
        failed = client.post(path, headers=headers, json={"content": "Again"})
        assert failed.status_code == 504
        assert "secret" not in failed.text
        messages = client.get(path, headers=headers).json()
        assert [m["position"] for m in messages] == [1, 2, 3, 4]
        assert [m["status"] for m in messages] == ["completed"] * 3 + ["failed"]
        assert [m.content for m in fake.requests[1].messages[2:]] == ["Hi", "Hello", "Again"]
