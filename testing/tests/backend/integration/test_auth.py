import pytest

from app.db.models import UserStatus
from testing.tests.factories import create_user
from testing.tests.helpers import login


@pytest.mark.integration
@pytest.mark.auth
def test_login_and_refresh_success(client, db_session, seed_roles):
    create_user(db_session, username="platform_admin", password="ChangeMe123!", is_platform_admin=True, role_code="PLATFORM_ADMIN")
    access_token, refresh_token = login(client, "platform_admin", "ChangeMe123!")
    assert access_token
    assert refresh_token

    res = client.post("/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert res.status_code == 200
    data = res.json()
    assert data["access_token"] != access_token
    assert data["refresh_token"]


@pytest.mark.integration
@pytest.mark.auth
def test_login_invalid_credentials(client, db_session, seed_roles):
    create_user(db_session, username="platform_admin", password="ChangeMe123!", is_platform_admin=True, role_code="PLATFORM_ADMIN")
    res = client.post("/v1/auth/login", json={"username_or_email": "platform_admin", "password": "bad"})
    assert res.status_code == 401


@pytest.mark.integration
@pytest.mark.auth
def test_login_inactive_user(client, db_session, seed_roles):
    create_user(
        db_session,
        username="inactive",
        password="ChangeMe123!",
        is_platform_admin=True,
        role_code="PLATFORM_ADMIN",
        status=UserStatus.INACTIVE,
    )
    res = client.post("/v1/auth/login", json={"username_or_email": "inactive", "password": "ChangeMe123!"})
    assert res.status_code == 401


@pytest.mark.integration
@pytest.mark.auth
def test_refresh_invalid_token(client):
    res = client.post("/v1/auth/refresh", json={"refresh_token": "not-a-token"})
    assert res.status_code == 401
