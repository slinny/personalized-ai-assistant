"""Immutable, per-request context allocation."""

from dataclasses import dataclass

from app.core.config import Settings
from app.providers import ProviderUnavailable


class ContextOverflow(ValueError):
    """Mandatory instructions and current input cannot fit without losing content."""


@dataclass(frozen=True)
class ContextBudget:
    context_window_tokens: int
    max_output_tokens: int
    safety_margin_tokens: int

    def __post_init__(self) -> None:
        values = (self.context_window_tokens, self.max_output_tokens, self.safety_margin_tokens)
        if any(type(value) is not int or value <= 0 for value in values):
            raise ValueError("Context budget values must be positive integers")
        if self.input_tokens <= 0:
            raise ValueError("Output reserve and safety margin must leave room for input")

    @property
    def input_tokens(self) -> int:
        return self.context_window_tokens - self.max_output_tokens - self.safety_margin_tokens


def resolve_budget(model: str | None, settings: Settings) -> ContextBudget:
    configured = settings.context_model_budgets.get(model) if model else None
    if configured is None:
        raise ProviderUnavailable("No context budget is configured for the selected model")
    return ContextBudget(
        configured.context_window_tokens,
        configured.max_output_tokens or settings.openai_max_output_tokens,
        configured.safety_margin_tokens,
    )
