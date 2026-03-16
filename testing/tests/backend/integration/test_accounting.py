from datetime import datetime
import pytest

from testing.tests.factories import create_company, create_user
from testing.tests.helpers import login, auth_headers


@pytest.mark.integration
def test_accounting_list_and_add_account(client, db_session, seed_roles):
    company = create_company(db_session, name="Acct Co")
    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    access_token, _ = login(client, "owner", "Pass@1234")

    res = client.get("/v1/accounting/accounts", headers=auth_headers(access_token))
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) >= 5

    res = client.post(
        "/v1/accounting/accounts",
        json={"code": "9999", "name": "Test Ledger", "type": "ASSET", "is_bank": False},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 200
    assert res.json()["code"] == "9999"


@pytest.mark.integration
def test_accounting_voucher_balanced_validation(client, db_session, seed_roles):
    company = create_company(db_session, name="Acct Co")
    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    access_token, _ = login(client, "owner", "Pass@1234")

    accounts = client.get("/v1/accounting/accounts", headers=auth_headers(access_token)).json()
    ledger_a = accounts[0]["id"]
    ledger_b = accounts[1]["id"]

    res = client.post(
        "/v1/accounting/vouchers",
        json={
            "voucher_type": "JOURNAL",
            "number": "JV-1",
            "date": datetime.utcnow().isoformat(),
            "lines": [
                {"ledger_id": ledger_a, "dr": 100, "cr": 0},
                {"ledger_id": ledger_b, "dr": 0, "cr": 90},
            ],
        },
        headers=auth_headers(access_token),
    )
    assert res.status_code == 400

    res = client.post(
        "/v1/accounting/vouchers",
        json={
            "voucher_type": "JOURNAL",
            "number": "JV-2",
            "date": datetime.utcnow().isoformat(),
            "lines": [
                {"ledger_id": ledger_a, "dr": 100, "cr": 0},
                {"ledger_id": ledger_b, "dr": 0, "cr": 100},
            ],
        },
        headers=auth_headers(access_token),
    )
    assert res.status_code == 200
