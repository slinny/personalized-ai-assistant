from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from openai import APIConnectionError, APITimeoutError, OpenAI
from pydantic import ValidationError

from app.core.config import Settings
from app.providers import GenerationRequest, InputMessage, ProviderError, ProviderTimeout
from app.providers.openai import OpenAIProvider


def test_nonstreaming_adapter() -> None:
    client = Mock(spec=OpenAI)
    client.responses = Mock()
    client.responses.create.return_value = SimpleNamespace(status="completed", output_text=" Hi ")
    provider = OpenAIProvider(client, max_output_tokens=256)
    result = provider.generate(GenerationRequest("chosen-model", (InputMessage("user", "Hi"),)))
    assert result.text == " Hi "
    client.responses.create.assert_called_once_with(
        model="chosen-model",
        input=[{"role": "user", "content": "Hi"}],
        stream=False,
        store=False,
        max_output_tokens=256,
    )


@pytest.mark.parametrize(
    "status,text", [("incomplete", "partial"), ("failed", ""), ("completed", " \n")]
)
def test_invalid_output(status: str, text: str) -> None:
    client = Mock(spec=OpenAI)
    client.responses = Mock()
    client.responses.create.return_value = SimpleNamespace(status=status, output_text=text)
    with pytest.raises(ProviderError):
        OpenAIProvider(client).generate(GenerationRequest("model", ()))


@pytest.mark.parametrize("timeout", [True, False])
def test_sanitized_errors(timeout: bool) -> None:
    client = Mock(spec=OpenAI)
    client.responses = Mock()
    request = httpx.Request("POST", "https://example.invalid")
    client.responses.create.side_effect = (
        APITimeoutError(request=request)
        if timeout
        else APIConnectionError(message="secret upstream diagnostic", request=request)
    )
    with pytest.raises(ProviderTimeout if timeout else ProviderError) as caught:
        OpenAIProvider(client).generate(GenerationRequest("model", ()))
    assert "secret" not in str(caught.value)


@pytest.mark.parametrize(
    "values",
    [
        {"openai_model": " "},
        {"openai_api_key": " "},
        {"openai_timeout_seconds": 0},
        {"openai_timeout_seconds": float("nan")},
        {"openai_max_output_tokens": 0},
        {"generation_lease_seconds": 20},
    ],
)
def test_invalid_settings(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(values)


def test_client_configuration_and_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    factory = Mock()
    monkeypatch.setattr("app.main.OpenAI", factory)
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key")
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "12")
    with TestClient(create_app()):
        factory.assert_called_once_with(api_key="test-only-key", timeout=12, max_retries=0)
        factory.return_value.close.assert_not_called()
    factory.return_value.close.assert_called_once()
