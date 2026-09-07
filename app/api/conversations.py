from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.assistant import Database, UserId, owned_profile
from app.api.dependencies import get_provider
from app.models import Conversation, Message
from app.providers import GenerationProvider, ProviderError, ProviderTimeout, ProviderUnavailable
from app.schemas.conversation import (
    ConversationResponse,
    MessageCreate,
    MessageResponse,
    TurnResponse,
)
from app.services.conversation import ConversationError, send_message

router = APIRouter(prefix="/conversations", tags=["conversations"])
Limit = Annotated[int, Query(ge=1, le=100)]


def owned_conversation(session: Session, user_id: UUID, conversation_id: UUID) -> Conversation:
    conversation = session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user_id
        )
    )
    if conversation is None:
        raise HTTPException(404, "Conversation not found")
    return conversation


@router.post("", response_model=ConversationResponse, status_code=201)
def create_conversation(user_id: UserId, session: Database) -> Conversation:
    profile = owned_profile(session, user_id)
    conversation = Conversation(user_id=user_id, assistant_profile_id=profile.id)
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return conversation


@router.get("", response_model=list[ConversationResponse])
def list_conversations(
    user_id: UserId,
    session: Database,
    limit: Limit = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Conversation]:
    return list(
        session.scalars(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.created_at.desc(), Conversation.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
def list_messages(
    conversation_id: UUID,
    user_id: UserId,
    session: Database,
    limit: Limit = 50,
    after_position: Annotated[int, Query(ge=0)] = 0,
) -> list[Message]:
    owned_conversation(session, user_id, conversation_id)
    return list(
        session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id, Message.position > after_position)
            .order_by(Message.position)
            .limit(limit)
        )
    )


@router.post("/{conversation_id}/messages", response_model=TurnResponse, status_code=201)
def post_message(
    conversation_id: UUID,
    payload: MessageCreate,
    user_id: UserId,
    session: Database,
    request: Request,
    provider: Annotated[GenerationProvider, Depends(get_provider)],
) -> TurnResponse:
    try:
        return send_message(
            session, user_id, conversation_id, payload.content, provider, request.app.state.settings
        )
    except ConversationError as error:
        raise HTTPException(error.status_code, error.detail) from None
    except ProviderTimeout:
        raise HTTPException(504, "Generation timed out") from None
    except ProviderUnavailable:
        raise HTTPException(503, "Generation is not configured") from None
    except ProviderError:
        raise HTTPException(502, "Generation failed") from None
