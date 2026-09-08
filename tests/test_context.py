from collections.abc import Iterator

import pytest

from app.models import AssistantProfile
from app.providers import InputMessage
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


@pytest.mark.parametrize("allowance,expected_turns", [(6, 0), (7, 0), (8, 1), (10, 2)])
def test_injectable_counter_exact_whole_turn_boundaries(
    allowance: int, expected_turns: int
) -> None:
    class FixedCounter:
        name = "fixed-test"
        request_overhead_tokens = 3

        def count_message(self, message: InputMessage) -> int:
            return 1

    history = [
        HistoryMessage(i, "assistant" if i % 2 == 0 else "user", str(i), "completed")
        for i in range(4, 0, -1)
    ]
    request = build_context(
        profile(), history, "Next", "model", ContextBudget(allowance + 2, 1, 1), FixedCounter()
    )
    assert len(request.messages) == 3 + expected_turns * 2
    assert request.context is not None
    assert request.context.estimated_input_tokens == 6 + expected_turns * 2


@pytest.mark.parametrize("status", ["failed", "in_progress", "cancelled"])
def test_ineligible_and_orphaned_messages_do_not_enter_context(status: str) -> None:
    history = [
        HistoryMessage(9, "user", "orphan newest", "completed"),
        HistoryMessage(8, "assistant", "excluded answer", status),
        HistoryMessage(7, "user", "excluded question", "completed"),
        HistoryMessage(6, "assistant", "nonadjacent answer", "completed"),
        HistoryMessage(4, "user", "nonadjacent question", "completed"),
        HistoryMessage(2, "assistant", "good answer", "completed"),
        HistoryMessage(1, "user", "good question", "completed"),
    ]
    request = build_context(profile(), history, "Next", "model", BUDGET)
    assert [m.content for m in request.messages[2:]] == ["good question", "good answer", "Next"]


def test_mandatory_overflow_does_not_read_history() -> None:
    def unreadable() -> Iterator[HistoryMessage]:
        raise AssertionError("History should not be fetched for rejected input")
        yield

    with pytest.raises(ContextOverflow):
        build_context(profile(), unreadable(), "Next", "model", ContextBudget(3, 1, 1))


def test_multilingual_selection_matches_brute_force_suffixes() -> None:
    from random import Random

    rng = Random(7)
    for _ in range(30):
        pairs = [
            (
                InputMessage(
                    "user", rng.choice(["hello", "你好", "🙂", "e\u0301"]) * rng.randrange(1, 40)
                ),
                InputMessage("assistant", "answer " * rng.randrange(1, 40)),
            )
            for _ in range(8)
        ]
        history = [
            HistoryMessage(i + 1, message.role, message.content, "completed")
            for i, message in enumerate(message for pair in pairs for message in pair)
        ]
        mandatory = build_context(profile(), [], "Next", "model", BUDGET).messages
        allowance = count_tokens(mandatory, DEFAULT_TOKEN_COUNTER) + rng.randrange(0, 2000)
        candidates = [
            (*mandatory[:2], *(m for pair in pairs[len(pairs) - n :] for m in pair), mandatory[-1])
            for n in range(len(pairs) + 1)
        ]
        expected = max(
            (c for c in candidates if count_tokens(c, DEFAULT_TOKEN_COUNTER) <= allowance),
            key=len,
        )
        request = build_context(
            profile(), reversed(history), "Next", "model", ContextBudget(allowance + 2, 1, 1)
        )
        assert request.messages == expected
