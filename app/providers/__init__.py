"""Provider-independent generation contracts."""

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class InputMessage:
    role: Literal["system", "developer", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class ContextDiagnostics:
    estimator: str
    context_window_tokens: int
    input_budget_tokens: int
    mandatory_input_tokens: int
    estimated_input_tokens: int
    reserved_output_tokens: int
    safety_margin_tokens: int
    scanned_messages: int
    included_turns: int
    dropped_scanned_turns: int
    stopped_at_budget: bool


@dataclass(frozen=True)
class GenerationRequest:
    model: str
    messages: tuple[InputMessage, ...]
    max_output_tokens: int
    context: ContextDiagnostics | None = None

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
