from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.db.session import build_engine, build_session_factory
from app.main import create_app


def test_health_without_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://unused:unused@127.0.0.1:1/unavailable")
    with TestClient(create_app()) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_settings_environment_overrides_dotenv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("APP_NAME=From file\n")
    monkeypatch.setenv("APP_NAME", "From environment")
    assert Settings().app_name == "From environment"


@pytest.mark.parametrize("url", ["not-a-url", "sqlite:///test.db", "postgresql://a:b@db/app"])
def test_invalid_database_configuration(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    monkeypatch.setenv("DATABASE_URL", url)
    with pytest.raises(ValidationError):
        Settings()


def test_engine_and_session_are_lazy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://a:b@127.0.0.1:1/app")
    engine = build_engine(Settings())
    try:
        assert engine.dialect.name == "postgresql"
        assert engine.dialect.driver == "psycopg"
        with build_session_factory(engine)() as session:
            assert session.get_bind() is engine
            assert not session.in_transaction()
    finally:
        engine.dispose()
