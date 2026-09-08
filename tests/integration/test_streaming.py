import json
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dependencies import get_streaming_provider
from app.main import create_app
from app.providers import StreamCompleted, TextDelta
from app.providers.fake import FakeStreamingProvider
from tests.integration.test_pipeline import Environment, env  # noqa: F401


def test_stream_saves_and_emits_committed_completion(env: Environment) -> None:  # noqa: F811
    app = create_app()
    provider = FakeStreamingProvider(TextDelta("Hello\n"), TextDelta("世界"), StreamCompleted())
    app.dependency_overrides[get_streaming_provider] = lambda: provider
    with TestClient(app) as client:
        response = client.post(
            f"/conversations/{env.conversation_id}/messages/stream",
            json={"content": "Hi"},
            headers={"Authorization": "Bearer " + "a" * 32},
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
    ]
    assert [e["event"] for e in events] == [
        "turn.started",
        "message.delta",
        "message.delta",
        "message.completed",
    ]
    assert [e["sequence"] for e in events] == [1, 2, 3, 4]
    assert events[-1]["payload"]["message"]["content"] == "Hello\n世界"
    assert env.messages()[1].content == "Hello\n世界"
    assert env.messages()[1].status == "completed"
    assert provider.closed


def test_stream_validation_precedes_reservation(env: Environment) -> None:  # noqa: F811
    app = create_app()
    provider = FakeStreamingProvider()
    app.dependency_overrides[get_streaming_provider] = lambda: provider
    with TestClient(app) as client:
        path = f"/conversations/{env.conversation_id}/messages/stream"
        assert client.post(path, json={"content": "Hi"}).status_code == 401
        assert (
            client.post(
                path, json={"content": " "}, headers={"Authorization": "Bearer " + "a" * 32}
            ).status_code
            == 422
        )
    assert env.messages() == [] and provider.requests == []


def test_real_http_delivers_delta_and_keepalive_before_completion(env: Environment) -> None:  # noqa: F811
    import asyncio
    from collections.abc import AsyncIterator
    from threading import Event

    from app.providers import GenerationRequest
    from tests.integration.stream_server import serve

    release = Event()

    class Gated(FakeStreamingProvider):
        async def stream(
            self, request: GenerationRequest
        ) -> AsyncIterator[TextDelta | StreamCompleted]:
            try:
                yield TextDelta("First")
                while not release.is_set():
                    await asyncio.sleep(0.01)
                yield StreamCompleted()
            finally:
                self.closed = True

    provider = Gated()
    app = create_app()
    app.state.settings.stream_heartbeat_seconds = 0.05
    app.dependency_overrides[get_streaming_provider] = lambda: provider
    try:
        with serve(app) as client:
            client.request(
                "POST",
                f"/conversations/{env.conversation_id}/messages/stream",
                json.dumps({"content": "Hi"}),
                {"Authorization": "Bearer " + "a" * 32, "Content-Type": "application/json"},
            )
            response = client.getresponse()
            assert response.status == 200
            observed = b""
            while b": keepalive" not in observed:
                line = response.readline()
                assert line
                observed += line
            assert b"message.delta" in observed and b"message.completed" not in observed
            assert env.messages()[1].status == "in_progress"
            release.set()
            assert b"message.completed" in response.read()
    finally:
        release.set()
    assert provider.closed and env.messages()[1].status == "completed"


def test_cancel_from_separate_app_stops_stalled_stream(env: Environment) -> None:  # noqa: F811
    import asyncio
    from collections.abc import AsyncIterator
    from threading import Event

    from app.providers import GenerationRequest
    from tests.integration.stream_server import serve

    closed = Event()

    class Stalled(FakeStreamingProvider):
        async def stream(
            self, request: GenerationRequest
        ) -> AsyncIterator[TextDelta | StreamCompleted]:
            try:
                yield TextDelta("provisional")
                await asyncio.Event().wait()
            finally:
                closed.set()

    app = create_app()
    app.state.settings.stream_poll_seconds = 0.02
    app.dependency_overrides[get_streaming_provider] = lambda: Stalled()
    headers = {"Authorization": "Bearer " + "a" * 32, "Content-Type": "application/json"}
    other_app = create_app()
    with serve(app) as connection, TestClient(other_app) as other_worker:
        path = f"/conversations/{env.conversation_id}/messages"
        connection.request("POST", path + "/stream", json.dumps({"content": "Hi"}), headers)
        response = connection.getresponse()
        observed = b""
        while b'"text":"provisional"' not in observed:
            observed += response.readline()
        message = env.messages()[1]
        cancel = path + f"/{message.id}/cancel"
        cancelled = other_worker.post(cancel, headers=headers)
        assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
        assert other_worker.post(cancel, headers=headers).json() == cancelled.json()
        tail = response.read()
        assert b"message.cancelled" in tail and b"message.completed" not in tail
        assert closed.wait(2)
        assert env.messages()[1].content == cancelled.json()["content"]
        assert (
            other_worker.post(path + f"/{env.messages()[0].id}/cancel", headers=headers).status_code
            == 409
        )
        other_app.state.settings.auth_user_id = uuid4()
        assert other_worker.post(cancel, headers=headers).status_code == 404


def test_real_disconnect_before_first_token_cancels(env: Environment) -> None:  # noqa: F811
    import asyncio
    from collections.abc import AsyncIterator
    from threading import Event
    from time import monotonic, sleep

    from app.providers import GenerationRequest
    from tests.integration.stream_server import serve

    entered, closed = Event(), Event()

    class Silent(FakeStreamingProvider):
        async def stream(
            self, request: GenerationRequest
        ) -> AsyncIterator[TextDelta | StreamCompleted]:
            try:
                entered.set()
                await asyncio.Event().wait()
                yield StreamCompleted()
            finally:
                closed.set()

    app = create_app()
    app.dependency_overrides[get_streaming_provider] = lambda: Silent()
    with serve(app) as connection:
        connection.request(
            "POST",
            f"/conversations/{env.conversation_id}/messages/stream",
            json.dumps({"content": "Hi"}),
            {"Authorization": "Bearer " + "a" * 32, "Content-Type": "application/json"},
        )
        response = connection.getresponse()
        assert response.status == 200 and entered.wait(2)
        response.close()
        connection.close()
        assert closed.wait(2)
        deadline = monotonic() + 2
        while env.messages()[1].status == "in_progress" and monotonic() < deadline:
            sleep(0.01)
        assert env.messages()[1].status == "cancelled"
