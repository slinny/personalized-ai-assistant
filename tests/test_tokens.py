import pytest

from app.providers import InputMessage
from app.services.tokens import Utf8TokenCounter, count_tokens


@pytest.mark.parametrize(
    "text,byte_count",
    [("", 0), ("hello", 5), ("你好", 6), ("🙂", 4), ("e\u0301", 3), ("\n\t ", 3)],
)
def test_multilingual_text_and_framing(text: str, byte_count: int) -> None:
    counter = Utf8TokenCounter()
    assert counter.count_message(InputMessage("user", text)) == byte_count + 20


def test_roles_empty_messages_and_request_overhead_are_counted() -> None:
    counter = Utf8TokenCounter()
    assert count_tokens([], counter) == 16
    assert count_tokens([InputMessage("system", ""), InputMessage("user", "a")], counter) == 59


def test_special_looking_text_is_plain_content() -> None:
    text = "<|endoftext|>"
    assert Utf8TokenCounter().count_message(InputMessage("user", text)) == 20 + len(text)
