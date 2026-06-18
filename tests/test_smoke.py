from fastapi.testclient import TestClient

from app.main import create_app


def test_homepage_renders() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "Copa Phibra 2026" in response.text
