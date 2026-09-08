"""Offline token estimation for plain-text requests; no network or tokenizer downloads."""

from collections.abc import Iterable
from typing import Protocol

from app.providers import InputMessage


class TokenCounter(Protocol):
    """Additive, nonnegative message costs with one request-level overhead."""

    @property
    def name(self) -> str: ...

    @property
    def request_overhead_tokens(self) -> int: ...

    def count_message(self, message: InputMessage) -> int: ...


class Utf8TokenCounter:
    """Count one token per UTF-8 byte, plus conservative framing allowances.

    Byte counting intentionally overestimates ordinary byte-tokenized text. The
    16-token framing allowances are estimates, not a provider serialization spec;
    a separate budget margin is still required. This supports text messages only.
    """

    name = "utf8_bytes_v1"
    request_overhead_tokens = 16

    def count_message(self, message: InputMessage) -> int:
        return 16 + len(message.role.encode("utf-8")) + len(message.content.encode("utf-8"))


DEFAULT_TOKEN_COUNTER = Utf8TokenCounter()


def count_tokens(messages: Iterable[InputMessage], counter: TokenCounter) -> int:
    return counter.request_overhead_tokens + sum(counter.count_message(m) for m in messages)
