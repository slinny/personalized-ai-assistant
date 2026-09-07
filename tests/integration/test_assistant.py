from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.db.provision import provision
from app.main import create_app
from app.models import AssistantProfile


def test_provision_preserves_profile(session: Session) -> None:
    user_id = uuid4()
    provision(session, user_id)
    profile = session.scalar(select(AssistantProfile).where(AssistantProfile.user_id == user_id))
    assert profile is not None
    profile.name = "Customized"
    session.flush()
    provision(session, user_id)
    session.refresh(profile)
    assert profile.name == "Customized"
    assert (
        len(
            session.scalars(
                select(AssistantProfile).where(AssistantProfile.user_id == user_id)
            ).all()
        )
        == 1
    )


def test_get_profile_and_ownership(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    user_id, other_id = uuid4(), uuid4()
    provision(session, other_id)
    app, headers = configured_app(monkeypatch, session, user_id)
    with TestClient(app) as client:
        assert client.get("/assistant", headers=headers).status_code == 404
        provision(session, user_id)
        response = client.get("/assistant", headers=headers)
        assert response.status_code == 200
        assert response.json()["user_id"] == str(user_id)
        assert response.json()["name"] == "Assistant"
        assert client.get("/assistant").status_code == 401


def configured_app(
    monkeypatch: pytest.MonkeyPatch, session: Session, user_id: UUID
) -> tuple[FastAPI, dict[str, str]]:
    monkeypatch.setenv("AUTH_TOKEN", "a" * 32)
    monkeypatch.setenv("AUTH_USER_ID", str(user_id))
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    return app, {"Authorization": "Bearer " + "a" * 32}
