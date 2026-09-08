from fastapi.testclient import TestClient

from app.main import create_app


def test_browser_client_assets_and_api_auth() -> None:
    with TestClient(create_app()) as client:
        page = client.get("/test-client")
        assert page.status_code == 200
        assert "Assistant playground" in page.text
        for asset, mime in [
            ("client.mjs", "javascript"),
            ("stream-client.mjs", "javascript"),
            ("style.css", "text/css"),
        ]:
            response = client.get(f"/test-client/{asset}")
            assert response.status_code == 200
            assert mime in response.headers["content-type"]
        assert client.get("/test-client/missing.js").status_code == 404
        assert client.get("/assistant").status_code in (401, 503)
