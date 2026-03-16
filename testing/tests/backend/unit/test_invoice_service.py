from datetime import datetime
import pytest
from fastapi import HTTPException

from app.services.invoice_service import create_invoice, generate_next_invoice_no
from app.db.models import InvoiceType, TaxMode, PaymentMode, InvoiceLine
from testing.tests.factories import create_company, create_user, create_category, create_product


@pytest.mark.unit
def test_generate_next_invoice_no(db_session, seed_roles):
    company = create_company(db_session, name="Test Co")
    user = create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")

    assert generate_next_invoice_no(db_session, company.id, InvoiceType.SALES) == "S-0001"

    create_invoice(
        db_session,
        user,
        InvoiceType.SALES,
        {
            "invoice_no": "S-0099",
            "invoice_date": datetime.utcnow(),
            "tax_mode": TaxMode.NON_GST,
            "lines": [{"description": "Service", "qty": 1, "price": 100}],
        },
    )
    assert generate_next_invoice_no(db_session, company.id, InvoiceType.SALES) == "S-0100"


@pytest.mark.unit
def test_create_invoice_discount_validation(db_session, seed_roles):
    company = create_company(db_session, name="Test Co")
    user = create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")

    with pytest.raises(HTTPException):
        create_invoice(
            db_session,
            user,
            InvoiceType.SALES,
            {
                "invoice_no": "S-1",
                "invoice_date": datetime.utcnow(),
                "tax_mode": TaxMode.NON_GST,
                "lines": [{"description": "Service", "qty": 1, "price": 100, "discount_percent": 120}],
            },
        )

    # boundary values should be accepted
    create_invoice(
        db_session,
        user,
        InvoiceType.SALES,
        {
            "invoice_no": "S-1A",
            "invoice_date": datetime.utcnow(),
            "tax_mode": TaxMode.NON_GST,
            "lines": [{"description": "Service", "qty": 1, "price": 100, "discount_percent": 0}],
        },
    )
    create_invoice(
        db_session,
        user,
        InvoiceType.SALES,
        {
            "invoice_no": "S-1B",
            "invoice_date": datetime.utcnow(),
            "tax_mode": TaxMode.NON_GST,
            "lines": [{"description": "Service", "qty": 1, "price": 100, "discount_percent": 100}],
        },
    )


@pytest.mark.unit
def test_create_invoice_invalid_tax_mode(db_session, seed_roles):
    company = create_company(db_session, name="Test Co")
    user = create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")

    with pytest.raises(HTTPException):
        create_invoice(
            db_session,
            user,
            InvoiceType.SALES,
            {
                "invoice_no": "S-2",
                "invoice_date": datetime.utcnow(),
                "tax_mode": "BAD",
                "lines": [{"description": "Service", "qty": 1, "price": 100}],
            },
        )


@pytest.mark.unit
def test_create_invoice_non_gst_hsn_removed(db_session, seed_roles):
    company = create_company(db_session, name="Test Co")
    user = create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")
    category = create_category(db_session, company_id=company.id, name="General")
    product = create_product(db_session, company_id=company.id, category_id=category.id, name="Tape", hsn="1234")

    create_invoice(
        db_session,
        user,
        InvoiceType.SALES,
        {
            "invoice_no": "S-3",
            "invoice_date": datetime.utcnow(),
            "tax_mode": TaxMode.NON_GST,
            "lines": [{"product_id": product.id, "description": "Tape", "qty": 1, "price": 100, "hsn": "1234"}],
        },
    )
    line = db_session.query(InvoiceLine).first()
    assert line is not None
    assert line.hsn is None


@pytest.mark.unit
def test_create_invoice_invalid_payment_mode(db_session, seed_roles):
    company = create_company(db_session, name="Test Co")
    user = create_user(db_session, username="owner", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")

    with pytest.raises(HTTPException):
        create_invoice(
            db_session,
            user,
            InvoiceType.SALES,
            {
                "invoice_no": "S-4",
                "invoice_date": datetime.utcnow(),
                "tax_mode": TaxMode.NON_GST,
                "payment_mode": "CRYPTO",
                "lines": [{"description": "Service", "qty": 1, "price": 100}],
            },
        )

    # valid payment mode should not raise
    create_invoice(
        db_session,
        user,
        InvoiceType.SALES,
        {
            "invoice_no": "S-5",
            "invoice_date": datetime.utcnow(),
            "tax_mode": TaxMode.NON_GST,
            "payment_mode": PaymentMode.CASH,
            "lines": [{"description": "Service", "qty": 1, "price": 100}],
        },
    )


@pytest.mark.unit
def test_create_invoice_intra_state_gst_split(db_session, seed_roles):
    company = create_company(db_session, name="GST Co")
    company.gstin = "27ABCDE1234F1Z5"
    company.state = "Maharashtra"
    db_session.commit()
    user = create_user(db_session, username="owner_gst", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")

    invoice = create_invoice(
        db_session,
        user,
        InvoiceType.SALES,
        {
            "invoice_no": "GST-1",
            "invoice_date": datetime.utcnow(),
            "tax_mode": TaxMode.GST,
            "company_snapshot_json": {"state": "Maharashtra", "state_code": "27", "gstin": company.gstin},
            "customer_snapshot_json": {"name": "Buyer", "gstin": "27AAACB1234C1Z9", "state": "Maharashtra", "state_code": "27"},
            "lines": [{"description": "Taxable Item", "qty": 1, "price": 2500, "tax_rate": 18, "taxable": True}],
        },
    )

    assert float(invoice.subtotal) == 2500.0
    assert float(invoice.tax_total) == 450.0
    assert float(invoice.cgst_amount or 0) == 225.0
    assert float(invoice.sgst_amount or 0) == 225.0
    assert float(invoice.igst_amount or 0) == 0.0
    assert float(invoice.grand_total) == 2950.0


@pytest.mark.unit
def test_create_invoice_inter_state_igst_split(db_session, seed_roles):
    company = create_company(db_session, name="GST Co 2")
    company.gstin = "27ABCDE1234F1Z5"
    company.state = "Maharashtra"
    db_session.commit()
    user = create_user(db_session, username="owner_gst_2", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")

    invoice = create_invoice(
        db_session,
        user,
        InvoiceType.SALES,
        {
            "invoice_no": "GST-2",
            "invoice_date": datetime.utcnow(),
            "tax_mode": TaxMode.GST,
            "company_snapshot_json": {"state": "Maharashtra", "state_code": "27", "gstin": company.gstin},
            "customer_snapshot_json": {"name": "Buyer", "gstin": "29AAACB1234C1Z9", "state": "Karnataka", "state_code": "29"},
            "lines": [{"description": "Taxable Item", "qty": 1, "price": 2500, "tax_rate": 18, "taxable": True}],
        },
    )

    assert float(invoice.subtotal) == 2500.0
    assert float(invoice.tax_total) == 450.0
    assert float(invoice.cgst_amount or 0) == 0.0
    assert float(invoice.sgst_amount or 0) == 0.0
    assert float(invoice.igst_amount or 0) == 450.0
    assert float(invoice.grand_total) == 2950.0


@pytest.mark.unit
def test_create_invoice_gst_requires_tax_rate_for_taxable_line(db_session, seed_roles):
    company = create_company(db_session, name="GST Co 3")
    company.gstin = "27ABCDE1234F1Z5"
    company.state = "Maharashtra"
    db_session.commit()
    user = create_user(db_session, username="owner_gst_3", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")

    with pytest.raises(HTTPException) as exc:
        create_invoice(
            db_session,
            user,
            InvoiceType.SALES,
            {
                "invoice_no": "GST-3",
                "invoice_date": datetime.utcnow(),
                "tax_mode": TaxMode.GST,
                "company_snapshot_json": {"state": "Maharashtra", "state_code": "27", "gstin": company.gstin},
                "customer_snapshot_json": {"name": "Buyer", "gstin": "27AAACB1234C1Z9", "state": "Maharashtra", "state_code": "27"},
                "lines": [{"description": "Taxable Item", "qty": 1, "price": 2500, "taxable": True}],
            },
        )


@pytest.mark.unit
def test_create_invoice_gst_positive_rate_overrides_false_taxable_flag(db_session, seed_roles):
    company = create_company(db_session, name="GST Co 4")
    company.gstin = "27ABCDE1234F1Z5"
    company.state = "Maharashtra"
    db_session.commit()
    user = create_user(db_session, username="owner_gst_4", password="Pass@1234", company_id=company.id, role_code="SUPER_ADMIN")

    invoice = create_invoice(
        db_session,
        user,
        InvoiceType.SALES,
        {
            "invoice_no": "GST-4",
            "invoice_date": datetime.utcnow(),
            "tax_mode": TaxMode.GST,
            "company_snapshot_json": {"state": "Maharashtra", "state_code": "27", "gstin": company.gstin},
            "customer_snapshot_json": {"name": "Buyer", "gstin": "27AAACB1234C1Z9", "state": "Maharashtra", "state_code": "27"},
            "lines": [{"description": "Taxable Item", "qty": 1, "price": 200, "tax_rate": 18, "taxable": False}],
        },
    )

    assert float(invoice.subtotal) == 200.0
    assert float(invoice.tax_total) == 36.0
    assert float(invoice.cgst_amount or 0) == 18.0
    assert float(invoice.sgst_amount or 0) == 18.0
    assert float(invoice.grand_total) == 236.0
