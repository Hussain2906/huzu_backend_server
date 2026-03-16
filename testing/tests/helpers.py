from __future__ import annotations

from typing import Tuple

from fastapi.testclient import TestClient


def login(client: TestClient, username: str, password: str) -> Tuple[str, str]:
    res = client.post("/v1/auth/login", json={"username_or_email": username, "password": password})
    assert res.status_code == 200, res.text
    data = res.json()
    return data["access_token"], data["refresh_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
