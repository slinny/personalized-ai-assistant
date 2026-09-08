"""Deterministic test provider, selected only through dependency overrides."""

from collections import deque
from collections.abc import AsyncIterator
from threading import Lock

from app.providers import (
    GenerationRequest,
    GenerationResult,
    ProviderError,
    StreamCompleted,
    TextDelta,
)


class FakeProvider:
    def __init__(self, *outcomes: GenerationResult | ProviderError) -> None:
        self.requests: list[GenerationRequest] = []
        self._outcomes = deque(outcomes)
        self._lock = Lock()

    def generate(self, request: GenerationRequest) -> GenerationResult:
        with self._lock:
            self.requests.append(request)
            if not self._outcomes:
                raise AssertionError("Fake provider has no remaining scripted outcomes")
            outcome = self._outcomes.popleft()
        if isinstance(outcome, ProviderError):
            raise outcome
        return outcome


class FakeStreamingProvider:
    def __init__(self, *events: TextDelta | StreamCompleted | Exception) -> None:
        self.events = events
        self.requests: list[GenerationRequest] = []
        self.closed = False

    async def stream(
        self, request: GenerationRequest
    ) -> AsyncIterator[TextDelta | StreamCompleted]:
        self.requests.append(request)
        try:
            for event in self.events:
                if isinstance(event, Exception):
                    raise event
                yield event
        finally:
            self.closed = True
