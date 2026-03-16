import pytest

from testing.tests.factories import create_company, create_user
from testing.tests.helpers import login, auth_headers


@pytest.mark.integration
def test_customers_crud(client, db_session, seed_roles):
    company = create_company(db_session, name="Masters Co")
    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    access_token, _ = login(client, "owner", "Pass@1234")

    res = client.post(
        "/v1/masters/customers",
        json={"name": "Rahul", "phone": "9000000000"},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 200
    customer_id = res.json()["id"]

    res = client.get("/v1/masters/customers", headers=auth_headers(access_token))
    assert res.status_code == 200
    assert len(res.json()) == 1

    res = client.patch(
        f"/v1/masters/customers/{customer_id}",
        json={"address": "Street 1"},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 200
    assert res.json()["address"] == "Street 1"

    res = client.patch(
        "/v1/masters/customers/not-found",
        json={"address": "Street 2"},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 404


@pytest.mark.integration
def test_suppliers_crud(client, db_session, seed_roles):
    company = create_company(db_session, name="Masters Co")
    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    access_token, _ = login(client, "owner", "Pass@1234")

    res = client.post(
        "/v1/masters/suppliers",
        json={"name": "ABC Distributors", "phone": "9111111111", "address_line1": "Main Road"},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 200
    supplier_id = res.json()["id"]
    assert res.json()["address"] == "Main Road"

    res = client.get("/v1/masters/suppliers", headers=auth_headers(access_token))
    assert res.status_code == 200
    assert len(res.json()) == 1

    res = client.patch(
        f"/v1/masters/suppliers/{supplier_id}",
        json={"city": "Pune"},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 200
    assert res.json()["city"] == "Pune"

    res = client.patch(
        "/v1/masters/suppliers/not-found",
        json={"city": "Mumbai"},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 404
