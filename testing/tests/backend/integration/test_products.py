import pytest

from testing.tests.factories import create_company, create_user
from testing.tests.helpers import login, auth_headers


@pytest.mark.integration
def test_categories_create_and_duplicate(client, db_session, seed_roles):
    company = create_company(db_session, name="Products Co")
    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    access_token, _ = login(client, "owner", "Pass@1234")

    res = client.post("/v1/products/categories", json={"name": ""}, headers=auth_headers(access_token))
    assert res.status_code == 400

    res = client.post("/v1/products/categories", json={"name": "Adhesives"}, headers=auth_headers(access_token))
    assert res.status_code == 200

    res = client.post("/v1/products/categories", json={"name": "adhesives"}, headers=auth_headers(access_token))
    assert res.status_code == 400
    assert res.json()["detail"] == "Category already exists"


@pytest.mark.integration
def test_category_update_duplicate(client, db_session, seed_roles):
    company = create_company(db_session, name="Cat Co")
    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    access_token, _ = login(client, "owner", "Pass@1234")

    cat1 = client.post("/v1/products/categories", json={"name": "Paint"}, headers=auth_headers(access_token)).json()
    cat2 = client.post("/v1/products/categories", json={"name": "Tools"}, headers=auth_headers(access_token)).json()

    res = client.patch(
        f"/v1/products/categories/{cat2['id']}",
        json={"name": "paint"},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 400


@pytest.mark.integration
def test_product_create_allows_no_category_and_duplicate_code(client, db_session, seed_roles):
    company = create_company(db_session, name="Prod Co")
    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    access_token, _ = login(client, "owner", "Pass@1234")

    res = client.post(
        "/v1/products",
        json={"name": "Glue", "selling_rate": 100, "purchase_rate": 80, "unit": "pcs"},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 200

    cat = client.post("/v1/products/categories", json={"name": "Adhesives"}, headers=auth_headers(access_token)).json()

    res = client.post(
        "/v1/products",
        json={
            "name": "Glue",
            "product_code": "P001",
            "category_id": cat["id"],
            "selling_rate": 100,
            "purchase_rate": 80,
            "unit": "pcs",
            "taxable": True,
            "tax_rate": 18,
        },
        headers=auth_headers(access_token),
    )
    assert res.status_code == 200

    res = client.post(
        "/v1/products",
        json={
            "name": "Glue 2",
            "product_code": "P001",
            "category_id": cat["id"],
            "selling_rate": 120,
            "purchase_rate": 90,
            "unit": "pcs",
            "taxable": True,
            "tax_rate": 18,
        },
        headers=auth_headers(access_token),
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "Product code already exists"


@pytest.mark.integration
def test_product_update_and_deactivate(client, db_session, seed_roles):
    company = create_company(db_session, name="Prod Co")
    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    access_token, _ = login(client, "owner", "Pass@1234")

    cat = client.post("/v1/products/categories", json={"name": "General"}, headers=auth_headers(access_token)).json()
    product = client.post(
        "/v1/products",
        json={
            "name": "Tape",
            "product_code": "T001",
            "category_id": cat["id"],
            "selling_rate": 50,
            "purchase_rate": 30,
            "unit": "pcs",
            "taxable": True,
            "tax_rate": 18,
        },
        headers=auth_headers(access_token),
    ).json()

    res = client.patch(
        f"/v1/products/{product['id']}",
        json={"product_code": "T001"},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 200

    res = client.patch(
        f"/v1/products/{product['id']}",
        json={"category_id": ""},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 400

    res = client.post(f"/v1/products/{product['id']}/deactivate", headers=auth_headers(access_token))
    assert res.status_code == 200
    assert res.json()["status"] == "INACTIVE"
