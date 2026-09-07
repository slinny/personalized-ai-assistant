from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.api.dependencies import get_session


def test_request_session_rolls_back_on_failure() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE probe (value INTEGER)"))
    request: Any = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(session_factory=sessionmaker(engine)))
    )
    dependency = get_session(request, uuid4())
    session = next(dependency)
    session.execute(text("INSERT INTO probe VALUES (1)"))
    with pytest.raises(RuntimeError):
        dependency.throw(RuntimeError("failed request"))
    with Session(engine) as check:
        assert check.scalar(text("SELECT count(*) FROM probe")) == 0
    engine.dispose()
