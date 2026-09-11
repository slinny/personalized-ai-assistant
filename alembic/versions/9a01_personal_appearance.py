"""Add one versioned appearance per assistant profile."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "9a01"
down_revision = "3f403ab7f7d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assistant_profiles", sa.Column("appearance", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("assistant_profiles", "appearance")
