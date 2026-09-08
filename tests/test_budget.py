import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.providers import ProviderUnavailable
from app.services.budget import ContextBudget, resolve_budget


def test_input_allocation_reserves_output_and_margin() -> None:
    assert ContextBudget(8192, 2048, 1024).input_tokens == 5120


@pytest.mark.parametrize("values", [(0, 1, 1), (100, 0, 1), (100, 1, 0), (100, 90, 10)])
def test_invalid_allocation(values: tuple[int, int, int]) -> None:
    with pytest.raises(ValueError):
        ContextBudget(*values)


def test_explicit_model_budgets_and_output_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "CONTEXT_MODEL_BUDGETS",
        '{"small":{"context_window_tokens":8192},'
        '"large":{"context_window_tokens":32768,"max_output_tokens":4096}}',
    )
    settings = Settings(openai_max_output_tokens=1024)
    assert resolve_budget("small", settings) == ContextBudget(8192, 1024, 1024)
    assert resolve_budget("large", settings) == ContextBudget(32768, 4096, 1024)
    for model in (None, "unknown", "small-new-version"):
        with pytest.raises(ProviderUnavailable):
            resolve_budget(model, settings)


@pytest.mark.parametrize(
    "entry",
    [
        {"context_window_tokens": 0},
        {"context_window_tokens": True},
        {"context_window_tokens": "8192"},
        {"context_window_tokens": 3072},
        {"context_window_tokens": 8192, "safety_margin_tokens": 0},
        {"context_window_tokens": 8192, "max_output_tokens": 16001},
        {"context_window_tokens": 8192, "typo": 1},
    ],
)
def test_invalid_model_budgets(entry: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"context_model_budgets": {"model": entry}})


@pytest.mark.parametrize("name", ["", " ", " model", "model ", "x" * 201])
def test_invalid_model_names(name: str) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"context_model_budgets": {name: {"context_window_tokens": 8192}}})


@pytest.mark.parametrize("limit", [0, 1, 100001])
def test_invalid_history_scan_limits(limit: int) -> None:
    with pytest.raises(ValidationError):
        Settings(context_history_scan_limit=limit)


def test_global_output_override_must_fit_every_model() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(
            {
                "openai_max_output_tokens": 8192,
                "context_model_budgets": {"model": {"context_window_tokens": 8192}},
            }
        )
