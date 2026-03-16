import pytest

from app.db.models import UserStatus
from testing.tests.factories import create_company, create_user
from testing.tests.helpers import login, auth_headers


@pytest.mark.integration
def test_company_profile_get_update(client, db_session, seed_roles):
    company = create_company(db_session, name="Acme Co", seat_limit=5)
    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    access_token, _ = login(client, "owner", "Pass@1234")

    res = client.get("/v1/company/profile", headers=auth_headers(access_token))
    assert res.status_code == 200
    assert res.json()["name"] == "Acme Co"

    res = client.patch(
        "/v1/company/profile",
        json={"business_name": "Acme Traders", "phone": "9999999999"},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 200
    assert res.json()["business_name"] == "Acme Traders"
    assert res.json()["phone"] == "9999999999"


@pytest.mark.integration
def test_company_create_user_requires_permissions(client, db_session, seed_roles):
    company = create_company(db_session, name="Seat Co", seat_limit=3)
    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    access_token, _ = login(client, "owner", "Pass@1234")

    res = client.post(
        "/v1/company/users",
        json={"username": "user1", "password": "Pass@1234", "role_code": "MANAGER", "allowed_modules": []},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "Select at least one permission"


@pytest.mark.integration
def test_company_users_seat_limit(client, db_session, seed_roles):
    company = create_company(db_session, name="Seat Co", seat_limit=1)
    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    access_token, _ = login(client, "owner", "Pass@1234")

    res = client.post(
        "/v1/company/users",
        json={
            "username": "user1",
            "password": "Pass@1234",
            "role_code": "MANAGER",
            "allowed_modules": ["sales"],
        },
        headers=auth_headers(access_token),
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "Seat limit reached"


@pytest.mark.integration
def test_company_enforce_single_manager(client, db_session, seed_roles):
    company = create_company(db_session, name="Single Manager", seat_limit=5)
    company.enforce_single_manager = True
    db_session.commit()

    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    access_token, _ = login(client, "owner", "Pass@1234")

    res = client.post(
        "/v1/company/users",
        json={
            "username": "mgr1",
            "password": "Pass@1234",
            "role_code": "MANAGER",
            "allowed_modules": ["sales"],
        },
        headers=auth_headers(access_token),
    )
    assert res.status_code == 200

    res = client.post(
        "/v1/company/users",
        json={
            "username": "mgr2",
            "password": "Pass@1234",
            "role_code": "MANAGER",
            "allowed_modules": ["sales"],
        },
        headers=auth_headers(access_token),
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "Only one manager allowed"


@pytest.mark.integration
def test_company_update_user_invalid_role(client, db_session, seed_roles):
    company = create_company(db_session, name="Role Co", seat_limit=5)
    owner = create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    access_token, _ = login(client, "owner", "Pass@1234")

    # create a user directly
    user = create_user(db_session, username="user1", password="Pass@1234", company_id=company.id, role_code="EMPLOYEE")

    res = client.patch(
        f"/v1/company/users/{user.id}",
        json={"role_code": "INVALID"},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 400

    # update allowed_modules empty should fail
    res = client.patch(
        f"/v1/company/users/{user.id}",
        json={"allowed_modules": []},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 400


@pytest.mark.integration
def test_company_list_users(client, db_session, seed_roles):
    company = create_company(db_session, name="Users Co", seat_limit=5)
    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    create_user(db_session, username="user1", password="Pass@1234", company_id=company.id, role_code="EMPLOYEE")

    access_token, _ = login(client, "owner", "Pass@1234")
    res = client.get("/v1/company/users", headers=auth_headers(access_token))
    assert res.status_code == 200
    assert len(res.json()) == 2
