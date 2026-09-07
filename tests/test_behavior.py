import pytest
from pydantic import ValidationError

from app.behavior.profile import BehaviorProfile


def test_profile_contract() -> None:
    profile = BehaviorProfile(name=" Alice ")
    assert profile.name == "Alice"
    assert profile.warmth == 0.5
    with pytest.raises(ValidationError):
        profile.name = "Other"


@pytest.mark.parametrize("value", [-0.1, 1.1, float("nan"), float("inf"), True])
def test_invalid_personality(value: float) -> None:
    with pytest.raises(ValidationError):
        BehaviorProfile(name="Alice", warmth=value)


def test_instruction_limit() -> None:
    assert (
        len(BehaviorProfile(name="Alice", custom_instructions="界" * 10000).custom_instructions)
        == 10000
    )
    with pytest.raises(ValidationError):
        BehaviorProfile(name="Alice", custom_instructions="界" * 10001)
