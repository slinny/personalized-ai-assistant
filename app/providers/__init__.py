"""Provider-independent generation contracts."""

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class InputMessage:
    role: Literal["system", "developer", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class GenerationRequest:
    model: str
    messages: tuple[InputMessage, ...]


@dataclass(frozen=True)
class GenerationResult:
    text: str


class ProviderError(Exception):
    """Sanitized failure safe to translate at the HTTP boundary."""


class ProviderTimeout(ProviderError):
    pass


class ProviderUnavailable(ProviderError):
    pass


class GenerationProvider(Protocol):
    def generate(self, request: GenerationRequest) -> GenerationResult: ...
