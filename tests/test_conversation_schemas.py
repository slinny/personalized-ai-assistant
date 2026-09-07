import pytest
from pydantic import ValidationError

from app.schemas.conversation import MessageCreate


@pytest.mark.parametrize("content", ["", " \n", "x" * 20001, None, 42])
def test_invalid_content(content: object) -> None:
    with pytest.raises(ValidationError):
        MessageCreate.model_validate({"content": content})


def test_content_preserved_and_server_fields_rejected() -> None:
    assert MessageCreate(content=" hello\n").content == " hello\n"
    assert len(MessageCreate(content="x" * 20000).content) == 20000
    with pytest.raises(ValidationError):
        MessageCreate.model_validate({"content": "hi", "role": "assistant"})
