from datetime import datetime
import pytest

from app.db.models import Quotation, QuotationStatus, Invoice
from testing.tests.factories import create_company, create_user, create_category, create_product, create_customer
from testing.tests.helpers import login, auth_headers


@pytest.mark.integration
def test_quotation_create_duplicate_and_line_types(client, db_session, seed_roles):
    company = create_company(db_session, name="Quote Co")
    create_user(
        db_session,
        username="sales",
        password="Pass@1234",
        company_id=company.id,
        role_code="MANAGER",
        allowed_modules=["sales"],
    )
    access_token, _ = login(client, "sales", "Pass@1234")

    customer = create_customer(db_session, company_id=company.id, name="Rahul")
    category = create_category(db_session, company_id=company.id, name="General")
    product = create_product(db_session, company_id=company.id, category_id=category.id, name="Tape")

    payload = {
        "quotation_no": "Q-1",
        "quotation_date": datetime.utcnow().isoformat(),
        "customer_id": customer.id,
        "lines": [
            {"line_type": "DESCRIPTION", "description": "Note line", "qty": 0, "price": 0, "discount_percent": 0},
            {"line_type": "PRODUCT", "product_id": product.id, "description": "Tape", "qty": 2, "price": 100, "discount_percent": 0},
        ],
    }
    res = client.post("/v1/quotations", json=payload, headers=auth_headers(access_token))
    assert res.status_code == 200

    # duplicate quotation number
    res = client.post("/v1/quotations", json=payload, headers=auth_headers(access_token))
    assert res.status_code == 400

    res = client.get("/v1/quotations/next-no", headers=auth_headers(access_token))
    assert res.status_code == 200
    assert res.json()["quotation_no"]

    # ensure description line qty coerced to 1 (order not guaranteed)
    quote_id = client.get("/v1/quotations", headers=auth_headers(access_token)).json()[0]["id"]
    detail = client.get(f"/v1/quotations/{quote_id}", headers=auth_headers(access_token)).json()
    desc_lines = [line for line in detail["lines"] if line["line_type"] == "DESCRIPTION"]
    assert desc_lines, "Expected a DESCRIPTION line"
    assert desc_lines[0]["qty"] == 1


@pytest.mark.integration
def test_quotation_status_transition_and_convert(client, db_session, seed_roles):
    company = create_company(db_session, name="Quote Co")
    create_user(
        db_session,
        username="sales",
        password="Pass@1234",
        company_id=company.id,
        role_code="MANAGER",
        allowed_modules=["sales"],
    )
    access_token, _ = login(client, "sales", "Pass@1234")

    customer = create_customer(db_session, company_id=company.id, name="Rahul")
    category = create_category(db_session, company_id=company.id, name="General")
    product = create_product(db_session, company_id=company.id, category_id=category.id, name="Tape")

    res = client.post(
        "/v1/quotations",
        json={
            "quotation_no": "Q-2",
            "quotation_date": datetime.utcnow().isoformat(),
            "customer_id": customer.id,
            "lines": [
                {"line_type": "PRODUCT", "product_id": product.id, "description": "Tape", "qty": 1, "price": 100},
            ],
        },
        headers=auth_headers(access_token),
    )
    assert res.status_code == 200
    quote_id = res.json()["id"]

    # invalid transition: directly to CONVERTED
    res = client.patch(
        f"/v1/quotations/{quote_id}",
        json={"status": "CONVERTED"},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 400

    # convert to sale
    res = client.post(
        f"/v1/quotations/{quote_id}/convert",
        json={"tax_mode": "NON_GST"},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 200
    invoice_id = res.json()["invoice_id"]

    quotation = db_session.get(Quotation, quote_id)
    assert quotation.status == QuotationStatus.CONVERTED
    assert quotation.converted_invoice_id == invoice_id

    invoice = db_session.get(Invoice, invoice_id)
    assert invoice is not None
    assert invoice.source_quotation_no == "Q-2"


@pytest.mark.integration
def test_quotation_convert_cancelled_forbidden(client, db_session, seed_roles):
    company = create_company(db_session, name="Quote Co")
    create_user(
        db_session,
        username="sales",
        password="Pass@1234",
        company_id=company.id,
        role_code="MANAGER",
        allowed_modules=["sales"],
    )
    access_token, _ = login(client, "sales", "Pass@1234")

    res = client.post(
        "/v1/quotations",
        json={
            "quotation_no": "Q-3",
            "quotation_date": datetime.utcnow().isoformat(),
            "lines": [
                {"line_type": "DESCRIPTION", "description": "Note", "qty": 1, "price": 0},
            ],
        },
        headers=auth_headers(access_token),
    )
    quote_id = res.json()["id"]

    # cancel
    client.patch(
        f"/v1/quotations/{quote_id}",
        json={"status": "CANCELLED"},
        headers=auth_headers(access_token),
    )

    res = client.post(
        f"/v1/quotations/{quote_id}/convert",
        json={"tax_mode": "GST"},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 400
