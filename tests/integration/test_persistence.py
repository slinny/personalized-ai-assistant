"""Run only against an explicitly named disposable PostgreSQL test database."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from alembic.config import Config
from sqlalchemy import Engine, delete, inspect, select
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from app.models import AssistantProfile, Conversation, Message, User


def graph(session: Session) -> tuple[User, AssistantProfile, Conversation]:
    user = User()
    session.add(user)
    session.flush()
    profile = AssistantProfile(user_id=user.id, name="Alice")
    session.add(profile)
    session.flush()
    conversation = Conversation(user_id=user.id, assistant_profile_id=profile.id)
    session.add(conversation)
    session.flush()
    return user, profile, conversation


def test_persistence_defaults_and_update(engine: Engine) -> None:
    with Session(engine) as session:
        user, profile, conversation = graph(session)
        user_id, profile_id, conversation_id = user.id, profile.id, conversation.id
        for position, status in enumerate(["in_progress", "completed", "cancelled", "failed"], 1):
            session.add(
                Message(
                    conversation_id=conversation.id,
                    position=position,
                    role="assistant",
                    status=status,
                )
            )
        session.commit()
    try:
        with Session(engine) as session:
            saved = session.get(AssistantProfile, profile_id)
            assert saved is not None
            assert saved.warmth == saved.verbosity == saved.humor == saved.formality == 0.5
            assert saved.primary_language == "en" and saved.language_switching_mode == "follow_user"
            assert saved.holiday_preferences == {} and saved.custom_instructions == ""
            assert not any(
                [
                    saved.morning_greeting_enabled,
                    saved.evening_greeting_enabled,
                    saved.good_night_greeting_enabled,
                ]
            )
            assert saved.preferred_model is None and saved.preferred_user_name is None
            assert saved.created_at.utcoffset() == timedelta(0)
            old_time = datetime(2000, 1, 1, tzinfo=UTC)
            saved.updated_at = old_time
            session.commit()
            saved.name = "Updated Alice"
            saved.holiday_preferences = {"new_year": "Happy New Year"}
            saved.custom_instructions = "中" * 10000
            session.commit()
            session.refresh(saved)
            assert saved.updated_at > old_time
            messages = session.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.position)
            ).all()
            assert [m.position for m in messages] == [1, 2, 3, 4]
            assert [m.status for m in messages] == [
                "in_progress",
                "completed",
                "cancelled",
                "failed",
            ]
            assert all(m.content == "" for m in messages)
        with Session(engine) as session:
            saved = session.get(AssistantProfile, profile_id)
            assert saved is not None and saved.holiday_preferences == {"new_year": "Happy New Year"}
            assert saved.custom_instructions == "中" * 10000
    finally:
        with Session(engine) as session:
            session.execute(delete(Conversation).where(Conversation.id == conversation_id))
            session.execute(delete(AssistantProfile).where(AssistantProfile.id == profile_id))
            session.execute(delete(User).where(User.id == user_id))
            session.commit()


@pytest.mark.parametrize(
    "field,value",
    [
        ("warmth", -0.1),
        ("verbosity", 1.1),
        ("humor", float("nan")),
        ("formality", float("inf")),
        ("name", " "),
        ("primary_language", ""),
        ("language_switching_mode", "sticky"),
        ("custom_instructions", "x" * 10001),
        ("holiday_preferences", []),
        ("preferred_model", ""),
        ("preferred_user_name", ""),
    ],
)
def test_invalid_profile(session: Session, field: str, value: Any) -> None:
    _, profile, _ = graph(session)
    setattr(profile, field, value)
    with pytest.raises(IntegrityError):
        session.flush()


@pytest.mark.parametrize(
    "field,value",
    [("role", "system"), ("status", "unknown"), ("position", 0), ("conversation_id", uuid.uuid4())],
)
def test_invalid_message(session: Session, field: str, value: Any) -> None:
    _, _, conversation = graph(session)
    message = Message(conversation_id=conversation.id, position=1, role="user", status="completed")
    setattr(message, field, value)
    session.add(message)
    with pytest.raises(IntegrityError):
        session.flush()


def test_ownership_and_uniqueness(session: Session) -> None:
    user, profile, conversation = graph(session)
    other = User()
    session.add(other)
    session.flush()
    invalid_records = [
        AssistantProfile(user_id=user.id, name="Duplicate"),
        AssistantProfile(user_id=uuid.uuid4(), name="Orphan"),
        Conversation(user_id=other.id, assistant_profile_id=profile.id),
        Conversation(user_id=user.id, assistant_profile_id=uuid.uuid4()),
    ]
    for record in invalid_records:
        with pytest.raises(IntegrityError), session.begin_nested():
            session.add(record)
            session.flush()
    session.add(
        Message(conversation_id=conversation.id, position=1, role="user", status="completed")
    )
    session.flush()
    with pytest.raises(IntegrityError), session.begin_nested():
        session.add(
            Message(
                conversation_id=conversation.id, position=1, role="assistant", status="in_progress"
            )
        )
        session.flush()


def test_deletion_contract(session: Session) -> None:
    user, profile, conversation = graph(session)
    session.add(
        Message(conversation_id=conversation.id, position=1, role="user", status="completed")
    )
    session.flush()
    for statement in [
        delete(User).where(User.id == user.id),
        delete(AssistantProfile).where(AssistantProfile.id == profile.id),
    ]:
        with pytest.raises(IntegrityError), session.begin_nested():
            session.execute(statement)
    session.execute(delete(Conversation).where(Conversation.id == conversation.id))
    assert (
        session.scalar(select(Message.id).where(Message.conversation_id == conversation.id)) is None
    )


def test_migration_cycle(engine: Engine) -> None:
    # This fixture is explicitly opt-in and accepts disposable *_test databases only.
    config = Config("alembic.ini")
    command.downgrade(config, "base")
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    command.upgrade(config, "head")
    assert set(inspect(engine).get_table_names()) == {
        "alembic_version",
        "users",
        "assistant_profiles",
        "conversations",
        "messages",
    }
    command.check(config)


@pytest.mark.parametrize(
    "field,limit",
    [
        ("name", 100),
        ("preferred_user_name", 100),
        ("primary_language", 35),
        ("preferred_model", 200),
    ],
)
def test_profile_string_limits(session: Session, field: str, limit: int) -> None:
    _, profile, _ = graph(session)
    setattr(profile, field, "x" * limit)
    session.flush()
    setattr(profile, field, "x" * (limit + 1))
    with pytest.raises(DataError):
        session.flush()


def test_required_message_status(session: Session) -> None:
    _, _, conversation = graph(session)
    session.add(Message(conversation_id=conversation.id, role="assistant", position=1))
    with pytest.raises(IntegrityError):
        session.flush()


def test_personality_boundaries(session: Session) -> None:
    _, profile, _ = graph(session)
    profile.warmth = profile.humor = 0.0
    profile.verbosity = profile.formality = 1.0
    session.flush()
    session.refresh(profile)
    assert (profile.warmth, profile.humor, profile.verbosity, profile.formality) == (0, 0, 1, 1)
