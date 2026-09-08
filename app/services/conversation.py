import logging
from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import AssistantProfile, Conversation, Message
from app.providers import GenerationProvider, GenerationRequest, ProviderError, ProviderUnavailable
from app.schemas.conversation import MessageResponse, TurnResponse
from app.services.budget import resolve_budget
from app.services.context import build_context
from app.services.history import iter_history

logger = logging.getLogger(__name__)


class ConversationError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def locked_conversation(session: Session, user_id: UUID, conversation_id: UUID) -> Conversation:
    conversation = session.scalar(
        select(Conversation)
        .where(Conversation.id == conversation_id, Conversation.user_id == user_id)
        .with_for_update()
    )
    if conversation is None:
        raise ConversationError(404, "Conversation not found")
    return conversation


@dataclass(frozen=True)
class ReservedTurn:
    user_message: MessageResponse
    assistant_message: MessageResponse
    request: GenerationRequest


def reserve_turn(
    session: Session,
    user_id: UUID,
    conversation_id: UUID,
    content: str,
    settings: Settings,
) -> ReservedTurn:
    # The conversation row serializes reservation and finalization across processes.
    try:
        conversation = locked_conversation(session, user_id, conversation_id)
        now = session.scalar(select(func.clock_timestamp()))
        assert now is not None
        active = session.scalars(
            select(Message).where(
                Message.conversation_id == conversation_id, Message.status == "in_progress"
            )
        ).all()
        for message in active:
            if message.updated_at + timedelta(seconds=settings.generation_lease_seconds) > now:
                raise ConversationError(409, "A generation is already in progress")
            message.status = "failed"
        profile = session.get(AssistantProfile, conversation.assistant_profile_id)
        assert profile is not None
        model = profile.preferred_model or settings.openai_model
        if model is None:
            raise ProviderUnavailable("No generation model is configured")
        budget = resolve_budget(model, settings)
        history_scan_limit = settings.context_history_scan_limit
        request = build_context(
            profile,
            iter_history(session, conversation_id, history_scan_limit),
            content,
            model,
            budget,
        )
        position = (
            session.scalar(
                select(func.max(Message.position)).where(Message.conversation_id == conversation_id)
            )
            or 0
        )
        user = Message(
            conversation_id=conversation_id,
            position=position + 1,
            role="user",
            content=content,
            status="completed",
        )
        assistant = Message(
            conversation_id=conversation_id,
            position=position + 2,
            role="assistant",
            status="in_progress",
            updated_at=now,
        )
        session.add_all([user, assistant])
        conversation.updated_at = now
        session.flush()
        user_response = MessageResponse.model_validate(user)
        assistant_response = MessageResponse.model_validate(assistant)
        session.commit()
    except Exception:
        session.rollback()
        raise

    # No transaction or row lock remains open while waiting for the provider.
    assert request.context is not None
    logger.info(
        "Conversation context assembled",
        extra={
            "context_budget": asdict(request.context),
            "recovered_turns": len(active),
            "history_scan_limit_reached": (request.context.scanned_messages >= history_scan_limit),
        },
    )
    return ReservedTurn(user_response, assistant_response, request)


def update_turn(
    session: Session,
    user_id: UUID,
    conversation_id: UUID,
    message_id: UUID,
    settings: Settings,
    *,
    status: Literal["in_progress", "completed", "failed", "cancelled"],
    content: str | None = None,
) -> MessageResponse:
    """Atomically checkpoint or finalize; terminal states never change.

    updated_at is the lease heartbeat as in Task 5. Each update checks expiry
    before extending it. Callers enforce a separate overall generation deadline.
    """
    try:
        conversation = locked_conversation(session, user_id, conversation_id)
        saved = session.scalar(
            select(Message)
            .where(Message.id == message_id, Message.conversation_id == conversation_id)
            .execution_options(populate_existing=True)
        )
        if saved is None:
            raise ConversationError(404, "Message not found")
        if saved.role != "assistant":
            raise ConversationError(409, "Only assistant messages can be cancelled")
        now = session.scalar(select(func.clock_timestamp()))
        assert now is not None
        if saved.status == "in_progress":
            if saved.updated_at + timedelta(seconds=settings.generation_lease_seconds) <= now:
                saved.status = "failed"
            else:
                if status == "completed" and (content is None or not content.strip()):
                    raise ValueError("Completion requires nonblank text")
                saved.status = status
                if content is not None:
                    saved.content = content
            saved.updated_at = now
            conversation.updated_at = now
        session.flush()
        response = MessageResponse.model_validate(saved)
        session.commit()
        return response
    except Exception:
        session.rollback()
        raise


def send_message(
    session: Session,
    user_id: UUID,
    conversation_id: UUID,
    content: str,
    provider: GenerationProvider,
    settings: Settings,
) -> TurnResponse:
    reserved = reserve_turn(session, user_id, conversation_id, content, settings)
    request = reserved.request
    failure: ProviderError | None = None
    text = ""
    try:
        result = provider.generate(request)
        if not result.text.strip():
            raise ProviderError("Generation did not return completed text")
        text = result.text
    except ProviderError as error:
        failure = error
    except Exception:
        failure = ProviderError("Generation failed")

    assistant = update_turn(
        session,
        user_id,
        conversation_id,
        reserved.assistant_message.id,
        settings,
        status="failed" if failure else "completed",
        content="" if failure else text,
    )
    if assistant.status == "cancelled":
        raise ConversationError(409, "Generation cancelled")
    if assistant.status != ("failed" if failure else "completed") or (
        failure is None and assistant.content != text
    ):
        raise ConversationError(409, "Generation expired")
    if failure is not None:
        raise failure
    return TurnResponse(user_message=reserved.user_message, assistant_message=assistant)
