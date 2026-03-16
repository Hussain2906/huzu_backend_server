from datetime import datetime, timedelta
import pytest

from app.db.models import InvoiceLine
from testing.tests.factories import create_company, create_user, create_category, create_product, create_customer
from testing.tests.helpers import login, auth_headers


@pytest.mark.integration
def test_sales_requires_permission(client, db_session, seed_roles):
    company = create_company(db_session, name="Sales Co")
    create_user(
        db_session,
        username="limited",
        password="Pass@1234",
        company_id=company.id,
        role_code="EMPLOYEE",
        allowed_modules=["purchase"],
    )
    access_token, _ = login(client, "limited", "Pass@1234")

    res = client.get("/v1/sales/invoices", headers=auth_headers(access_token))
    assert res.status_code == 403


@pytest.mark.integration
def test_sales_gst_requires_customer_gstin(client, db_session, seed_roles):
    company = create_company(db_session, name="Sales Co")
    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    access_token, _ = login(client, "owner", "Pass@1234")

    customer = create_customer(db_session, company_id=company.id, name="Rahul")
    category = create_category(db_session, company_id=company.id, name="General")
    product = create_product(db_session, company_id=company.id, category_id=category.id, name="Glue")

    res = client.post(
        "/v1/sales/invoices",
        json={
            "invoice_no": "S-1",
            "invoice_date": datetime.utcnow().isoformat(),
            "tax_mode": "GST",
            "customer_id": customer.id,
            "lines": [
                {"product_id": product.id, "description": "Glue", "qty": 1, "price": 100, "tax_rate": 18},
            ],
        },
        headers=auth_headers(access_token),
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "Party GSTIN required for GST invoices"


@pytest.mark.integration
def test_sales_invoice_duplicate_and_hsn_handling(client, db_session, seed_roles):
    company = create_company(db_session, name="Sales Co")
    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    access_token, _ = login(client, "owner", "Pass@1234")

    category = create_category(db_session, company_id=company.id, name="General")
    product = create_product(db_session, company_id=company.id, category_id=category.id, name="Tape", hsn="1234")

    res = client.post(
        "/v1/sales/invoices",
        json={
            "invoice_no": "S-1",
            "invoice_date": datetime.utcnow().isoformat(),
            "tax_mode": "NON_GST",
            "lines": [
                {"product_id": product.id, "description": "Tape", "hsn": "1234", "qty": 1, "price": 100},
            ],
        },
        headers=auth_headers(access_token),
    )
    assert res.status_code == 200
    invoice_id = res.json()["id"]

    line = db_session.query(InvoiceLine).first()
    assert line is not None
    assert line.hsn is None  # non-gst sales should omit HSN in backend

    # duplicate invoice_no
    res = client.post(
        "/v1/sales/invoices",
        json={
            "invoice_no": "S-1",
            "invoice_date": datetime.utcnow().isoformat(),
            "tax_mode": "NON_GST",
            "lines": [
                {"description": "Service", "qty": 1, "price": 100},
            ],
        },
        headers=auth_headers(access_token),
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "Duplicate invoice number"

    # next invoice number
    res = client.get("/v1/sales/invoices/next-no", headers=auth_headers(access_token))
    assert res.status_code == 200
    assert res.json()["invoice_no"]

    # get detail endpoint
    res = client.get(f"/v1/sales/invoices/{invoice_id}", headers=auth_headers(access_token))
    assert res.status_code == 200


@pytest.mark.integration
def test_sales_discount_boundaries_and_invalid_payment_mode(client, db_session, seed_roles):
    company = create_company(db_session, name="Sales Co")
    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    access_token, _ = login(client, "owner", "Pass@1234")

    category = create_category(db_session, company_id=company.id, name="General")
    product = create_product(db_session, company_id=company.id, category_id=category.id, name="Tape")

    res = client.post(
        "/v1/sales/invoices",
        json={
            "invoice_no": "S-2",
            "invoice_date": datetime.utcnow().isoformat(),
            "tax_mode": "NON_GST",
            "lines": [
                {"product_id": product.id, "description": "Tape", "qty": 1, "price": 100, "discount_percent": 150},
            ],
        },
        headers=auth_headers(access_token),
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "Invalid discount percent"

    res = client.post(
        "/v1/sales/invoices",
        json={
            "invoice_no": "S-3",
            "invoice_date": datetime.utcnow().isoformat(),
            "tax_mode": "NON_GST",
            "payment_mode": "CRYPTO",
            "lines": [
                {"description": "Service", "qty": 1, "price": 100},
            ],
        },
        headers=auth_headers(access_token),
    )
    assert res.status_code == 422


@pytest.mark.integration
def test_sales_backdated_restricted_for_non_admin(client, db_session, seed_roles):
    company = create_company(db_session, name="Sales Co")
    create_user(db_session, username="manager", password="Pass@1234", company_id=company.id, role_code="MANAGER")
    access_token, _ = login(client, "manager", "Pass@1234")

    res = client.post(
        "/v1/sales/invoices",
        json={
            "invoice_no": "S-10",
            "invoice_date": (datetime.utcnow() - timedelta(days=1)).isoformat(),
            "tax_mode": "NON_GST",
            "lines": [
                {"description": "Service", "qty": 1, "price": 100},
            ],
        },
        headers=auth_headers(access_token),
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "Backdated invoices are restricted"


@pytest.mark.integration
def test_sales_returns_and_stock(client, db_session, seed_roles):
    company = create_company(db_session, name="Sales Co")
    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    access_token, _ = login(client, "owner", "Pass@1234")

    category = create_category(db_session, company_id=company.id, name="General")
    product = create_product(db_session, company_id=company.id, category_id=category.id, name="Tape")

    # Create sale of qty 2
    res = client.post(
        "/v1/sales/invoices",
        json={
            "invoice_no": "S-20",
            "invoice_date": datetime.utcnow().isoformat(),
            "tax_mode": "NON_GST",
            "lines": [
                {"product_id": product.id, "description": "Tape", "qty": 2, "price": 100},
            ],
        },
        headers=auth_headers(access_token),
    )
    assert res.status_code == 200


@pytest.mark.integration
def test_sales_gst_totals_and_tax_summary_are_computed(client, db_session, seed_roles):
    company = create_company(db_session, name="GST Sales Co")
    company.gstin = "27ABCDE1234F1Z5"
    company.state = "Maharashtra"
    db_session.commit()
    create_user(db_session, username="gst_owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    access_token, _ = login(client, "gst_owner", "Pass@1234")

    customer = create_customer(db_session, company_id=company.id, name="Rahul Traders")
    customer.gstin = "27AAACB1234C1Z9"
    customer.extra_json = {"state": "Maharashtra", "state_code": "27"}
    db_session.commit()

    category = create_category(db_session, company_id=company.id, name="General")
    product = create_product(db_session, company_id=company.id, category_id=category.id, name="Glue", selling_rate=2500, tax_rate=18)

    res = client.post(
        "/v1/sales/invoices",
        json={
            "invoice_no": "S-GST-1",
            "invoice_date": datetime.utcnow().isoformat(),
            "tax_mode": "GST",
            "customer_id": customer.id,
            "lines": [
                {"product_id": product.id, "description": "Glue", "qty": 1, "price": 2500, "tax_rate": 18, "taxable": True},
            ],
        },
        headers=auth_headers(access_token),
    )
    assert res.status_code == 200
    invoice_id = res.json()["id"]

    detail = client.get(f"/v1/sales/invoices/{invoice_id}", headers=auth_headers(access_token))
    assert detail.status_code == 200
    body = detail.json()
    assert body["subtotal"] == 2500.0
    assert body["tax_total"] == 450.0
    assert body["cgst_amount"] == 225.0
    assert body["sgst_amount"] == 225.0
    assert body["igst_amount"] in (None, 0, 0.0)
    assert body["grand_total"] == 2950.0
    assert body["tax_summary"][0]["central_tax_rate"] == 9.0
    assert body["tax_summary"][0]["state_tax_rate"] == 9.0
    assert body["tax_summary"][0]["total_tax_amount"] == 450.0
    invoice_id = res.json()["id"]

    # Return exceeds sold quantity
    res = client.post(
        f"/v1/sales/invoices/{invoice_id}/return",
        json={"lines": [{"product_id": product.id, "qty": 5}]},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 400

    # Valid return
    res = client.post(
        f"/v1/sales/invoices/{invoice_id}/return",
        json={"lines": [{"product_id": product.id, "qty": 1}], "notes": "Damaged"},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 200
