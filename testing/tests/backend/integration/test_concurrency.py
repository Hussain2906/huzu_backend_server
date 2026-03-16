from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import pytest

from app.db.models import ProductCategory, Invoice
from testing.tests.factories import create_company, create_user, create_category, create_product
from testing.tests.helpers import login, auth_headers


@pytest.mark.integration
@pytest.mark.concurrency
def test_concurrent_category_create(client_factory, db_session, seed_roles):
    company = create_company(db_session, name="Race Co")
    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")

    client = client_factory()
    access_token, _ = login(client, "owner", "Pass@1234")
    headers = auth_headers(access_token)

    def _create():
        c = client_factory()
        return c.post("/v1/products/categories", json={"name": "Tools"}, headers=headers).status_code

    with ThreadPoolExecutor(max_workers=2) as ex:
        results = list(ex.map(lambda _: _create(), range(2)))

    # Only one category should exist
    count = db_session.query(ProductCategory).filter(ProductCategory.company_id == company.id).count()
    assert count == 1
    assert any(code == 200 for code in results)


@pytest.mark.integration
@pytest.mark.concurrency
def test_concurrent_invoice_create_duplicate(client_factory, db_session, seed_roles):
    company = create_company(db_session, name="Race Co")
    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")

    category = create_category(db_session, company_id=company.id, name="General")
    product = create_product(db_session, company_id=company.id, category_id=category.id, name="Tape")

    client = client_factory()
    access_token, _ = login(client, "owner", "Pass@1234")
    headers = auth_headers(access_token)

    payload = {
        "invoice_no": "S-1000",
        "invoice_date": datetime.utcnow().isoformat(),
        "tax_mode": "NON_GST",
        "lines": [{"product_id": product.id, "description": "Tape", "qty": 1, "price": 10}],
    }

    def _create():
        c = client_factory()
        return c.post("/v1/sales/invoices", json=payload, headers=headers).status_code

    with ThreadPoolExecutor(max_workers=2) as ex:
        results = list(ex.map(lambda _: _create(), range(2)))

    count = db_session.query(Invoice).filter(Invoice.company_id == company.id, Invoice.invoice_no == "S-1000").count()
    assert count == 1
    assert results.count(200) == 1
