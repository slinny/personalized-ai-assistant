"""Explicit, repeatable provisioning: python -m app.db.provision."""

from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import build_engine
from app.models import AssistantProfile, User


def provision(session: Session, user_id: UUID) -> None:
    session.execute(insert(User).values(id=user_id).on_conflict_do_nothing(index_elements=["id"]))
    session.execute(
        insert(AssistantProfile)
        .values(user_id=user_id, name="Assistant")
        .on_conflict_do_nothing(index_elements=["user_id"])
    )


def main() -> None:
    settings = Settings()
    if settings.auth_user_id is None:
        raise SystemExit("Configure AUTH_TOKEN and AUTH_USER_ID before provisioning")
    engine = build_engine(settings)
    try:
        with Session(engine) as session, session.begin():
            provision(session, settings.auth_user_id)
    finally:
        engine.dispose()
    print("User and assistant profile are ready.")


if __name__ == "__main__":
    main()
