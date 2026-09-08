import logging
from dataclasses import asdict
from datetime import timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import AssistantProfile, Conversation, Message
from app.providers import GenerationProvider, ProviderError, ProviderUnavailable
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


def send_message(
    session: Session,
    user_id: UUID,
    conversation_id: UUID,
    content: str,
    provider: GenerationProvider,
    settings: Settings,
) -> TurnResponse:
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
        assistant_id = assistant.id
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
            "history_scan_limit_reached": (request.context.scanned_messages >= history_scan_limit),
        },
    )
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

    try:
        conversation = locked_conversation(session, user_id, conversation_id)
        saved = session.get(Message, assistant_id, populate_existing=True)
        assert saved is not None
        now = session.scalar(select(func.clock_timestamp()))
        assert now is not None
        if saved.status != "in_progress":
            raise ConversationError(409, "Generation expired")
        if saved.updated_at + timedelta(seconds=settings.generation_lease_seconds) <= now:
            saved.status = "failed"
            session.commit()
            raise ConversationError(409, "Generation expired")
        saved.status = "failed" if failure else "completed"
        saved.content = "" if failure else text
        saved.updated_at = now
        conversation.updated_at = now
        session.flush()
        assistant_response = MessageResponse.model_validate(saved)
        session.commit()
    except Exception:
        # If persistence is unavailable, the reservation remains recoverable by its lease.
        session.rollback()
        raise
    if failure is not None:
        raise failure
    return TurnResponse(user_message=user_response, assistant_message=assistant_response)
