from sqlalchemy import MetaData

from alembic import context
from app.core.config import Settings
from app.db.session import build_engine

# Task 2 will replace this empty metadata with the actual domain model metadata.
target_metadata = MetaData()
settings = Settings()

if context.is_offline_mode():
    context.configure(
        url=str(settings.database_url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = build_engine(settings)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()
