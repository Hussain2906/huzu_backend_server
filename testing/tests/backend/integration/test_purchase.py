from datetime import datetime
import pytest

from testing.tests.factories import create_company, create_user, create_category, create_product, create_supplier
from testing.tests.helpers import login, auth_headers


@pytest.mark.integration
def test_purchase_requires_permission(client, db_session, seed_roles):
    company = create_company(db_session, name="Purchase Co")
    create_user(
        db_session,
        username="limited",
        password="Pass@1234",
        company_id=company.id,
        role_code="EMPLOYEE",
        allowed_modules=["sales"],
    )
    access_token, _ = login(client, "limited", "Pass@1234")

    res = client.get("/v1/purchase/invoices", headers=auth_headers(access_token))
    assert res.status_code == 403


@pytest.mark.integration
def test_purchase_gst_requires_supplier_gstin(client, db_session, seed_roles):
    company = create_company(db_session, name="Purchase Co")
    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    access_token, _ = login(client, "owner", "Pass@1234")

    supplier = create_supplier(db_session, company_id=company.id, name="ABC")
    category = create_category(db_session, company_id=company.id, name="General")
    product = create_product(db_session, company_id=company.id, category_id=category.id, name="Tape")

    res = client.post(
        "/v1/purchase/invoices",
        json={
            "invoice_no": "P-1",
            "invoice_date": datetime.utcnow().isoformat(),
            "tax_mode": "GST",
            "supplier_id": supplier.id,
            "lines": [
                {"product_id": product.id, "description": "Tape", "qty": 1, "price": 80, "tax_rate": 18},
            ],
        },
        headers=auth_headers(access_token),
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "Supplier GSTIN required for GST bills"


@pytest.mark.integration
def test_purchase_payment_status_unpaid(client, db_session, seed_roles):
    company = create_company(db_session, name="Purchase Co")
    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    access_token, _ = login(client, "owner", "Pass@1234")

    supplier = create_supplier(db_session, company_id=company.id, name="ABC")
    supplier.gstin = "22AAAAA0000A1Z5"
    db_session.commit()

    category = create_category(db_session, company_id=company.id, name="General")
    product = create_product(db_session, company_id=company.id, category_id=category.id, name="Tape")

    res = client.post(
        "/v1/purchase/invoices",
        json={
            "invoice_no": "P-2",
            "invoice_date": datetime.utcnow().isoformat(),
            "tax_mode": "GST",
            "supplier_id": supplier.id,
            "payment_status": "UNPAID",
            "lines": [
                {"product_id": product.id, "description": "Tape", "qty": 2, "price": 80, "tax_rate": 18},
            ],
        },
        headers=auth_headers(access_token),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["paid_amount"] == 0
    assert body["balance_due"] == body["grand_total"]

    # next invoice number
    res = client.get("/v1/purchase/invoices/next-no", headers=auth_headers(access_token))
    assert res.status_code == 200
    assert res.json()["invoice_no"]

    # detail endpoint
    res = client.get(f"/v1/purchase/invoices/{body['id']}", headers=auth_headers(access_token))
    assert res.status_code == 200


@pytest.mark.integration
def test_purchase_invalid_payment_mode(client, db_session, seed_roles):
    company = create_company(db_session, name="Purchase Co")
    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    access_token, _ = login(client, "owner", "Pass@1234")

    supplier = create_supplier(db_session, company_id=company.id, name="ABC")
    supplier.gstin = "22AAAAA0000A1Z5"
    db_session.commit()

    res = client.post(
        "/v1/purchase/invoices",
        json={
            "invoice_no": "P-3",
            "invoice_date": datetime.utcnow().isoformat(),
            "tax_mode": "GST",
            "supplier_id": supplier.id,
            "payment_mode": "CRYPTO",
            "lines": [
                {"description": "Service", "qty": 1, "price": 80, "tax_rate": 18},
            ],
        },
        headers=auth_headers(access_token),
    )
    assert res.status_code == 422
