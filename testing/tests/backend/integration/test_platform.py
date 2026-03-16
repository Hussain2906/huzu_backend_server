import pytest

from testing.tests.factories import Factory, create_user, create_company
from testing.tests.helpers import login, auth_headers


@pytest.mark.integration
def test_platform_endpoints_require_admin(client, db_session, seed_roles):
    res = client.get("/v1/platform/companies")
    assert res.status_code == 401

    # create company user and token
    company = create_company(db_session, name="Demo Co")
    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    access_token, _ = login(client, "owner", "Pass@1234")

    res = client.get("/v1/platform/companies", headers=auth_headers(access_token))
    assert res.status_code == 403


@pytest.mark.integration
def test_platform_create_company_and_duplicate_username(client, db_session, seed_roles, rng):
    create_user(db_session, username="platform_admin", password="ChangeMe123!", is_platform_admin=True, role_code="PLATFORM_ADMIN")
    access_token, _ = login(client, "platform_admin", "ChangeMe123!")

    factory = Factory(rng)
    payload = factory.company_payload(username="owner", password="Pass@1234")
    res = client.post("/v1/platform/companies", json=payload, headers=auth_headers(access_token))
    assert res.status_code == 200

    res = client.get("/v1/platform/companies", headers=auth_headers(access_token))
    assert res.status_code == 200
    assert len(res.json()) >= 1

    # duplicate username should fail
    payload2 = factory.company_payload(username="owner", password="Pass@1234")
    res = client.post("/v1/platform/companies", json=payload2, headers=auth_headers(access_token))
    assert res.status_code == 400
    assert res.json()["detail"] == "Username already in use"


@pytest.mark.integration
def test_platform_update_company_not_found(client, db_session, seed_roles):
    create_user(db_session, username="platform_admin", password="ChangeMe123!", is_platform_admin=True, role_code="PLATFORM_ADMIN")
    access_token, _ = login(client, "platform_admin", "ChangeMe123!")

    res = client.patch("/v1/platform/companies/does-not-exist", json={"name": "New"}, headers=auth_headers(access_token))
    assert res.status_code == 404


@pytest.mark.integration
def test_platform_admin_profile_update_requires_password(client, db_session, seed_roles):
    create_user(db_session, username="platform_admin", password="ChangeMe123!", is_platform_admin=True, role_code="PLATFORM_ADMIN")
    access_token, _ = login(client, "platform_admin", "ChangeMe123!")

    # attempt update without current password
    res = client.patch(
        "/v1/platform/admin/profile",
        json={"username": "new_admin"},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 400

    # invalid current password
    res = client.patch(
        "/v1/platform/admin/profile",
        json={"username": "new_admin", "current_password": "wrong", "new_password": "NewPass123!"},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 400

    # valid update
    res = client.patch(
        "/v1/platform/admin/profile",
        json={"username": "new_admin", "current_password": "ChangeMe123!", "new_password": "NewPass123!"},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 200
    assert res.json()["username"] == "new_admin"
