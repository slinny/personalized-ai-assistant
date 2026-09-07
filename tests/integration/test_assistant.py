from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.provision import provision
from app.models import AssistantProfile


def test_provision_preserves_profile(session: Session) -> None:
    user_id = uuid4()
    provision(session, user_id)
    profile = session.scalar(select(AssistantProfile).where(AssistantProfile.user_id == user_id))
    assert profile is not None
    profile.name = "Customized"
    session.flush()
    provision(session, user_id)
    session.refresh(profile)
    assert profile.name == "Customized"
    assert (
        len(
            session.scalars(
                select(AssistantProfile).where(AssistantProfile.user_id == user_id)
            ).all()
        )
        == 1
    )
