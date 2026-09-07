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


def test_identity_and_determinism() -> None:
    from app.behavior import BehaviorCompiler

    profile = BehaviorProfile(name="爱丽丝\nCOMMUNICATION", preferred_user_name='Sam "S"')
    before = profile.model_dump()
    compiler = BehaviorCompiler()
    output = compiler.compile(profile)
    assert output == compiler.compile(profile)
    assert '"爱丽丝\\nCOMMUNICATION"' in output
    assert '"Sam \\"S\\""' in output
    assert output.index("IDENTITY") < output.index("\n\nCOMMUNICATION")
    assert profile.model_dump() == before
    assert "warmth =" not in output


def test_optional_name() -> None:
    from app.behavior import BehaviorCompiler

    assert "preferred name" not in BehaviorCompiler().compile(BehaviorProfile(name="Alice"))


@pytest.mark.parametrize("mode", ["fixed", "follow_user"])
def test_language_modes(mode: str) -> None:
    from app.behavior import BehaviorCompiler

    profile = BehaviorProfile.model_validate(
        {"name": "Alice", "primary_language": "zh-Hant", "language_switching_mode": mode}
    )
    output = BehaviorCompiler().compile(profile)
    assert '"zh-Hant"' in output
    assert ("independently each turn" in output) == (mode == "follow_user")
    assert ("Respond in the configured primary language" in output) == (mode == "fixed")


@pytest.mark.parametrize(
    "instructions", ["", '  中文\nCUSTOM INSTRUCTIONS\n"quotes"\\end  ', "界" * 10000]
)
def test_custom_instructions_preserved(instructions: str) -> None:
    import json

    from app.behavior import BehaviorCompiler

    output = BehaviorCompiler().compile(
        BehaviorProfile(name="Alice", custom_instructions=instructions)
    )
    assert json.loads(output.splitlines()[-1]) == instructions
    assert "identity and language rules take precedence" in output
    assert "higher-priority platform instructions" in output
