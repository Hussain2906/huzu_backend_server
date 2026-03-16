import io
import csv
import pytest

from testing.tests.factories import create_company, create_user
from testing.tests.helpers import login, auth_headers


def _csv_bytes(headers, rows):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


@pytest.mark.integration
@pytest.mark.csv
def test_download_template_contains_required_headers(client, db_session, seed_roles):
    company = create_company(db_session, name="Import Co")
    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    access_token, _ = login(client, "owner", "Pass@1234")

    res = client.get("/v1/imports/templates/products", headers=auth_headers(access_token))
    assert res.status_code == 200
    text = res.text
    assert "name" in text.split("\n")[0]
    assert "category" in text.split("\n")[0]


@pytest.mark.integration
@pytest.mark.csv
def test_import_job_create_and_get(client, db_session, seed_roles):
    company = create_company(db_session, name="Import Co")
    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    access_token, _ = login(client, "owner", "Pass@1234")

    res = client.post(
        "/v1/imports",
        json={"job_type": "products", "source_path": "/tmp/file.csv"},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 200
    job_id = res.json()["id"]

    res = client.get(f"/v1/imports/{job_id}", headers=auth_headers(access_token))
    assert res.status_code == 200
    assert res.json()["id"] == job_id


@pytest.mark.integration
@pytest.mark.csv
def test_import_rejects_non_csv(client, db_session, seed_roles):
    company = create_company(db_session, name="Import Co")
    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    access_token, _ = login(client, "owner", "Pass@1234")

    res = client.post(
        "/v1/imports/products",
        files={"file": ("data.txt", b"not csv", "text/plain")},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 400


@pytest.mark.integration
@pytest.mark.csv
def test_import_unknown_module(client, db_session, seed_roles):
    company = create_company(db_session, name="Import Co")
    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    access_token, _ = login(client, "owner", "Pass@1234")

    headers = ["name", "category"]
    data = _csv_bytes(headers, [{"name": "x", "category": "c"}])

    res = client.post(
        "/v1/imports/unknown",
        files={"file": ("data.csv", data, "text/csv")},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 200
    assert res.json()["status"] == "FAILED"


@pytest.mark.integration
@pytest.mark.csv
def test_import_products_validation_errors(client, db_session, seed_roles):
    company = create_company(db_session, name="Import Co")
    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    access_token, _ = login(client, "owner", "Pass@1234")

    headers = ["name", "category", "selling_rate"]
    rows = [
        {"name": "", "category": "General", "selling_rate": "100"},
        {"name": "Glue", "category": "", "selling_rate": "abc"},
    ]
    data = _csv_bytes(headers, rows)

    res = client.post(
        "/v1/imports/products",
        files={"file": ("products.csv", data, "text/csv")},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "FAILED"
    assert body["imported"] == 0
    assert any(err["row"] == 2 for err in body["errors"])


@pytest.mark.integration
@pytest.mark.csv
def test_import_sales_gst_requires_gstin(client, db_session, seed_roles):
    company = create_company(db_session, name="Import Co")
    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    access_token, _ = login(client, "owner", "Pass@1234")

    headers = [
        "invoice_no",
        "invoice_date",
        "tax_mode",
        "customer_name",
        "qty",
        "price",
        "product_name",
        "category",
    ]
    rows = [
        {
            "invoice_no": "S-100",
            "invoice_date": "2026-02-05",
            "tax_mode": "GST",
            "customer_name": "Rahul",
            "qty": "1",
            "price": "100",
            "product_name": "Glue",
            "category": "General",
        }
    ]
    data = _csv_bytes(headers, rows)

    res = client.post(
        "/v1/imports/sales",
        files={"file": ("sales.csv", data, "text/csv")},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "FAILED"
    assert any(err["field"] == "customer_gstin" for err in body["errors"])


@pytest.mark.integration
@pytest.mark.csv
def test_import_products_success_large_file(client, db_session, seed_roles):
    company = create_company(db_session, name="Import Co")
    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    access_token, _ = login(client, "owner", "Pass@1234")

    headers = ["name", "category", "selling_rate", "purchase_rate", "taxable", "tax_rate"]
    rows = []
    for i in range(1, 51):
        rows.append(
            {
                "name": f"Product {i}",
                "category": "General",
                "selling_rate": "100",
                "purchase_rate": "80",
                "taxable": "TRUE",
                "tax_rate": "18",
            }
        )
    data = _csv_bytes(headers, rows)

    res = client.post(
        "/v1/imports/products",
        files={"file": ("products.csv", data, "text/csv")},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "SUCCESS"
    assert body["imported"] == 50
