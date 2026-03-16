import pytest

from testing.tests.factories import create_company, create_user
from testing.tests.helpers import login, auth_headers


@pytest.mark.integration
def test_download_job_create_and_get(client, db_session, seed_roles):
    company = create_company(db_session, name="Download Co")
    create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    access_token, _ = login(client, "owner", "Pass@1234")

    res = client.post(
        "/v1/downloads",
        json={"job_type": "sales_export", "filters": {"from": "2026-02-01"}},
        headers=auth_headers(access_token),
    )
    assert res.status_code == 200
    job_id = res.json()["id"]

    res = client.get(f"/v1/downloads/{job_id}", headers=auth_headers(access_token))
    assert res.status_code == 200
    assert res.json()["id"] == job_id

    res = client.get("/v1/downloads/not-found", headers=auth_headers(access_token))
    assert res.status_code == 200
    assert res.json()["status"] == "NOT_FOUND"
