import json

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
