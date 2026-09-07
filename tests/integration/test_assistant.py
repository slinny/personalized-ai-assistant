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


def test_patch_partial_updates(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid4()
    provision(session, user_id)
    app, headers = configured_app(monkeypatch, session, user_id)
    with TestClient(app) as client:
        initial = client.get("/assistant", headers=headers).json()
        assert client.patch("/assistant", headers=headers, json={}).json() == initial
        response = client.patch(
            "/assistant",
            headers=headers,
            json={
                "name": " Ada ",
                "warmth": 1,
                "preferred_model": "example-model",
                "holiday_preferences": {"new_year": "Happy New Year"},
            },
        )
        assert response.status_code == 200
        updated = response.json()
        assert updated["name"] == "Ada" and updated["warmth"] == 1
        assert updated["verbosity"] == initial["verbosity"]
        assert updated["id"] == initial["id"]
        assert (
            client.patch(
                "/assistant",
                headers=headers,
                json={
                    "preferred_model": None,
                    "holiday_preferences": {},
                },
            ).status_code
            == 200
        )
        session.expire_all()
        saved = client.get("/assistant", headers=headers).json()
        assert saved["preferred_model"] is None and saved["holiday_preferences"] == {}
        assert saved["name"] == "Ada"
        assert (
            client.patch(
                "/assistant",
                headers=headers,
                json={
                    "name": "Should not persist",
                    "warmth": 2,
                },
            ).status_code
            == 422
        )
        assert client.get("/assistant", headers=headers).json() == saved
        assert client.patch("/assistant", json={"name": "Unauthorized"}).status_code == 401
