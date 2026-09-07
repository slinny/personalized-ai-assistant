import pytest

from app.models import AssistantProfile
from app.providers import ProviderUnavailable
from app.services.context import MAX_CONTEXT_CHARACTERS, HistoryMessage, build_context


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
    request = build_context(profile(), history, "Next", "fallback")
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


def test_model_selection_and_latest_profile() -> None:
    assistant = profile()
    with pytest.raises(ProviderUnavailable):
        build_context(assistant, [], "Hi", None)
    assistant.preferred_model = "preferred"
    assistant.name = "New name"
    request = build_context(assistant, [], "Hi", "fallback")
    assert request.model == "preferred"
    assert "New name" in request.messages[1].content


def test_history_limits_keep_whole_recent_pairs() -> None:
    history = [
        HistoryMessage(i, "user" if i % 2 else "assistant", str(i), "completed")
        for i in range(1, 61)
    ]
    request = build_context(profile(), history, "Next", "model")
    assert len(request.messages) == 43
    assert request.messages[2].content == "21"
    history[-1] = HistoryMessage(60, "assistant", "x" * MAX_CONTEXT_CHARACTERS, "completed")
    assert len(build_context(profile(), history, "Next", "model").messages) == 3
