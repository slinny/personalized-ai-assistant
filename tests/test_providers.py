import pytest

from app.providers import GenerationRequest, GenerationResult, InputMessage, ProviderTimeout
from app.providers.fake import FakeProvider


def test_fake_records_requests_and_scripted_outcomes() -> None:
    request = GenerationRequest("test-model", (InputMessage("user", "hello"),), 2048)
    fake = FakeProvider(GenerationResult("hello back"), ProviderTimeout())
    assert fake.generate(request).text == "hello back"
    with pytest.raises(ProviderTimeout):
        fake.generate(request)
    assert fake.requests == [request, request]
    with pytest.raises(AssertionError, match="no remaining"):
        fake.generate(request)
