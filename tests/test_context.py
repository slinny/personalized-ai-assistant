from collections.abc import Iterator

import pytest

from app.models import AssistantProfile
from app.services.budget import ContextBudget, ContextOverflow
from app.services.context import HistoryMessage, build_context
from app.services.tokens import DEFAULT_TOKEN_COUNTER, count_tokens

BUDGET = ContextBudget(32768, 2048, 1024)


def profile() -> AssistantProfile:
    return AssistantProfile(
        name="Ada",
        preferred_user_name=None,
        warmth=0.5,
        verbosity=0.5,
        humor=0.5,
        formality=0.5,
        primary_language="en",
        language_switching_mode="follow_user",
        custom_instructions="Be kind",
        preferred_model=None,
    )


def test_context_order_priority_and_failed_turns() -> None:
    history = [
        HistoryMessage(4, "assistant", "", "failed"),
        HistoryMessage(2, "assistant", "Answer", "completed"),
        HistoryMessage(1, "user", "Question", "completed"),
        HistoryMessage(3, "user", "Failed question", "completed"),
    ]
    request = build_context(
        profile(),
        sorted(history, key=lambda m: m.position, reverse=True),
        "Next",
        "fallback",
        BUDGET,
    )
    assert request.model == "fallback"
    assert [m.role for m in request.messages] == [
        "system",
        "developer",
        "user",
        "assistant",
        "user",
    ]
    assert "Ada" in request.messages[1].content and "Be kind" in request.messages[1].content
    assert [m.content for m in request.messages[2:]] == ["Question", "Answer", "Next"]


def test_resolved_model_and_latest_profile() -> None:
    assistant = profile()
    assistant.preferred_model = "preferred"
    assistant.name = "New name"
    request = build_context(assistant, [], "Hi", "resolved", BUDGET)
    assert request.model == "resolved"
    assert request.max_output_tokens == BUDGET.max_output_tokens
    assert "New name" in request.messages[1].content


def test_history_limits_keep_whole_recent_pairs() -> None:
    history = [
        HistoryMessage(i, "user" if i % 2 else "assistant", str(i), "completed")
        for i in range(1, 61)
    ]
    request = build_context(
        profile(), sorted(history, key=lambda m: m.position, reverse=True), "Next", "model", BUDGET
    )
    assert len(request.messages) == 63
    assert request.messages[2].content == "1"
    history[-1] = HistoryMessage(60, "assistant", "x" * BUDGET.context_window_tokens, "completed")
    assert (
        len(
            build_context(
                profile(),
                sorted(history, key=lambda m: m.position, reverse=True),
                "Next",
                "model",
                BUDGET,
            ).messages
        )
        == 3
    )


def test_exact_budget_and_mandatory_overflow() -> None:
    request = build_context(profile(), [], "Next", "model", BUDGET)
    needed = count_tokens(request.messages, DEFAULT_TOKEN_COUNTER)
    exact = ContextBudget(needed + 2, 1, 1)
    assert build_context(profile(), [], "Next", "model", exact).messages == request.messages
    with pytest.raises(ContextOverflow):
        build_context(profile(), [], "Next!", "model", exact)


def test_stop_at_first_nonfitting_pair_without_cherry_picking() -> None:
    history = [
        HistoryMessage(1, "user", "old", "completed"),
        HistoryMessage(2, "assistant", "small", "completed"),
        HistoryMessage(3, "user", "middle", "completed"),
        HistoryMessage(4, "assistant", "x" * 32768, "completed"),
        HistoryMessage(5, "user", "recent", "completed"),
        HistoryMessage(6, "assistant", "reply", "completed"),
    ]
    request = build_context(
        profile(), sorted(history, key=lambda m: m.position, reverse=True), "Next", "model", BUDGET
    )
    assert [m.content for m in request.messages[2:]] == ["recent", "reply", "Next"]


def test_history_consumption_stops_when_pair_does_not_fit() -> None:
    def history() -> Iterator[HistoryMessage]:
        yield HistoryMessage(4, "assistant", "x" * 32768, "completed")
        yield HistoryMessage(3, "user", "recent", "completed")
        raise AssertionError("Older history should not be read")

    request = build_context(profile(), history(), "Next", "model", BUDGET)
    assert len(request.messages) == 3
    assert request.context is not None
    assert request.context.scanned_messages == 2
    assert request.context.dropped_scanned_turns == 1
    assert request.context.included_turns == 0
    assert request.context.stopped_at_budget


def test_context_diagnostics_match_request_and_budget() -> None:
    history = [
        HistoryMessage(2, "assistant", "answer", "completed"),
        HistoryMessage(1, "user", "question", "completed"),
    ]
    request = build_context(profile(), history, "next", "model", BUDGET)
    diagnostics = request.context
    assert diagnostics is not None
    assert diagnostics.estimated_input_tokens == count_tokens(
        request.messages, DEFAULT_TOKEN_COUNTER
    )
    assert diagnostics.estimated_input_tokens <= diagnostics.input_budget_tokens
    assert diagnostics.scanned_messages == 2 and diagnostics.included_turns == 1
    assert diagnostics.dropped_scanned_turns == 0 and not diagnostics.stopped_at_budget
