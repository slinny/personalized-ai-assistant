import httpx
import pytest


@pytest.fixture(autouse=True)
def forbid_live_http(monkeypatch: pytest.MonkeyPatch) -> None:
    """PostgreSQL is real; HTTP providers must use fakes or explicit mock transports."""

    def blocked(*args: object, **kwargs: object) -> httpx.Response:
        raise AssertionError("Live HTTP is forbidden in automated tests")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)

    async def async_blocked(*args: object, **kwargs: object) -> httpx.Response:
        raise AssertionError("Live async HTTP is forbidden in automated tests")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", async_blocked)
