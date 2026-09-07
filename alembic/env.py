from alembic import context
from app.core.config import Settings
from app.db.session import build_engine
from app.models import Base

target_metadata = Base.metadata
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
