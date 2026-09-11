"""Task 2 persistence models; importing this module registers all tables."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class Record:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(Record, Base):
    __tablename__ = "users"


class AssistantProfile(Record, Base):
    __tablename__ = "assistant_profiles"
    __table_args__ = (
        UniqueConstraint("user_id"),
        UniqueConstraint("id", "user_id"),
        CheckConstraint("length(trim(name)) > 0", name="name_nonempty"),
        CheckConstraint(
            "preferred_user_name IS NULL OR length(trim(preferred_user_name)) > 0",
            name="preferred_name_nonempty",
        ),
        CheckConstraint("warmth BETWEEN 0 AND 1", name="warmth_range"),
        CheckConstraint("verbosity BETWEEN 0 AND 1", name="verbosity_range"),
        CheckConstraint("humor BETWEEN 0 AND 1", name="humor_range"),
        CheckConstraint("formality BETWEEN 0 AND 1", name="formality_range"),
        CheckConstraint("length(trim(primary_language)) > 0", name="language_nonempty"),
        CheckConstraint(
            "language_switching_mode IN ('follow_user', 'fixed')", name="language_mode"
        ),
        CheckConstraint("length(custom_instructions) <= 10000", name="instructions_length"),
        CheckConstraint("jsonb_typeof(holiday_preferences) = 'object'", name="holiday_object"),
        CheckConstraint(
            "preferred_model IS NULL OR length(trim(preferred_model)) > 0", name="model_nonempty"
        ),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(100))
    preferred_user_name: Mapped[str | None] = mapped_column(String(100))
    warmth: Mapped[float] = mapped_column(Float, server_default=text("0.5"))
    verbosity: Mapped[float] = mapped_column(Float, server_default=text("0.5"))
    humor: Mapped[float] = mapped_column(Float, server_default=text("0.5"))
    formality: Mapped[float] = mapped_column(Float, server_default=text("0.5"))
    primary_language: Mapped[str] = mapped_column(String(35), server_default=text("'en'"))
    language_switching_mode: Mapped[str] = mapped_column(
        String(20), server_default=text("'follow_user'")
    )
    custom_instructions: Mapped[str] = mapped_column(Text, server_default=text("''"))
    morning_greeting_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    evening_greeting_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    good_night_greeting_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    holiday_preferences: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    preferred_model: Mapped[str | None] = mapped_column(String(200))
    appearance: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class Conversation(Record, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["assistant_profile_id", "user_id"],
            ["assistant_profiles.id", "assistant_profiles.user_id"],
            ondelete="RESTRICT",
        ),
        Index("ix_conversations_user_id_created_at", "user_id", "created_at"),
        Index("ix_conversations_assistant_profile_id_user_id", "assistant_profile_id", "user_id"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    assistant_profile_id: Mapped[uuid.UUID] = mapped_column(Uuid)


class Message(Record, Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "position"),
        CheckConstraint("position > 0", name="position_positive"),
        CheckConstraint("role IN ('user', 'assistant')", name="role"),
        CheckConstraint(
            "status IN ('in_progress', 'completed', 'cancelled', 'failed')", name="status"
        ),
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    position: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text, server_default=text("''"))
    status: Mapped[str] = mapped_column(String(20))


class MemoryNote(Record, Base):
    __tablename__ = "memory_notes"
    __table_args__ = (
        CheckConstraint(
            "length(trim(content)) > 0 AND length(content) <= 300", name="content_length"
        ),
        Index("ix_memory_notes_user_id_updated_at", "user_id", "updated_at"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    content: Mapped[str] = mapped_column(String(300))
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL")
    )
