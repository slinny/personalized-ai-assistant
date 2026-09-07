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
