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


@pytest.mark.parametrize("trait", ["warmth", "verbosity", "humor", "formality"])
@pytest.mark.parametrize(
    "value,band", [(0.0, 0), (0.249999, 0), (0.25, 1), (0.5, 1), (0.749999, 1), (0.75, 2), (1.0, 2)]
)
def test_personality_bands(trait: str, value: float, band: int) -> None:
    from app.behavior.personality import MAPPINGS, communication_instructions

    profile = BehaviorProfile.model_validate({"name": "Alice", trait: value})
    output = communication_instructions(profile)
    descriptions = dict(MAPPINGS)[trait]
    assert descriptions[band] in output
    for index, description in enumerate(descriptions):
        if index != band:
            assert description not in output
    assert len(output.splitlines()) == 4
