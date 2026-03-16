import pytest

from app.db.models import InventoryLedger, StockReason
from testing.tests.factories import create_company, create_user, create_category, create_product
from testing.tests.helpers import login, auth_headers


@pytest.mark.integration
def test_inventory_adjust_and_moves(client, db_session, seed_roles):
    company = create_company(db_session, name="Inventory Co")
    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    access_token, _ = login(client, "owner", "Pass@1234")

    # invalid product
    res = client.post(
        "/v1/inventory/adjust",
        json={"product_id": "does-not-exist", "new_qty": 10},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 404

    # create product
    category = create_category(db_session, company_id=company.id, name="General")
    product = create_product(db_session, company_id=company.id, category_id=category.id, name="Glue", product_code="P001")

    # negative qty rejected by schema
    res = client.post(
        "/v1/inventory/adjust",
        json={"product_id": product.id, "new_qty": -1},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 422

    res = client.post(
        "/v1/inventory/adjust",
        json={"product_id": product.id, "new_qty": 10, "notes": "Initial"},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 200
    assert res.json()["qty_on_hand"] == 10

    # list stock
    res = client.get("/v1/inventory/stock", headers=auth_headers(access_token))
    assert res.status_code == 200
    assert res.json()[0]["qty_on_hand"] == 10

    # moves should include adjustment
    res = client.get(f"/v1/inventory/moves/{product.id}", headers=auth_headers(access_token))
    assert res.status_code == 200
    assert len(res.json()) == 1

    row = db_session.query(InventoryLedger).filter(InventoryLedger.product_id == product.id).first()
    assert row is not None
    assert row.reason == StockReason.ADJUSTMENT
