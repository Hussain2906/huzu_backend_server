from datetime import datetime
from sqlalchemy.orm import Session

from app.db.models import Payment, PaymentMode, PaymentAllocation, Invoice, InvoiceType
from app.services.accounting.ledger_service import ledger_map
from app.services.accounting.voucher_service import create_voucher


def create_payment(db: Session, company_id: str, payload: dict) -> Payment:
    mode = PaymentMode(payload["mode"])
    payment = Payment(
        company_id=company_id,
        counterparty_type=payload.get("counterparty_type"),
        counterparty_id=payload.get("counterparty_id"),
        mode=mode,
        amount=payload.get("amount"),
        ref_no=payload.get("ref_no"),
        ref_date=payload.get("ref_date"),
        notes=payload.get("notes"),
        status="POSTED",
    )
    db.add(payment)
    db.commit()
    return payment


def allocate_payment(db: Session, payment_id: str, company_id: str, allocations: list[dict]) -> list[PaymentAllocation]:
    payment = db.get(Payment, payment_id)
    if not payment or payment.company_id != company_id:
        raise ValueError("Payment not found")

    ledgers = ledger_map(db, company_id)
    ar = ledgers["1200"]
    ap = ledgers["2100"]
    cash_bank = ledgers["1000"]  # using cash ledger as default receipt/payment bucket

    alloc_rows = []
    for alloc in allocations:
        invoice = db.get(Invoice, alloc["invoice_id"])
        if not invoice or invoice.company_id != company_id:
            raise ValueError("Invoice not found")
        if invoice.invoice_type not in (InvoiceType.SALES, InvoiceType.PURCHASE):
            raise ValueError("Only sales/purchase invoices allocatable")
        row = PaymentAllocation(payment_id=payment.id, invoice_id=invoice.id, amount_applied=alloc["amount"])
        db.add(row)
        alloc_rows.append(row)

        # update invoice balances
        invoice.paid_amount = float(invoice.paid_amount) + float(alloc["amount"])
        invoice.balance_due = float(invoice.grand_total) - float(invoice.paid_amount)

        # create accounting voucher for receipt/payment
        if invoice.invoice_type == InvoiceType.SALES:
            lines = [
                {"ledger_id": cash_bank.id, "dr": float(alloc["amount"]), "cr": 0},
                {"ledger_id": ar.id, "dr": 0, "cr": float(alloc["amount"]), "line_ref": invoice.invoice_no},
            ]
            vtype = "RECEIPT"
            number = f"RC-{payment.id[:6]}"
        else:
            lines = [
                {"ledger_id": ap.id, "dr": float(alloc["amount"]), "cr": 0, "line_ref": invoice.invoice_no},
                {"ledger_id": cash_bank.id, "dr": 0, "cr": float(alloc["amount"])},
            ]
            vtype = "PAYMENT"
            number = f"PM-{payment.id[:6]}"

        voucher = create_voucher(
            db=db,
            company_id=company_id,
            voucher_type=vtype,
            number=number,
            date=payment.ref_date or payment.created_at,
            lines=lines,
            narration=f"Payment allocation for {invoice.invoice_no}",
            ref_type="payment",
            ref_id=payment.id,
            user_id=None,
        )
        invoice.voucher_id = invoice.voucher_id or voucher.id

    db.commit()
    return alloc_rows
