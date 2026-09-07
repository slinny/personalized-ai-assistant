import pytest
from pydantic import ValidationError

from app.evaluation.schema import Case, Check, Suite


def sample_case() -> Case:
    return Case.model_validate(
        {
            "id": "identity",
            "version": 1,
            "category": "identity",
            "profile": {"name": "Ada"},
            "turns": [{"content": "Who are you?", "rubric": "Uses configured name."}],
        }
    )


def test_schema_rejects_duplicates_and_invalid_checks() -> None:
    case = sample_case()
    with pytest.raises(ValidationError):
        Suite(version=1, cases=[case, case])
    with pytest.raises(ValidationError):
        Check(kind="max_words", value="zero")
    with pytest.raises(ValidationError):
        Case.model_validate({**case.model_dump(), "turns": []})


def test_runner_history_errors_and_repetition_isolation() -> None:
    from app.evaluation.runner import run_cases
    from app.evaluation.schema import Turn
    from app.providers import GenerationResult, ProviderTimeout
    from app.providers.fake import FakeProvider

    case = sample_case()
    case.turns.append(Turn(content="And now?", rubric="Still uses name."))
    provider = FakeProvider(
        GenerationResult("Ada"),
        ProviderTimeout("secret"),
        GenerationResult("Ada"),
        GenerationResult("Still Ada"),
    )
    results = run_cases([case], provider, "test-model", repeats=2)
    assert results[0].turns[1].error == "ProviderTimeout"
    assert provider.requests[1].messages[-2].content == "Ada"
    assert len(provider.requests[2].messages) == 3
    assert results[1].turns[1].response == "Still Ada"
