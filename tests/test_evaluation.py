from pathlib import Path

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


def test_initial_suite() -> None:
    from pathlib import Path

    from app.evaluation.schema import load_suite

    suite = load_suite(Path("evaluations/initial.json"))
    assert len(suite.cases) == 18
    assert {case.category for case in suite.cases} == {
        "identity",
        "personality",
        "language",
        "custom",
        "precedence",
        "consistency",
    }


def test_report_distinguishes_fail_error_and_pending(tmp_path: "Path") -> None:
    import json

    from app.evaluation.report import write_report
    from app.evaluation.runner import run_cases
    from app.providers import GenerationResult, ProviderError
    from app.providers.fake import FakeProvider

    case = sample_case()
    case.turns[0].checks = [Check(kind="contains", value="Ada")]
    results = run_cases(
        [case],
        FakeProvider(
            GenerationResult("Bob"), ProviderError("do not expose"), GenerationResult("Ada")
        ),
        "test",
        repeats=3,
    )
    report = write_report(results, tmp_path, {"mode": "offline"})
    assert report["counts"] == {"error": 1, "fail": 1, "pending_review": 1}
    raw = (tmp_path / "results.json").read_text()
    assert "do not expose" not in raw
    assert json.loads(raw)["results"][0]["turns"][0]["request"][1]["role"] == "developer"


def test_comparison_isolates_arms_and_preserves_model() -> None:
    from app.evaluation.runner import run_cases
    from app.providers import GenerationResult
    from app.providers.fake import FakeProvider

    provider = FakeProvider(GenerationResult("Ada"), GenerationResult("Assistant"))
    results = run_cases([sample_case()], provider, "same-model", compare=True)
    assert [result.arm for result in results] == ["customized", "default"]
    assert all(request.model == "same-model" for request in provider.requests)
    assert all(len(request.messages) == 3 for request in provider.requests)
    assert '"Ada"' in provider.requests[0].messages[1].content
    assert '"Assistant"' in provider.requests[1].messages[1].content


def test_cli_offline_and_invalid_selection(tmp_path: Path) -> None:
    import json

    from app.evaluation.__main__ import main

    output = tmp_path / "run"
    assert main(["--output", str(output), "--compare"]) == 1
    report = json.loads((output / "results.json").read_text())
    assert len(report["results"]) == 36
    assert report["metadata"]["mode"] == "offline-fake"
    assert report["counts"]["error"] == 0
    with pytest.raises(SystemExit):
        main(["--output", str(tmp_path / "invalid"), "--case", "missing"])
    assert not (tmp_path / "invalid").exists()
    with pytest.raises(SystemExit):
        main(["--output", str(output)])


@pytest.mark.parametrize(
    "kind,value,response,expected",
    [
        ("contains", "Ada", "ADA here", True),
        ("not_contains", "Bob", "Bob here", False),
        ("max_words", "2", "one two three", False),
        ("max_words", "2", "one two", True),
    ],
)
def test_objective_checks(kind: str, value: str, response: str, expected: bool) -> None:
    from app.evaluation.report import check_response

    assert (
        check_response(Check.model_validate({"kind": kind, "value": value}), response) is expected
    )


def test_empty_response_stops_case() -> None:
    from app.evaluation.runner import run_cases
    from app.evaluation.schema import Turn
    from app.providers import GenerationResult
    from app.providers.fake import FakeProvider

    case = sample_case()
    case.turns.append(Turn(content="Next", rubric="Answer"))
    provider = FakeProvider(GenerationResult(" "))
    result = run_cases([case], provider, "test")[0]
    assert len(result.turns) == len(provider.requests) == 1
    assert result.turns[0].error == "ProviderError"
