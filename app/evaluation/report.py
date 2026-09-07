import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.evaluation.runner import CaseResult
from app.evaluation.schema import Check


def check_response(check: Check, response: str) -> bool:
    if check.kind == "max_words":
        return len(response.split()) <= int(check.value)
    present = check.value.casefold() in response.casefold()
    return present if check.kind == "contains" else not present


def write_report(
    results: list[CaseResult], directory: Path, metadata: dict[str, Any]
) -> dict[str, Any]:
    records = []
    counts = {"error": 0, "fail": 0, "pending_review": 0}
    lines = [
        "# Behavior evaluation",
        "",
        "Human review: 0 = misses, 1 = partial, 2 = meets.",
        "Review every rubric and factual quality. Objective checks alone do not prove behavior.",
    ]
    for result in results:
        record = result.model_dump()
        failed = False
        for expected, actual, serialized in zip(
            result.case.turns, result.turns, record["turns"], strict=False
        ):
            # Baseline responses are reviewed against the desired behavior, but are
            # not failed for lacking customization they were never given.
            checks = expected.checks if result.arm == "customized" else []
            serialized["checks"] = [
                {**check.model_dump(), "passed": check_response(check, actual.response)}
                for check in checks
                if actual.response is not None
            ]
            serialized["rubric"] = expected.rubric
            serialized["human_score"] = None
            failed |= any(not check["passed"] for check in serialized["checks"])
        status = (
            "error"
            if any(t.error for t in result.turns)
            else ("fail" if failed else "pending_review")
        )
        record["status"] = status
        counts[status] += 1
        records.append(record)
        lines.extend(
            [
                "",
                f"## {result.case.id} / repetition {result.repetition} / {result.arm}",
                "",
                f"Status: {status}",
            ]
        )
        for turn in record["turns"]:
            # Quote output so model-generated headings cannot masquerade as report structure.
            lines.extend(["", "Rubric: " + turn["rubric"], "", "Response:", ""])
            lines.extend("> " + line for line in (turn["response"] or turn["error"]).splitlines())
            lines.extend(
                [
                    "",
                    "Checks: " + json.dumps(turn["checks"], ensure_ascii=False),
                    "",
                    "Human score: pending",
                ]
            )
    report = {
        "report_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "metadata": metadata,
        "counts": counts,
        "results": records,
    }
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (directory / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report
