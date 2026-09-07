from dataclasses import asdict
from typing import Literal

from pydantic import BaseModel, Field

from app.behavior import BehaviorProfile
from app.evaluation.schema import Case
from app.models import AssistantProfile
from app.providers import GenerationProvider, ProviderError
from app.services.context import HistoryMessage, build_context


class TurnResult(BaseModel):
    request: list[dict[str, str]]
    response: str | None = None
    error: str | None = None


class CaseResult(BaseModel):
    case: Case
    profile: BehaviorProfile
    model: str
    repetition: int
    arm: Literal["customized", "default"]
    turns: list[TurnResult] = Field(default_factory=list)


def run_cases(
    cases: list[Case],
    provider: GenerationProvider,
    model: str,
    repeats: int = 1,
    compare: bool = False,
) -> list[CaseResult]:
    if not model.strip() or not 1 <= repeats <= 10:
        raise ValueError("A nonblank model and 1–10 repetitions are required")
    results: list[CaseResult] = []
    for case in cases:
        for repetition in range(1, repeats + 1):
            arms: list[Literal["customized", "default"]] = ["customized"]
            if compare:
                arms.append("default")
            for arm in arms:
                profile = case.profile if arm == "customized" else BehaviorProfile(name="Assistant")
                row = AssistantProfile(**profile.model_dump(), preferred_model=model)
                history: list[HistoryMessage] = []
                for pair in case.history:
                    history.extend(
                        [
                            HistoryMessage(len(history) + 1, "user", pair.user, "completed"),
                            HistoryMessage(
                                len(history) + 2, "assistant", pair.assistant, "completed"
                            ),
                        ]
                    )
                result = CaseResult(
                    case=case, profile=profile, model=model, repetition=repetition, arm=arm
                )
                results.append(result)
                for turn in case.turns:
                    request = build_context(row, history, turn.content, model)
                    output = TurnResult(request=[asdict(message) for message in request.messages])
                    result.turns.append(output)
                    try:
                        response = provider.generate(request).text
                        if not response.strip():
                            raise ProviderError("Empty response")
                    except ProviderError as exc:
                        output.error = type(exc).__name__
                        break
                    output.response = response
                    history.extend(
                        [
                            HistoryMessage(len(history) + 1, "user", turn.content, "completed"),
                            HistoryMessage(len(history) + 2, "assistant", response, "completed"),
                        ]
                    )
    return results
