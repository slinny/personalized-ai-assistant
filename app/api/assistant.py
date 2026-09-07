from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import current_user_id
from app.api.dependencies import get_session
from app.models import AssistantProfile
from app.schemas.assistant import AssistantPatch, AssistantResponse

router = APIRouter(prefix="/assistant", tags=["assistant"])
UserId = Annotated[UUID, Depends(current_user_id)]
Database = Annotated[Session, Depends(get_session)]


def owned_profile(session: Session, user_id: UUID) -> AssistantProfile:
    profile = session.scalar(select(AssistantProfile).where(AssistantProfile.user_id == user_id))
    if profile is None:
        raise HTTPException(404, "Assistant profile not found; run provisioning")
    return profile


@router.get("", response_model=AssistantResponse)
def get_assistant(user_id: UserId, session: Database) -> AssistantProfile:
    return owned_profile(session, user_id)


@router.patch("", response_model=AssistantResponse)
def patch_assistant(
    payload: AssistantPatch, user_id: UserId, session: Database
) -> AssistantProfile:
    profile = owned_profile(session, user_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    session.commit()
    session.refresh(profile)
    return profile
