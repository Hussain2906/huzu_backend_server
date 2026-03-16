from datetime import datetime
import pytest

from testing.tests.factories import create_company, create_user, create_category, create_product, create_customer
from testing.tests.helpers import login, auth_headers


@pytest.mark.integration
def test_payments_create_and_allocate(client, db_session, seed_roles):
    company = create_company(db_session, name="Pay Co")
    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    access_token, _ = login(client, "owner", "Pass@1234")

    # create sales invoice
    customer = create_customer(db_session, company_id=company.id, name="Rahul")
    customer.gstin = "22AAAAA0000A1Z5"
    db_session.commit()
    category = create_category(db_session, company_id=company.id, name="General")
    product = create_product(db_session, company_id=company.id, category_id=category.id, name="Tape")

    res = client.post(
        "/v1/sales/invoices",
        json={
            "invoice_no": "S-900",
            "invoice_date": datetime.utcnow().isoformat(),
            "tax_mode": "GST",
            "customer_id": customer.id,
            "lines": [
                {"product_id": product.id, "description": "Tape", "qty": 2, "price": 100, "tax_rate": 18},
            ],
        },
        headers=auth_headers(access_token),
    )
    assert res.status_code == 200
    invoice_id = res.json()["id"]

    # create payment
    res = client.post(
        "/v1/payments",
        json={
            "counterparty_type": "CUSTOMER",
            "counterparty_id": customer.id,
            "mode": "CASH",
            "amount": 100,
        },
        headers=auth_headers(access_token),
    )
    assert res.status_code == 200
    payment_id = res.json()["id"]

    # allocate payment
    res = client.post(
        f"/v1/payments/{payment_id}/allocate",
        json={"allocations": [{"invoice_id": invoice_id, "amount": 100}]},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 200
    assert res.json()["allocations"] == 1


@pytest.mark.integration
def test_payments_allocate_invalid_payment(client, db_session, seed_roles):
    company = create_company(db_session, name="Pay Co")
    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    access_token, _ = login(client, "owner", "Pass@1234")

    res = client.post(
        "/v1/payments/not-found/allocate",
        json={"allocations": []},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 400
