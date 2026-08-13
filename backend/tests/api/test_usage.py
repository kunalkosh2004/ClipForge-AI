import os

import httpx
import pytest

BASE_URL = os.getenv("CLIPFORGE_API_URL", "http://localhost:8000")


@pytest.fixture
def client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=10.0)


def _login(client: httpx.Client) -> dict[str, str]:
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "demo@clipforge.ai", "password": "demo1234"},
    )
    assert r.status_code == 200, f"login failed: {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_get_ai_usage(client: httpx.Client) -> None:
    headers = _login(client)
    r = client.get("/api/v1/ai/usage", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "tokens_used" in body
    assert "tokens_remaining" in body
    assert "requests" in body
    assert "keys" in body
    assert body["token_limit"] >= body["tokens_used"]
    assert body["request_limit"] >= body["requests"]


def test_get_ai_usage_requires_auth(client: httpx.Client) -> None:
    r = client.get("/api/v1/ai/usage")
    assert r.status_code == 401
