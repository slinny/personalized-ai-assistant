from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import timedelta
from threading import Event
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_provider
from app.core.config import ModelBudgetConfig, Settings
from app.db.provision import provision
from app.main import create_app
from app.models import AssistantProfile, Conversation, Message, User
from app.providers import GenerationRequest, GenerationResult, ProviderError, ProviderTimeout
from app.providers.fake import FakeProvider
from app.schemas.conversation import TurnResponse
from app.services.context import recent_pairs
from app.services.conversation import ConversationError, send_message
from app.services.history import iter_history


@dataclass
class Environment:
    engine: Engine
    user_id: UUID
    conversation_id: UUID
    settings: Settings

    def send(self, provider: FakeProvider, content: str = "Hi") -> TurnResponse:
        with Session(self.engine) as session:
            return send_message(
                session, self.user_id, self.conversation_id, content, provider, self.settings
            )

    def messages(self) -> list[Message]:
        with Session(self.engine) as session:
            return list(
                session.scalars(
                    select(Message)
                    .where(Message.conversation_id == self.conversation_id)
                    .order_by(Message.position)
                )
            )

    def expire_active(self) -> None:
        with Session(self.engine) as session, session.begin():
            active = session.scalar(
                select(Message).where(
                    Message.conversation_id == self.conversation_id, Message.status == "in_progress"
                )
            )
            assert active is not None
            now = session.scalar(select(func.clock_timestamp()))
            assert now is not None
            active.updated_at = now - timedelta(seconds=181)


@pytest.fixture
def env(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[Environment]:
    user_id = uuid4()
    monkeypatch.setenv("DATABASE_URL", engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("AUTH_USER_ID", str(user_id))
    monkeypatch.setenv("AUTH_TOKEN", "a" * 32)
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv(
        "CONTEXT_MODEL_BUDGETS",
        '{"test-model":{"context_window_tokens":32768},'
        '"new-model":{"context_window_tokens":16384}}',
    )
    with Session(engine) as session, session.begin():
        provision(session, user_id)
        profile = session.scalar(
            select(AssistantProfile).where(AssistantProfile.user_id == user_id)
        )
        assert profile is not None
        conversation = Conversation(user_id=user_id, assistant_profile_id=profile.id)
        session.add(conversation)
        session.flush()
        conversation_id = conversation.id
    try:
        yield Environment(engine, user_id, conversation_id, Settings())
    finally:
        with Session(engine) as session, session.begin():
            session.execute(delete(Conversation).where(Conversation.user_id == user_id))
            session.execute(delete(AssistantProfile).where(AssistantProfile.user_id == user_id))
            session.execute(delete(User).where(User.id == user_id))


def test_provider_runs_after_committed_reservation(env: Environment) -> None:
    with Session(env.engine) as session:

        class InspectingProvider(FakeProvider):
            def generate(self, request: GenerationRequest) -> GenerationResult:
                assert not session.in_transaction()
                assert [m.status for m in env.messages()] == ["completed", "in_progress"]
                return super().generate(request)

        send_message(
            session,
            env.user_id,
            env.conversation_id,
            "Hi",
            InspectingProvider(GenerationResult("Hello")),
            env.settings,
        )
    assert [m.status for m in env.messages()] == ["completed", "completed"]


def test_concurrent_turn_rejected_and_other_conversation_allowed(env: Environment) -> None:
    entered, release = Event(), Event()

    class BlockingProvider(FakeProvider):
        def generate(self, request: GenerationRequest) -> GenerationResult:
            entered.set()
            assert release.wait(10)
            return super().generate(request)

    provider = BlockingProvider(GenerationResult("First"))
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(env.send, provider)
        try:
            assert entered.wait(10)
            rejected = FakeProvider(GenerationResult("Should not run"))
            with pytest.raises(ConversationError) as caught:
                env.send(rejected)
            assert caught.value.status_code == 409
            assert rejected.requests == []
            with Session(env.engine) as session, session.begin():
                original = session.get(Conversation, env.conversation_id)
                assert original is not None
                other = Conversation(
                    user_id=env.user_id, assistant_profile_id=original.assistant_profile_id
                )
                session.add(other)
                session.flush()
                other_id = other.id
            other_env = Environment(env.engine, env.user_id, other_id, env.settings)
            assert (
                other_env.send(
                    FakeProvider(GenerationResult("Independent"))
                ).assistant_message.content
                == "Independent"
            )
        finally:
            release.set()
        assert pending.result(timeout=10).assistant_message.content == "First"
    assert [m.position for m in env.messages()] == [1, 2]


def test_recovery_prevents_late_response_overwrite(env: Environment) -> None:
    entered, release = Event(), Event()

    class BlockingProvider(FakeProvider):
        def generate(self, request: GenerationRequest) -> GenerationResult:
            entered.set()
            assert release.wait(10)
            return super().generate(request)

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(env.send, BlockingProvider(GenerationResult("Late reply")))
        try:
            assert entered.wait(10)
            env.expire_active()
            replacement = FakeProvider(GenerationResult("Fresh reply"))
            result = env.send(replacement, "New question")
            assert result.assistant_message.position == 4
            assert [m.content for m in replacement.requests[0].messages[2:]] == ["New question"]
        finally:
            release.set()
        with pytest.raises(ConversationError, match="expired"):
            pending.result(timeout=10)
    messages = env.messages()
    assert [m.status for m in messages] == ["completed", "failed", "completed", "completed"]
    assert messages[1].content == "" and messages[3].content == "Fresh reply"


def test_expired_response_without_takeover_is_failed(env: Environment) -> None:
    class ExpiringProvider(FakeProvider):
        def generate(self, request: GenerationRequest) -> GenerationResult:
            env.expire_active()
            return super().generate(request)

    with pytest.raises(ConversationError, match="expired"):
        env.send(ExpiringProvider(GenerationResult("Too late")))
    assert env.messages()[1].status == "failed"
    assert env.messages()[1].content == ""


def test_final_commit_failure_leaves_recoverable_reservation(
    env: Environment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with Session(env.engine) as session:
        commit = session.commit
        calls = 0

        def fail_final_commit() -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("Simulated database outage")
            commit()

        monkeypatch.setattr(session, "commit", fail_final_commit)
        with pytest.raises(RuntimeError, match="database outage"):
            send_message(
                session,
                env.user_id,
                env.conversation_id,
                "Hi",
                FakeProvider(GenerationResult("Unsaved")),
                env.settings,
            )
    assert env.messages()[1].status == "in_progress"
    env.expire_active()
    env.send(FakeProvider(GenerationResult("Recovered")))
    assert [m.status for m in env.messages()] == ["completed", "failed", "completed", "completed"]


@pytest.mark.parametrize(
    "outcome,status",
    [
        (ProviderTimeout("secret"), 504),
        (ProviderError("secret"), 502),
        (GenerationResult(" \n"), 502),
    ],
)
def test_http_errors_and_failed_turn_history(
    env: Environment,
    outcome: GenerationResult | ProviderError,
    status: int,
) -> None:
    app = create_app()
    fake = FakeProvider(outcome, GenerationResult("Recovered"))
    app.dependency_overrides[get_provider] = lambda: fake
    headers = {"Authorization": "Bearer " + "a" * 32}
    path = f"/conversations/{env.conversation_id}/messages"
    with TestClient(app) as client:
        response = client.post(path, headers=headers, json={"content": "Fail"})
        assert response.status_code == status
        assert "secret" not in response.text
        assert client.post(path, headers=headers, json={"content": "Retry"}).status_code == 201
    assert [m.content for m in fake.requests[1].messages[2:]] == ["Retry"]
    assert env.messages()[1].status == "failed"


def test_http_persistence_profile_changes_pagination_and_ownership(env: Environment) -> None:
    fake = FakeProvider(GenerationResult("One"), GenerationResult("Two"))
    headers = {"Authorization": "Bearer " + "a" * 32}
    path = f"/conversations/{env.conversation_id}/messages"
    app = create_app()
    app.dependency_overrides[get_provider] = lambda: fake
    with TestClient(app) as client:
        assert client.post(path, json={"content": "Hi"}).status_code == 401
        assert client.post(path, headers=headers, json={"content": " "}).status_code == 422
        assert (
            client.post(path, headers=headers, json={"content": "Hi", "role": "system"}).status_code
            == 422
        )
        assert fake.requests == []
        assert client.post(path, headers=headers, json={"content": "Hi"}).status_code == 201
        assert (
            client.patch(
                "/assistant",
                headers=headers,
                json={"name": "Changed", "preferred_model": "new-model"},
            ).status_code
            == 200
        )
    restarted = create_app()
    restarted.dependency_overrides[get_provider] = lambda: fake
    with TestClient(restarted) as client:
        assert len(client.get(path, headers=headers).json()) == 2
        assert client.post(path, headers=headers, json={"content": "Next"}).status_code == 201
        assert fake.requests[1].model == "new-model"
        assert "Changed" in fake.requests[1].messages[1].content
        assert [m.content for m in fake.requests[1].messages[2:]] == ["Hi", "One", "Next"]
        assert [
            m["position"]
            for m in client.get(path + "?after_position=2&limit=1", headers=headers).json()
        ] == [3]
        restarted.state.settings.auth_user_id = uuid4()
        assert client.get(path, headers=headers).status_code == 404
        assert client.post(path, headers=headers, json={"content": "Foreign"}).status_code == 404
        assert len(fake.requests) == 2
        assert client.get("/conversations", headers=headers).json() == []


def test_missing_model_does_not_reserve_messages(env: Environment) -> None:
    env.settings.openai_model = None
    fake = FakeProvider(GenerationResult("Should not run"))
    app = create_app()
    app.state.settings = env.settings
    app.dependency_overrides[get_provider] = lambda: fake
    with TestClient(app) as client:
        response = client.post(
            f"/conversations/{env.conversation_id}/messages",
            headers={"Authorization": "Bearer " + "a" * 32},
            json={"content": "Hi"},
        )
        assert response.status_code == 503
    assert env.messages() == [] and fake.requests == []


def test_unexpected_provider_failure_is_sanitized(env: Environment) -> None:
    class BrokenProvider(FakeProvider):
        def generate(self, request: GenerationRequest) -> GenerationResult:
            raise RuntimeError("private diagnostic")

    app = create_app()
    app.dependency_overrides[get_provider] = lambda: BrokenProvider()
    with TestClient(app) as client:
        response = client.post(
            f"/conversations/{env.conversation_id}/messages",
            headers={"Authorization": "Bearer " + "a" * 32},
            json={"content": "Hi"},
        )
        assert response.status_code == 502
        assert "private" not in response.text
    assert env.messages()[1].status == "failed"


def test_http_missing_provider_does_not_reserve(env: Environment) -> None:
    app = create_app()
    with TestClient(app) as client:
        app.state.provider = None
        response = client.post(
            f"/conversations/{env.conversation_id}/messages",
            headers={"Authorization": "Bearer " + "a" * 32},
            json={"content": "Hi"},
        )
        assert response.status_code == 503
    assert env.messages() == []


@pytest.mark.parametrize("failure", ["message", "instructions", "unknown_model"])
def test_context_rejection_is_atomic(env: Environment, failure: str) -> None:
    env.send(FakeProvider(GenerationResult("Saved reply")))
    before = [(m.id, m.content, m.status, m.updated_at) for m in env.messages()]
    with Session(env.engine) as session:
        conversation = session.get(Conversation, env.conversation_id)
        assert conversation is not None
        timestamp = conversation.updated_at
        if failure == "instructions":
            profile = session.get(AssistantProfile, conversation.assistant_profile_id)
            assert profile is not None
            profile.custom_instructions = "private instructions " * 200
            session.commit()
    env.settings.context_model_budgets = {
        "test-model": ModelBudgetConfig(
            context_window_tokens=4096, max_output_tokens=2048, safety_margin_tokens=1024
        )
    }
    if failure == "unknown_model":
        env.settings.openai_model = "unconfigured"
    app = create_app()
    app.state.settings = env.settings
    fake = FakeProvider()
    app.dependency_overrides[get_provider] = lambda: fake
    with TestClient(app) as client:
        response = client.post(
            f"/conversations/{env.conversation_id}/messages",
            headers={"Authorization": "Bearer " + "a" * 32},
            json={"content": "private input " * 200 if failure == "message" else "Hi"},
        )
    assert response.status_code == (503 if failure == "unknown_model" else 422)
    assert "private" not in response.text
    assert fake.requests == []
    assert [(m.id, m.content, m.status, m.updated_at) for m in env.messages()] == before
    with Session(env.engine) as session:
        conversation = session.get(Conversation, env.conversation_id)
        assert conversation is not None and conversation.updated_at == timestamp


def seed_history(env: Environment, count: int) -> None:
    with Session(env.engine) as session, session.begin():
        session.add_all(
            Message(
                conversation_id=env.conversation_id,
                position=position,
                role="user" if position % 2 else "assistant",
                content=f"message {position}",
                status="completed",
            )
            for position in range(1, count + 1)
        )


@pytest.mark.parametrize("scan_limit,expected_pairs", [(10000, 60), (63, 31)])
def test_history_beyond_forty_messages_and_scan_limit(
    env: Environment, scan_limit: int, expected_pairs: int
) -> None:
    seed_history(env, 120)
    before = [(m.id, m.content, m.status) for m in env.messages()]
    env.settings.context_history_scan_limit = scan_limit
    fake = FakeProvider(GenerationResult("New reply"))
    env.send(fake, "Next")
    messages = fake.requests[0].messages
    assert len(messages) == 3 + expected_pairs * 2
    assert messages[2].content == f"message {121 - expected_pairs * 2}"
    assert messages[-2].content == "message 120"
    assert messages[-1].content == "Next"
    assert [(m.id, m.content, m.status) for m in env.messages()[:120]] == before


def test_pairs_across_odd_batch_boundaries(env: Environment) -> None:
    seed_history(env, 8)
    with Session(env.engine) as session:
        history = iter_history(session, env.conversation_id, 100, batch_size=3)
        pairs = list(recent_pairs(history))
    assert [(u.content, a.content) for u, a in pairs] == [
        ("message 7", "message 8"),
        ("message 5", "message 6"),
        ("message 3", "message 4"),
        ("message 1", "message 2"),
    ]


def test_model_output_budget_is_snapshotted_before_provider_call(env: Environment) -> None:
    env.settings.context_model_budgets["test-model"] = ModelBudgetConfig(
        context_window_tokens=8192, max_output_tokens=256
    )

    class SettingsChangingProvider(FakeProvider):
        def generate(self, request: GenerationRequest) -> GenerationResult:
            env.settings.openai_max_output_tokens = 4096
            env.settings.context_model_budgets["test-model"] = ModelBudgetConfig(
                context_window_tokens=16384, max_output_tokens=512
            )
            assert request.max_output_tokens == 256
            return super().generate(request)

    env.send(SettingsChangingProvider(GenerationResult("First")))
    fake = FakeProvider(GenerationResult("Second"))
    env.send(fake)
    assert fake.requests[0].max_output_tokens == 512


def test_context_logs_counts_without_content(
    env: Environment, caplog: pytest.LogCaptureFixture
) -> None:
    import json
    import logging

    fake = FakeProvider(GenerationResult("private assistant text"))
    with caplog.at_level(logging.INFO, logger="app.services.conversation"):
        env.send(fake, "private user text")
    records = [r for r in caplog.records if r.name == "app.services.conversation"]
    assert len(records) == 1
    fields = vars(records[0])
    assert fields["context_budget"]["included_turns"] == 0
    assert fields["context_budget"]["estimated_input_tokens"] > 0
    assert not fields["history_scan_limit_reached"]
    serialized = json.dumps(fields, default=str)
    assert "private user text" not in serialized and "private assistant text" not in serialized
    assert "Be kind" not in serialized
