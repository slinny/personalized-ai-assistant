"""Add small, explicitly managed user memory."""

import sqlalchemy as sa

from alembic import op

revision = "9a02"
down_revision = "9a01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "memory_notes",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.String(300), nullable=False),
        sa.Column("source_message_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "length(trim(content)) > 0 AND length(content) <= 300",
            name=op.f("ck_memory_notes_content_length"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memory_notes_user_id_updated_at", "memory_notes", ["user_id", "updated_at"])


def downgrade() -> None:
    op.drop_table("memory_notes")
