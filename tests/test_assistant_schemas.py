from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.assistant import AssistantPatch


@pytest.mark.parametrize(
    "payload",
    [
        {"name": " "},
        {"name": "x" * 101},
        {"warmth": -0.1},
        {"warmth": 1.1},
        {"warmth": float("nan")},
        {"warmth": float("inf")},
        {"warmth": True},
        {"warmth": "0.5"},
        {"name": None},
        {"holiday_preferences": None},
        {"holiday_preferences": {" ": "hi"}},
        {"holiday_preferences": {"x": True}},
        {"holiday_preferences": {"x": "a" * 1001}},
        {"holiday_preferences": {str(i): "" for i in range(101)}},
        {"user_id": "x"},
        {"morning_greeting_enabled": "true"},
        {"language_switching_mode": "other"},
        {"custom_instructions": "x" * 10001},
    ],
)
def test_invalid_patch(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        AssistantPatch.model_validate(payload)


def test_partial_and_boundary_values() -> None:
    assert AssistantPatch().model_dump(exclude_unset=True) == {}
    patch = AssistantPatch.model_validate(
        {
            "name": " Alice ",
            "warmth": 0,
            "humor": 1,
            "preferred_model": None,
            "custom_instructions": "x" * 10000,
            "holiday_preferences": {},
        }
    )
    assert patch.name == "Alice"
    values = patch.model_dump(exclude_unset=True)
    assert values["preferred_model"] is None
    assert "verbosity" not in values
