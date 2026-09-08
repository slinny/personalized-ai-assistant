import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.streaming import Delta, StreamEvent


def test_sse_serialization_does_not_inject_frames() -> None:
    text = 'hello\n\nevent: fake\r\ndata: "世界" 🦊'
    event = StreamEvent(
        event="message.delta", message_id=uuid4(), sequence=1, payload=Delta(text=text)
    )
    frame = event.encode().decode()
    assert frame.count("\n\n") == 1
    assert json.loads(frame.split("data: ", 1)[1])["payload"]["text"] == text


@pytest.mark.parametrize(
    "values",
    [
        {"stream_poll_seconds": 0},
        {"stream_idle_seconds": float("inf")},
        {"stream_max_output_bytes": 0},
        {"generation_lease_seconds": 31, "stream_checkpoint_seconds": 11},
    ],
)
def test_stream_limits(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(values)
