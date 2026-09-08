import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Literal

import anyio
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from starlette.types import Message as ASGIMessage

from app.api.dependencies import get_streaming_provider
from app.main import create_app
from app.providers import GenerationRequest, GenerationResult, StreamCompleted, TextDelta
from app.providers.fake import FakeProvider, FakeStreamingProvider
from app.schemas.conversation import MessageResponse
from app.services.conversation import reserve_turn
from app.services.streaming import TurnStream
from tests.integration.test_pipeline import Environment, env  # noqa: F401


@pytest.mark.parametrize("kind", ["eof", "blank", "exception", "output_limit", "idle", "deadline"])
def test_failures_preserve_partial_and_exclude_history(env: Environment, kind: str) -> None:  # noqa: F811
    class Scripted(FakeStreamingProvider):
        async def stream(
            self, request: GenerationRequest
        ) -> AsyncIterator[TextDelta | StreamCompleted]:
            try:
                yield TextDelta(" " if kind == "blank" else "partial")
                if kind == "idle":
                    await asyncio.Event().wait()
                if kind == "deadline":
                    while True:
                        await asyncio.sleep(0.01)
                        yield TextDelta(".")
                if kind == "exception":
                    raise RuntimeError("private upstream secret")
                if kind == "output_limit":
                    yield TextDelta("x" * 100)
                if kind != "eof":
                    yield StreamCompleted()
            finally:
                self.closed = True

    provider = Scripted()
    app = create_app()
    app.state.settings.stream_idle_seconds = 0.08
    app.state.settings.stream_deadline_seconds = 0.15
    app.state.settings.stream_poll_seconds = 0.01
    app.state.settings.stream_checkpoint_seconds = 0.02
    app.state.settings.stream_max_output_bytes = 50
    app.dependency_overrides[get_streaming_provider] = lambda: provider
    with TestClient(app) as client:
        response = client.post(
            f"/conversations/{env.conversation_id}/messages/stream",
            json={"content": "Hi"},
            headers={"Authorization": "Bearer " + "a" * 32},
        )
    assert "private" not in response.text and provider.closed
    events = [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
    ]
    terminal = events[-1]
    assert terminal["event"] == "message.failed"
    assert terminal["payload"]["error_code"] == (
        "generation_timeout"
        if kind in ("idle", "deadline")
        else "output_limit"
        if kind == "output_limit"
        else "generation_failed"
    )
    saved = env.messages()[1]
    assert saved.status == "failed"
    assert saved.content == terminal["payload"]["message"]["content"]
    assert saved.content.startswith(" " if kind == "blank" else "partial")
    followup = FakeProvider(GenerationResult("new reply"))
    env.send(followup, "Next")
    assert [m.content for m in followup.requests[0].messages[2:]] == ["Next"]


def test_commit_outage_reports_unknown_and_recovers(
    env: Environment,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # noqa: F811
    original = TurnStream.save

    async def unavailable(
        self: TurnStream,
        status: Literal["in_progress", "completed", "failed", "cancelled"],
        content: str | None = None,
    ) -> MessageResponse:
        raise RuntimeError("private database outage")

    monkeypatch.setattr(TurnStream, "save", unavailable)
    provider = FakeStreamingProvider(TextDelta("unsaved"), StreamCompleted())
    app = create_app()
    app.dependency_overrides[get_streaming_provider] = lambda: provider
    with TestClient(app) as client:
        response = client.post(
            f"/conversations/{env.conversation_id}/messages/stream",
            json={"content": "Hi"},
            headers={"Authorization": "Bearer " + "a" * 32},
        )
    assert "event: stream.error" in response.text
    assert "event: message.completed" not in response.text and "private" not in response.text
    assert env.messages()[1].status == "in_progress" and provider.closed
    monkeypatch.setattr(TurnStream, "save", original)
    env.expire_active()
    env.send(FakeProvider(GenerationResult("Recovered")))
    assert env.messages()[1].status == "failed"


def test_stalled_asgi_send_is_cancelled_and_cleaned(env: Environment) -> None:  # noqa: F811
    with Session(env.engine) as session:
        turn = reserve_turn(session, env.user_id, env.conversation_id, "Hi", env.settings)
    provider = FakeStreamingProvider(*(TextDelta("chunk") for _ in range(20)))
    env.settings.stream_send_timeout_seconds = 0.05
    response = TurnStream(turn, env.user_id, lambda: Session(env.engine), provider, env.settings)

    async def send(message: ASGIMessage) -> None:
        await asyncio.Event().wait()

    async def receive() -> ASGIMessage:
        await asyncio.Event().wait()
        return {"type": "http.disconnect"}

    async def run() -> None:
        with anyio.fail_after(2):
            await response({"type": "http"}, receive, send)

    anyio.run(run)
    assert env.messages()[1].status == "cancelled"
    assert provider.closed


def test_metrics_do_not_include_content(env: Environment, caplog: pytest.LogCaptureFixture) -> None:  # noqa: F811
    app = create_app()
    app.dependency_overrides[get_streaming_provider] = lambda: FakeStreamingProvider(
        TextDelta("private reply"),
        StreamCompleted(),
    )
    with caplog.at_level(logging.INFO, logger="app.services.streaming"), TestClient(app) as client:
        client.post(
            f"/conversations/{env.conversation_id}/messages/stream",
            json={"content": "private input"},
            headers={"Authorization": "Bearer " + "a" * 32},
        )
    records = [vars(r) for r in caplog.records if r.name == "app.services.streaming"]
    assert len(records) == 1
    assert records[0]["stream_metrics"]["outcome"] == "completed"
    assert records[0]["stream_metrics"]["first_delta_seconds"] >= 0
    assert "private" not in json.dumps(records, default=str)


@pytest.mark.parametrize("expire", [False, True])
def test_lease_renewal_and_late_worker(env: Environment, expire: bool) -> None:  # noqa: F811
    class Delayed(FakeStreamingProvider):
        async def stream(
            self, request: GenerationRequest
        ) -> AsyncIterator[TextDelta | StreamCompleted]:
            yield TextDelta("partial")
            if expire:
                await anyio.to_thread.run_sync(env.expire_active)
            else:
                await asyncio.sleep(1.2)
            yield StreamCompleted()

    app = create_app()
    app.state.settings.generation_lease_seconds = 1
    app.state.settings.stream_poll_seconds = 0.05
    app.state.settings.stream_checkpoint_seconds = 0.05
    app.state.settings.stream_deadline_seconds = 3
    app.dependency_overrides[get_streaming_provider] = lambda: Delayed()
    with TestClient(app) as client:
        response = client.post(
            f"/conversations/{env.conversation_id}/messages/stream",
            json={"content": "Hi"},
            headers={"Authorization": "Bearer " + "a" * 32},
        )
    if expire:
        assert "message.failed" in response.text and "lease_expired" in response.text
        assert env.messages()[1].content == ""
    else:
        assert "message.completed" in response.text
        assert env.messages()[1].content == "partial"
