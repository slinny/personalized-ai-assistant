from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings


def build_engine(settings: Settings) -> Engine:
    """Construct a lazy engine; the caller owns its lifetime and disposal."""
    return create_engine(
        str(settings.database_url), pool_pre_ping=True, connect_args={"connect_timeout": 5}
    )


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    # Callers explicitly commit successful writes; context exit rolls back unfinished work.
    return sessionmaker(bind=engine, expire_on_commit=False)
