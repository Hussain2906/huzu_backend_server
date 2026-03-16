from datetime import datetime
import pytest
from fastapi import HTTPException

from app.services.quotation_service import create_quotation, update_quotation
from app.db.models import QuotationStatus
from testing.tests.factories import create_company, create_user


@pytest.mark.unit
def test_quotation_invalid_line_type(db_session, seed_roles):
    company = create_company(db_session, name="Quote Co")
    user = create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")

    with pytest.raises(HTTPException):
        create_quotation(
            db_session,
            user,
            {
                "quotation_no": "Q-1",
                "quotation_date": datetime.utcnow(),
                "lines": [{"line_type": "BAD", "description": "x", "qty": 1, "price": 10}],
            },
        )


@pytest.mark.unit
def test_quotation_invalid_status_transition(db_session, seed_roles):
    company = create_company(db_session, name="Quote Co")
    user = create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")

    quotation = create_quotation(
        db_session,
        user,
        {
            "quotation_no": "Q-2",
            "quotation_date": datetime.utcnow(),
            "lines": [{"line_type": "DESCRIPTION", "description": "note", "qty": 1, "price": 0}],
        },
    )

    with pytest.raises(HTTPException):
        update_quotation(db_session, user, quotation, {"status": QuotationStatus.CONVERTED})


@pytest.mark.unit
def test_quotation_cannot_edit_cancelled(db_session, seed_roles):
    company = create_company(db_session, name="Quote Co")
    user = create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")

    quotation = create_quotation(
        db_session,
        user,
        {
            "quotation_no": "Q-3",
            "quotation_date": datetime.utcnow(),
            "status": QuotationStatus.CANCELLED,
            "lines": [{"line_type": "DESCRIPTION", "description": "note", "qty": 1, "price": 0}],
        },
    )

    with pytest.raises(HTTPException):
        update_quotation(db_session, user, quotation, {"notes": "new"})
