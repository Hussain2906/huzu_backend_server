from datetime import datetime
from typing import List

from sqlalchemy.orm import Session

from app.db.models import JournalLine, JournalVoucher, LedgerType, Invoice, InvoiceType, TaxMode
from app.services.accounting.ledger_service import ensure_default_ledgers


def create_voucher(db: Session, company_id: str, voucher_type: str, number: str, date: datetime, lines: List[dict], narration: str | None, ref_type: str | None, ref_id: str | None, user_id: str | None = None) -> JournalVoucher:
    voucher = JournalVoucher(
        company_id=company_id,
        voucher_type=voucher_type,
        number=number,
        date=date,
        narration=narration,
        ref_type=ref_type,
        ref_id=ref_id,
        created_by=user_id,
    )
    db.add(voucher)
    db.flush()

    for ln in lines:
        db.add(
            JournalLine(
                voucher_id=voucher.id,
                ledger_id=ln["ledger_id"],
                dr=ln.get("dr", 0),
                cr=ln.get("cr", 0),
                line_ref=ln.get("line_ref"),
            )
        )
    db.commit()
    db.refresh(voucher)
    return voucher


def auto_post_invoice(db: Session, invoice: Invoice) -> JournalVoucher:
    ledgers = ensure_default_ledgers(db, invoice.company_id)

    ar = ledgers["1200"]
    ap = ledgers["2100"]
    sales = ledgers["4100"]
    purchases = ledgers["5100"]
    cogs = ledgers["5200"]
    inventory = ledgers["5300"]
    output_gst = ledgers["5400"]
    input_gst = ledgers["5500"]
    rounding = ledgers["5600"]

    # Build lines
    lines: List[dict] = []
    if invoice.invoice_type == InvoiceType.SALES:
        lines.append({"ledger_id": ar.id, "dr": float(invoice.grand_total), "cr": 0, "line_ref": invoice.invoice_no})
        lines.append({"ledger_id": sales.id, "dr": 0, "cr": float(invoice.subtotal), "line_ref": invoice.invoice_no})
        if float(invoice.tax_total) > 0:
            lines.append({"ledger_id": output_gst.id, "dr": 0, "cr": float(invoice.tax_total), "line_ref": invoice.invoice_no})
        if float(invoice.round_off) != 0:
            if invoice.round_off > 0:
                lines.append({"ledger_id": rounding.id, "dr": float(invoice.round_off), "cr": 0})
            else:
                lines.append({"ledger_id": rounding.id, "dr": 0, "cr": abs(float(invoice.round_off))})
        # COGS/Inventory move
        lines.append({"ledger_id": cogs.id, "dr": float(invoice.subtotal), "cr": 0})
        lines.append({"ledger_id": inventory.id, "dr": 0, "cr": float(invoice.subtotal)})
    else:
        # Purchase
        lines.append({"ledger_id": purchases.id, "dr": float(invoice.subtotal), "cr": 0, "line_ref": invoice.invoice_no})
        if float(invoice.tax_total) > 0:
            lines.append({"ledger_id": input_gst.id, "dr": float(invoice.tax_total), "cr": 0, "line_ref": invoice.invoice_no})
        if float(invoice.round_off) != 0:
            if invoice.round_off > 0:
                lines.append({"ledger_id": rounding.id, "dr": 0, "cr": float(invoice.round_off)})
            else:
                lines.append({"ledger_id": rounding.id, "dr": abs(float(invoice.round_off)), "cr": 0})
        lines.append({"ledger_id": ap.id, "dr": 0, "cr": float(invoice.grand_total), "line_ref": invoice.invoice_no})
        # Inventory increase mirrored by liability already captured; skip COGS move here.
        lines.append({"ledger_id": inventory.id, "dr": float(invoice.subtotal), "cr": 0})
        lines.append({"ledger_id": purchases.id, "dr": 0, "cr": float(invoice.subtotal)})

    total_dr = round(sum(float(l.get("dr", 0)) for l in lines), 2)
    total_cr = round(sum(float(l.get("cr", 0)) for l in lines), 2)
    if abs(total_dr - total_cr) > 0.01:
        # balance with rounding ledger
        diff = total_dr - total_cr
        if diff > 0:
            lines.append({"ledger_id": rounding.id, "dr": 0, "cr": diff})
        else:
            lines.append({"ledger_id": rounding.id, "dr": abs(diff), "cr": 0})

    voucher = create_voucher(
        db=db,
        company_id=invoice.company_id,
        voucher_type="SALES" if invoice.invoice_type == InvoiceType.SALES else "PURCHASE",
        number=f"J-{invoice.invoice_no}",
        date=invoice.invoice_date,
        lines=lines,
        narration=f"Auto-post for invoice {invoice.invoice_no}",
        ref_type="invoice",
        ref_id=invoice.id,
        user_id=invoice.created_by,
    )
    return voucher
