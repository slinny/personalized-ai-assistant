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
    max_output_tokens: int

    def __post_init__(self) -> None:
        if type(self.max_output_tokens) is not int or self.max_output_tokens <= 0:
            raise ValueError("Output allowance must be a positive integer")


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
