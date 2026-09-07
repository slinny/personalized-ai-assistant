from sqlalchemy.dialects.postgresql.psycopg import PGDialect_psycopg
from sqlalchemy.schema import CreateTable

from app.models import Base


def test_postgresql_schema_contract() -> None:
    tables = Base.metadata.tables
    assert set(tables) == {"users", "assistant_profiles", "conversations", "messages"}
    dialect = PGDialect_psycopg()  # type: ignore[no-untyped-call]
    ddl = "\n".join(str(CreateTable(t).compile(dialect=dialect)) for t in tables.values())
    assert "FOREIGN KEY(assistant_profile_id, user_id)" in ddl
    assert "UNIQUE (conversation_id, position)" in ddl
    assert "TIMESTAMP WITH TIME ZONE" in ddl
    assert "JSONB" in ddl
    assert "ON DELETE CASCADE" in ddl
