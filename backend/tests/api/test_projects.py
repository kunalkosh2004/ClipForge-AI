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


def test_create_project(client: httpx.Client) -> None:
    headers = _login(client)
    r = client.post(
        "/api/v1/projects",
        json={"name": "Integration Test Project"},
        headers=headers,
    )
    assert r.status_code == 201
    assert r.json()["name"] == "Integration Test Project"


def test_list_projects(client: httpx.Client) -> None:
    headers = _login(client)
    r = client.get("/api/v1/projects", headers=headers)
    assert r.status_code == 200
    assert isinstance(r.json()["items"], list)


def test_create_project_requires_auth(client: httpx.Client) -> None:
    r = client.post("/api/v1/projects", json={"name": "No Auth"})
    assert r.status_code in (401, 403)
