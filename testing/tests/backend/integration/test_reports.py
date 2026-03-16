from datetime import datetime, timedelta
import pytest

from testing.tests.factories import create_company, create_user, create_category, create_product, create_customer
from testing.tests.helpers import login, auth_headers


@pytest.mark.integration
def test_reports_endpoints_return_shapes(client, db_session, seed_roles):
    company = create_company(db_session, name="Report Co")
    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    access_token, _ = login(client, "owner", "Pass@1234")

    # create a sale to generate vouchers
    customer = create_customer(db_session, company_id=company.id, name="Rahul")
    customer.gstin = "22AAAAA0000A1Z5"
    db_session.commit()
    category = create_category(db_session, company_id=company.id, name="General")
    product = create_product(db_session, company_id=company.id, category_id=category.id, name="Tape")

    client.post(
        "/v1/sales/invoices",
        json={
            "invoice_no": "S-700",
            "invoice_date": datetime.utcnow().isoformat(),
            "tax_mode": "GST",
            "customer_id": customer.id,
            "lines": [
                {"product_id": product.id, "description": "Tape", "qty": 1, "price": 100, "tax_rate": 18},
            ],
        },
        headers=auth_headers(access_token),
    )

    as_of = datetime.utcnow().isoformat()
    res = client.get(f"/v1/reports/trial-balance?as_of={as_of}", headers=auth_headers(access_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)

    # ledger report
    # pick any ledger id from trial balance if available
    tb = res.json()
    if tb:
        ledger_id = tb[0]["ledger_id"]
        date_from = (datetime.utcnow() - timedelta(days=2)).isoformat()
        date_to = datetime.utcnow().isoformat()
        res = client.get(
            f"/v1/reports/ledger/{ledger_id}?date_from={date_from}&date_to={date_to}",
            headers=auth_headers(access_token),
        )
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    res = client.get(
        f"/v1/reports/pl?date_from={(datetime.utcnow()-timedelta(days=1)).isoformat()}&date_to={datetime.utcnow().isoformat()}",
        headers=auth_headers(access_token),
    )
    assert res.status_code == 200
    assert "net_profit" in res.json()

    res = client.get(f"/v1/reports/balance-sheet?as_of={as_of}", headers=auth_headers(access_token))
    assert res.status_code == 200
    assert "assets" in res.json()
