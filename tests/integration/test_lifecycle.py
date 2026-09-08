from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.services.conversation import ConversationError, reserve_turn, update_turn
from tests.integration.test_pipeline import Environment, env  # noqa: F401


def test_terminal_race_is_immutable(env: Environment) -> None:  # noqa: F811
    with Session(env.engine) as session:
        turn = reserve_turn(session, env.user_id, env.conversation_id, "Hi", env.settings)

    def finish(cancel: bool) -> str:
        with Session(env.engine) as session:
            return update_turn(
                session,
                env.user_id,
                env.conversation_id,
                turn.assistant_message.id,
                env.settings,
                status="cancelled" if cancel else "completed",
                content=None if cancel else "Hello",
            ).status

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(finish, [False, True]))
    assert outcomes[0] == outcomes[1]
    assert env.messages()[1].status == outcomes[0]
    assert finish(True) == outcomes[0]


def test_checkpoint_expiry_and_ownership(env: Environment) -> None:  # noqa: F811
    with Session(env.engine) as session:
        turn = reserve_turn(session, env.user_id, env.conversation_id, "Hi", env.settings)
        partial = update_turn(
            session,
            env.user_id,
            env.conversation_id,
            turn.assistant_message.id,
            env.settings,
            status="in_progress",
            content="partial",
        )
        assert partial.content == "partial"
        with pytest.raises(ConversationError) as error:
            update_turn(
                session,
                uuid4(),
                env.conversation_id,
                turn.assistant_message.id,
                env.settings,
                status="cancelled",
            )
        assert error.value.status_code == 404
    env.expire_active()
    with Session(env.engine) as session:
        late = update_turn(
            session,
            env.user_id,
            env.conversation_id,
            turn.assistant_message.id,
            env.settings,
            status="completed",
            content="late",
        )
    assert late.status == "failed" and late.content == "partial"


def test_json_generation_cannot_overwrite_cancellation(env: Environment) -> None:  # noqa: F811
    from app.providers import GenerationRequest, GenerationResult
    from app.providers.fake import FakeProvider

    class Cancelling(FakeProvider):
        def generate(self, request: GenerationRequest) -> GenerationResult:
            message = env.messages()[1]
            with Session(env.engine) as session:
                update_turn(
                    session,
                    env.user_id,
                    env.conversation_id,
                    message.id,
                    env.settings,
                    status="cancelled",
                )
            return GenerationResult("late")

    with pytest.raises(ConversationError, match="cancelled"):
        env.send(Cancelling())
    assert env.messages()[1].status == "cancelled"
    assert env.messages()[1].content == ""


def test_expired_json_failure_still_returns_conflict(env: Environment) -> None:  # noqa: F811
    from app.providers import GenerationRequest, GenerationResult, ProviderError
    from app.providers.fake import FakeProvider

    class ExpiringFailure(FakeProvider):
        def generate(self, request: GenerationRequest) -> GenerationResult:
            env.expire_active()
            raise ProviderError("failed late")

    with pytest.raises(ConversationError, match="expired"):
        env.send(ExpiringFailure())
    assert env.messages()[1].status == "failed"
