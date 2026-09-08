import argparse
import hashlib
from dataclasses import asdict
from pathlib import Path

from openai import OpenAI

from app.core.config import Settings
from app.evaluation.report import write_report
from app.evaluation.runner import run_cases
from app.evaluation.schema import load_suite
from app.providers import GenerationResult, ProviderUnavailable
from app.providers.fake import FakeProvider
from app.providers.openai import OpenAIProvider
from app.services.budget import ContextBudget, resolve_budget


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Explicit live or offline behavior evaluation")
    parser.add_argument("--suite", type=Path, default=Path("evaluations/initial.json"))
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--category", action="append", default=[])
    parser.add_argument("--model")
    parser.add_argument("--repeats", type=int, choices=range(1, 11), default=1)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    suite = load_suite(args.suite)
    if set(args.case) - {case.id for case in suite.cases}:
        parser.error("Unknown case ID")
    if set(args.category) - {case.category for case in suite.cases}:
        parser.error("Unknown category")
    cases = [
        case
        for case in suite.cases
        if (not args.case or case.id in args.case)
        and (not args.category or case.category in args.category)
    ]
    if not cases:
        parser.error("No cases selected")
    if args.output.exists():
        parser.error("Output directory already exists; choose a new run directory")
    settings = Settings() if args.live else None
    model = args.model or (settings.openai_model if settings else "offline-fake")
    if not model or not model.strip():
        parser.error("A nonblank model is required")
    try:
        budget = resolve_budget(model, settings) if settings else ContextBudget(32768, 2048, 1024)
    except ProviderUnavailable:
        parser.error("Live execution requires a CONTEXT_MODEL_BUDGETS entry for the selected model")
    metadata = {
        "mode": "live" if args.live else "offline-fake",
        "model": model,
        "suite_version": suite.version,
        "suite_sha256": hashlib.sha256(args.suite.read_bytes()).hexdigest(),
        "repeats": args.repeats,
        "compare": args.compare,
        "context_budget": asdict(budget),
    }
    if settings:
        if settings.openai_api_key is None:
            parser.error("Live execution requires OPENAI_API_KEY")
        metadata.update(
            timeout_seconds=settings.openai_timeout_seconds,
            max_output_tokens=budget.max_output_tokens,
            retries=0,
        )
        with OpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=settings.openai_timeout_seconds,
            max_retries=0,
        ) as client:
            results = run_cases(
                cases,
                OpenAIProvider(client),
                model,
                args.repeats,
                args.compare,
                budget=budget,
            )
    else:
        count = sum(len(case.turns) for case in cases) * args.repeats * (2 if args.compare else 1)
        provider = FakeProvider(
            *(GenerationResult("OFFLINE FAKE: no model behavior measured.") for _ in range(count))
        )
        results = run_cases(cases, provider, model, args.repeats, args.compare, budget=budget)
    report = write_report(results, args.output, metadata)
    print(f"{metadata['mode']}: {report['counts']}; report: {args.output / 'report.md'}")
    if report["counts"]["error"]:
        return 2
    return 1 if report["counts"]["fail"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
