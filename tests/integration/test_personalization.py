from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_provider, get_session
from app.db.provision import provision
from app.main import create_app
from app.models import AssistantProfile, Conversation
from app.providers import GenerationResult, ProviderTimeout
from app.providers.fake import FakeProvider
from app.schemas.theme import Theme


def test_theme_preview_save_and_isolation(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id, other_id = uuid4(), uuid4()
    for identity in (user_id, other_id):
        provision(session, identity)
    session.commit()
    monkeypatch.setenv("AUTH_USER_ID", str(user_id))
    monkeypatch.setenv("AUTH_TOKEN", "a" * 32)
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv("CONTEXT_MODEL_BUDGETS", '{"test-model":{"context_window_tokens":16000}}')
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    theme = Theme(font="serif", font_size=18)
    fake = FakeProvider(
        GenerationResult(theme.model_dump_json()),
        GenerationResult('{"text":"#ffffff"}'),
        ProviderTimeout(),
        GenerationResult("Start with one manageable task."),
    )
    app.dependency_overrides[get_provider] = lambda: fake
    headers = {"Authorization": "Bearer " + "a" * 32}
    with TestClient(app) as client:
        assert client.get("/assistant/theme").status_code == 401
        assert client.post("/assistant/theme/generate", json={"prompt": "cozy"}).status_code == 401
        initial = client.get("/assistant", headers=headers).json()
        assert client.get("/assistant/theme", headers=headers).json() == Theme().model_dump()
        generated = client.post(
            "/assistant/theme/generate", headers=headers, json={"prompt": "cozy"}
        )
        assert generated.status_code == 200
        assert generated.json() == theme.model_dump()
        assert client.get("/assistant/theme", headers=headers).json() == Theme().model_dump()
        assert not session.scalars(select(Conversation)).all()
        assert fake.requests[0].max_output_tokens <= 2048
        saved = client.put("/assistant/theme", headers=headers, json=generated.json())
        assert saved.status_code == 200
        session.expire_all()
        assert client.get("/assistant/theme", headers=headers).json() == theme.model_dump()
        for expected in (502, 504):
            assert (
                client.post(
                    "/assistant/theme/generate", headers=headers, json={"prompt": "refine"}
                ).status_code
                == expected
            )
            assert client.get("/assistant/theme", headers=headers).json() == theme.model_dump()
        assert (
            client.put("/assistant/theme", headers=headers, json={"accent": "#ffffff"}).status_code
            == 422
        )
        preview = client.post(
            "/assistant/preview", headers=headers, json={"changes": {"verbosity": 0.1}}
        )
        assert preview.status_code == 200
        assert preview.json()["text"] == "Start with one manageable task."
        unchanged = client.get("/assistant", headers=headers).json()
        assert unchanged["verbosity"] == initial["verbosity"]
        other = session.scalar(select(AssistantProfile).where(AssistantProfile.user_id == other_id))
        assert other is not None and other.appearance is None
        assert (
            client.put("/assistant/theme", headers=headers, json=Theme().model_dump()).status_code
            == 200
        )
