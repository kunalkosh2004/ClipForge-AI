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


def test_health(client: httpx.Client) -> None:
    r = client.get("/api/v1/health")
    assert r.status_code in (200, 404)


def test_openapi_spec(client: httpx.Client) -> None:
    r = client.get("/api/v1/openapi.json")
    assert r.status_code == 200
    spec = r.json()
    assert "openapi" in spec
    assert "/api/v1/auth/register" in spec["paths"]
    assert "/api/v1/auth/login" in spec["paths"]
    assert "/api/v1/projects" in spec["paths"]


def test_register_and_login(client: httpx.Client) -> None:
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": "integration@test.com", "password": "testpass123"},
    )
    assert reg.status_code in (201, 409)

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "integration@test.com", "password": "testpass123"},
    )
    assert login.status_code == 200
    tokens = login.json()
    assert "access_token" in tokens
    assert tokens["token_type"] == "bearer"


def test_me_requires_auth(client: httpx.Client) -> None:
    r = client.get("/api/v1/auth/me")
    assert r.status_code in (401, 403)


def test_me_with_token(client: httpx.Client) -> None:
    headers = _login(client)
    r = client.get("/api/v1/auth/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["email"] == "demo@clipforge.ai"


def test_projects_list_requires_auth(client: httpx.Client) -> None:
    r = client.get("/api/v1/projects")
    assert r.status_code in (401, 403)


def test_create_and_list_projects(client: httpx.Client) -> None:
    headers = _login(client)
    r = client.post(
        "/api/v1/projects",
        json={"name": "Test Project"},
        headers=headers,
    )
    assert r.status_code == 201
    pid = r.json()["id"]

    r = client.get("/api/v1/projects", headers=headers)
    assert r.status_code == 200
    assert any(p["id"] == pid for p in r.json()["items"])


def test_delete_project(client: httpx.Client) -> None:
    headers = _login(client)
    r = client.post(
        "/api/v1/projects",
        json={"name": "To Delete"},
        headers=headers,
    )
    assert r.status_code == 201
    pid = r.json()["id"]
    r = client.delete(f"/api/v1/projects/{pid}", headers=headers)
    assert r.status_code == 204
