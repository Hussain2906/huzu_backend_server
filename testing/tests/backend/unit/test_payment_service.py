import pytest

from app.services.payments.payment_service import create_payment
from testing.tests.factories import create_company


@pytest.mark.unit
def test_create_payment_invalid_mode(db_session, seed_roles):
    company = create_company(db_session, name="Pay Co")
    with pytest.raises(Exception):
        create_payment(db_session, company.id, {"mode": "CRYPTO", "amount": 10, "counterparty_type": "OTHER"})
