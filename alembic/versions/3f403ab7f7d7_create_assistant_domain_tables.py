"""Create assistant domain tables

Revision ID: 3f403ab7f7d7
Revises:
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "3f403ab7f7d7"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_table(
        "assistant_profiles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("preferred_user_name", sa.String(length=100), nullable=True),
        sa.Column("warmth", sa.Float(), server_default=sa.text("0.5"), nullable=False),
        sa.Column("verbosity", sa.Float(), server_default=sa.text("0.5"), nullable=False),
        sa.Column("humor", sa.Float(), server_default=sa.text("0.5"), nullable=False),
        sa.Column("formality", sa.Float(), server_default=sa.text("0.5"), nullable=False),
        sa.Column(
            "primary_language", sa.String(length=35), server_default=sa.text("'en'"), nullable=False
        ),
        sa.Column(
            "language_switching_mode",
            sa.String(length=20),
            server_default=sa.text("'follow_user'"),
            nullable=False,
        ),
        sa.Column("custom_instructions", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column(
            "morning_greeting_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "evening_greeting_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "good_night_greeting_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "holiday_preferences",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("preferred_model", sa.String(length=200), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "jsonb_typeof(holiday_preferences) = 'object'",
            name=op.f("ck_assistant_profiles_holiday_object"),
        ),
        sa.CheckConstraint(
            "language_switching_mode IN ('follow_user', 'fixed')",
            name=op.f("ck_assistant_profiles_language_mode"),
        ),
        sa.CheckConstraint(
            "formality BETWEEN 0 AND 1", name=op.f("ck_assistant_profiles_formality_range")
        ),
        sa.CheckConstraint("humor BETWEEN 0 AND 1", name=op.f("ck_assistant_profiles_humor_range")),
        sa.CheckConstraint(
            "length(custom_instructions) <= 10000",
            name=op.f("ck_assistant_profiles_instructions_length"),
        ),
        sa.CheckConstraint(
            "length(trim(name)) > 0", name=op.f("ck_assistant_profiles_name_nonempty")
        ),
        sa.CheckConstraint(
            "length(trim(primary_language)) > 0",
            name=op.f("ck_assistant_profiles_language_nonempty"),
        ),
        sa.CheckConstraint(
            "preferred_model IS NULL OR length(trim(preferred_model)) > 0",
            name=op.f("ck_assistant_profiles_model_nonempty"),
        ),
        sa.CheckConstraint(
            "preferred_user_name IS NULL OR length(trim(preferred_user_name)) > 0",
            name=op.f("ck_assistant_profiles_preferred_name_nonempty"),
        ),
        sa.CheckConstraint(
            "verbosity BETWEEN 0 AND 1", name=op.f("ck_assistant_profiles_verbosity_range")
        ),
        sa.CheckConstraint(
            "warmth BETWEEN 0 AND 1", name=op.f("ck_assistant_profiles_warmth_range")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_assistant_profiles_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assistant_profiles")),
        sa.UniqueConstraint("id", "user_id", name=op.f("uq_assistant_profiles_id")),
        sa.UniqueConstraint("user_id", name=op.f("uq_assistant_profiles_user_id")),
    )
    op.create_table(
        "conversations",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("assistant_profile_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["assistant_profile_id", "user_id"],
            ["assistant_profiles.id", "assistant_profiles.user_id"],
            name=op.f("fk_conversations_assistant_profile_id_assistant_profiles"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_conversations_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversations")),
    )
    op.create_index(
        "ix_conversations_assistant_profile_id_user_id",
        "conversations",
        ["assistant_profile_id", "user_id"],
        unique=False,
    )
    op.create_index(
        "ix_conversations_user_id_created_at",
        "conversations",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "messages",
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("role IN ('user', 'assistant')", name=op.f("ck_messages_role")),
        sa.CheckConstraint(
            "status IN ('in_progress', 'completed', 'cancelled', 'failed')",
            name=op.f("ck_messages_status"),
        ),
        sa.CheckConstraint("position > 0", name=op.f("ck_messages_position_positive")),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_messages_conversation_id_conversations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
        sa.UniqueConstraint(
            "conversation_id", "position", name=op.f("uq_messages_conversation_id")
        ),
    )


def downgrade() -> None:
    op.drop_table("messages")
    op.drop_index("ix_conversations_user_id_created_at", table_name="conversations")
    op.drop_index("ix_conversations_assistant_profile_id_user_id", table_name="conversations")
    op.drop_table("conversations")
    op.drop_table("assistant_profiles")
    op.drop_table("users")
