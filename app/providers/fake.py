"""Deterministic test provider, selected only through dependency overrides."""

from collections import deque
from threading import Lock

from app.providers import GenerationRequest, GenerationResult, ProviderError


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
