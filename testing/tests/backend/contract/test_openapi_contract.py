import pytest


EXPECTED_ENDPOINTS = [
    ("/health", "get"),
    ("/v1/auth/login", "post"),
    ("/v1/auth/refresh", "post"),
    ("/v1/platform/companies", "post"),
    ("/v1/platform/companies", "get"),
    ("/v1/platform/companies/{company_id}", "patch"),
    ("/v1/platform/admin/profile", "get"),
    ("/v1/platform/admin/profile", "patch"),
    ("/v1/company/profile", "get"),
    ("/v1/company/profile", "patch"),
    ("/v1/company/users", "get"),
    ("/v1/company/users", "post"),
    ("/v1/company/users/{user_id}", "patch"),
    ("/v1/products/categories", "get"),
    ("/v1/products/categories", "post"),
    ("/v1/products/categories/{category_id}", "patch"),
    ("/v1/products", "get"),
    ("/v1/products", "post"),
    ("/v1/products/{product_id}", "patch"),
    ("/v1/products/{product_id}/deactivate", "post"),
    ("/v1/masters/customers", "get"),
    ("/v1/masters/customers", "post"),
    ("/v1/masters/customers/{customer_id}", "patch"),
    ("/v1/masters/suppliers", "get"),
    ("/v1/masters/suppliers", "post"),
    ("/v1/masters/suppliers/{supplier_id}", "patch"),
    ("/v1/inventory/stock", "get"),
    ("/v1/inventory/adjust", "post"),
    ("/v1/inventory/moves/{product_id}", "get"),
    ("/v1/sales/invoices", "get"),
    ("/v1/sales/invoices", "post"),
    ("/v1/sales/invoices/next-no", "get"),
    ("/v1/sales/invoices/{invoice_id}", "get"),
    ("/v1/sales/invoices/{invoice_id}/cancel", "post"),
    ("/v1/sales/invoices/{invoice_id}/return", "post"),
    ("/v1/purchase/invoices", "get"),
    ("/v1/purchase/invoices", "post"),
    ("/v1/purchase/invoices/next-no", "get"),
    ("/v1/purchase/invoices/{invoice_id}", "get"),
    ("/v1/purchase/invoices/{invoice_id}/cancel", "post"),
    ("/v1/quotations", "get"),
    ("/v1/quotations", "post"),
    ("/v1/quotations/next-no", "get"),
    ("/v1/quotations/{quotation_id}", "get"),
    ("/v1/quotations/{quotation_id}", "patch"),
    ("/v1/quotations/{quotation_id}/convert", "post"),
    ("/v1/quotations/{quotation_id}/duplicate", "post"),
    ("/v1/downloads", "post"),
    ("/v1/downloads/{job_id}", "get"),
    ("/v1/imports", "post"),
    ("/v1/imports/{job_id}", "get"),
    ("/v1/imports/templates/{module}", "get"),
    ("/v1/imports/{module}", "post"),
    ("/v1/accounting/accounts", "get"),
    ("/v1/accounting/accounts", "post"),
    ("/v1/accounting/vouchers", "get"),
    ("/v1/accounting/vouchers", "post"),
    ("/v1/payments", "post"),
    ("/v1/payments/{payment_id}/allocate", "post"),
    ("/v1/reports/trial-balance", "get"),
    ("/v1/reports/ledger/{ledger_id}", "get"),
    ("/v1/reports/pl", "get"),
    ("/v1/reports/balance-sheet", "get"),
]


@pytest.mark.contract
def test_openapi_contains_all_endpoints(client):
    res = client.get("/openapi.json")
    assert res.status_code == 200
    spec = res.json()
    paths = spec.get("paths", {})

    missing = []
    for path, method in EXPECTED_ENDPOINTS:
        if path not in paths or method not in paths[path]:
            missing.append(f"{method.upper()} {path}")

    assert not missing, f"Missing endpoints in OpenAPI: {missing}"
