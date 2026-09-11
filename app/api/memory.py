from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from app.api.assistant import Database, UserId
from app.models import AssistantProfile, Conversation, MemoryNote, Message
from app.schemas.memory import MemoryCreate, MemoryEdit, MemoryResponse

router = APIRouter(prefix="/memories", tags=["memory"])


def lock_profile(user_id: UserId, session: Database) -> None:
    # Serialize all note mutations for a user, including concurrent inserts at the cap.
    profile = session.scalar(
        select(AssistantProfile).where(AssistantProfile.user_id == user_id).with_for_update()
    )
    if profile is None:
        raise HTTPException(404, "Assistant profile not found; run provisioning")


def owned_note(note_id: UUID, user_id: UserId, session: Database) -> MemoryNote:
    note = session.scalar(
        select(MemoryNote).where(MemoryNote.id == note_id, MemoryNote.user_id == user_id)
    )
    if note is None:
        raise HTTPException(404, "Memory note not found")
    return note


@router.get("", response_model=list[MemoryResponse])
def list_notes(user_id: UserId, session: Database) -> list[MemoryNote]:
    return list(
        session.scalars(
            select(MemoryNote)
            .where(MemoryNote.user_id == user_id)
            .order_by(MemoryNote.updated_at.desc(), MemoryNote.id.desc())
            .limit(20)
        )
    )


@router.post("", response_model=MemoryResponse, status_code=201)
def create_note(payload: MemoryCreate, user_id: UserId, session: Database) -> MemoryNote:
    lock_profile(user_id, session)
    count = session.scalar(
        select(func.count()).select_from(MemoryNote).where(MemoryNote.user_id == user_id)
    )
    if count is not None and count >= 20:
        raise HTTPException(409, "You can save up to 20 notes. Edit or delete a note first.")
    if payload.source_message_id is not None:
        source = session.scalar(
            select(Message.id)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(
                Message.id == payload.source_message_id,
                Message.role == "user",
                Conversation.user_id == user_id,
            )
        )
        if source is None:
            raise HTTPException(404, "Source user message not found")
    note = MemoryNote(user_id=user_id, **payload.model_dump())
    session.add(note)
    session.commit()
    session.refresh(note)
    return note


@router.patch("/{note_id}", response_model=MemoryResponse)
def edit_note(note_id: UUID, payload: MemoryEdit, user_id: UserId, session: Database) -> MemoryNote:
    lock_profile(user_id, session)
    note = owned_note(note_id, user_id, session)
    note.content = payload.content
    session.commit()
    session.refresh(note)
    return note


@router.delete("/{note_id}")
def delete_note(note_id: UUID, user_id: UserId, session: Database) -> dict[str, bool]:
    lock_profile(user_id, session)
    session.delete(owned_note(note_id, user_id, session))
    session.commit()
    return {"deleted": True}
