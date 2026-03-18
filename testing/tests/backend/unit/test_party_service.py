import pytest

from app.db.models import Customer, PartyRole, PartyRoleType, Supplier
from app.services.party_service import ensure_party_links_for_legacy_data
from testing.tests.factories import create_company


@pytest.mark.unit
def test_ensure_party_links_backfills_legacy_rows(db_session):
    company = create_company(db_session, name="Legacy Co")

    customer = Customer(company_id=company.id, name="Legacy Customer", phone="9000000000", gstin="22AAAAA0000A1Z5")
    supplier = Supplier(company_id=company.id, name="Legacy Supplier", phone="9111111111")
    db_session.add_all([customer, supplier])
    db_session.commit()

    assert customer.party_id is None
    assert supplier.party_id is None

    ensure_party_links_for_legacy_data(db_session)
    db_session.commit()

    db_session.refresh(customer)
    db_session.refresh(supplier)

    assert customer.party_id is not None
    assert supplier.party_id is not None

    customer_role = (
        db_session.query(PartyRole)
        .filter(
            PartyRole.company_id == company.id,
            PartyRole.party_id == customer.party_id,
            PartyRole.role == PartyRoleType.CUSTOMER,
            PartyRole.customer_id == customer.id,
        )
        .first()
    )
    supplier_role = (
        db_session.query(PartyRole)
        .filter(
            PartyRole.company_id == company.id,
            PartyRole.party_id == supplier.party_id,
            PartyRole.role == PartyRoleType.SUPPLIER,
            PartyRole.supplier_id == supplier.id,
        )
        .first()
    )
    assert customer_role is not None
    assert supplier_role is not None
