import asyncio
from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from openai import APITimeoutError, AsyncOpenAI

from app.providers import (
    GenerationRequest,
    ProviderError,
    ProviderTimeout,
    StreamCompleted,
    TextDelta,
)
from app.providers.openai import OpenAIStreamingProvider


class SDKStream:
    def __init__(self, events: list[SimpleNamespace]) -> None:
        self.events = events
        self.closed = False

    async def __aenter__(self) -> "SDKStream":
        return self

    async def __aexit__(self, *args: object) -> None:
        self.closed = True

    async def __aiter__(self) -> AsyncIterator[SimpleNamespace]:
        for event in self.events:
            yield event


def test_stream_adapter_options_and_cleanup() -> None:
    sdk = SDKStream(
        [
            SimpleNamespace(type="response.output_text.delta", delta="Hello"),
            SimpleNamespace(
                type="response.completed", response=SimpleNamespace(status="completed")
            ),
        ]
    )
    client = Mock(spec=AsyncOpenAI)
    client.responses = SimpleNamespace(create=AsyncMock(return_value=sdk))

    async def run() -> None:
        results = [
            event
            async for event in OpenAIStreamingProvider(client).stream(
                GenerationRequest("model", (), 123)
            )
        ]
        assert results == [TextDelta("Hello"), StreamCompleted()]

    asyncio.run(run())
    assert sdk.closed
    client.responses.create.assert_awaited_once_with(
        model="model",
        input=[],
        stream=True,
        store=False,
        max_output_tokens=123,
        truncation="disabled",
    )


@pytest.mark.parametrize("kind", ["eof", "response.failed", "response.incomplete", "error"])
def test_stream_failure_closes(kind: str) -> None:
    sdk = SDKStream([] if kind == "eof" else [SimpleNamespace(type=kind)])
    client = Mock(spec=AsyncOpenAI)
    client.responses = SimpleNamespace(create=AsyncMock(return_value=sdk))

    async def run() -> None:
        with pytest.raises(ProviderError):
            async for _ in OpenAIStreamingProvider(client).stream(
                GenerationRequest("model", (), 123)
            ):
                pass

    asyncio.run(run())
    assert sdk.closed


def test_stream_timeout_is_sanitized() -> None:
    client = Mock(spec=AsyncOpenAI)
    client.responses = SimpleNamespace(
        create=AsyncMock(
            side_effect=APITimeoutError(request=httpx.Request("POST", "https://example.invalid"))
        )
    )

    async def run() -> None:
        with pytest.raises(ProviderTimeout, match="Generation timed out"):
            async for _ in OpenAIStreamingProvider(client).stream(
                GenerationRequest("model", (), 123)
            ):
                pass

    asyncio.run(run())


def test_async_client_configuration_and_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    client = Mock(spec=AsyncOpenAI)
    client.close = AsyncMock()
    factory = Mock(return_value=client)
    monkeypatch.setattr("app.main.AsyncOpenAI", factory)
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key")
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "12")
    with TestClient(create_app()):
        factory.assert_called_once_with(api_key="test-only-key", timeout=12, max_retries=0)
        client.close.assert_not_awaited()
    client.close.assert_awaited_once()


def test_early_stream_close_releases_sdk_context() -> None:
    sdk = SDKStream([SimpleNamespace(type="response.output_text.delta", delta="partial")])
    client = Mock(spec=AsyncOpenAI)
    client.responses = SimpleNamespace(create=AsyncMock(return_value=sdk))

    async def run() -> None:
        from contextlib import aclosing

        iterator = OpenAIStreamingProvider(client).stream(GenerationRequest("model", (), 123))
        async with aclosing(iterator):
            assert await anext(iterator) == TextDelta("partial")

    asyncio.run(run())
    assert sdk.closed
