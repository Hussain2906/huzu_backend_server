from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import logging
import re

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.db.models import (
    InventoryLedger,
    Invoice,
    InvoiceLine,
    InvoiceStatus,
    InvoiceType,
    JournalLine,
    JournalVoucher,
    PaymentMode,
    Product,
    StockItem,
    StockReason,
    TaxMode,
    User,
)
from app.services.accounting.voucher_service import auto_post_invoice

logger = logging.getLogger(__name__)


def _round_money(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _state_code_from_gstin(gstin: str | None) -> str | None:
    cleaned = (gstin or "").strip()
    if len(cleaned) >= 2 and cleaned[:2].isdigit():
        return cleaned[:2]
    return None


def _snapshot_state(snapshot: dict | None) -> str | None:
    if not isinstance(snapshot, dict):
        return None
    return (
        snapshot.get("place_of_supply")
        or snapshot.get("state")
        or snapshot.get("gst_state")
        or ((snapshot.get("extra_data") or {}).get("place_of_supply") if isinstance(snapshot.get("extra_data"), dict) else None)
        or ((snapshot.get("extra_data") or {}).get("state") if isinstance(snapshot.get("extra_data"), dict) else None)
    )


def _snapshot_state_code(snapshot: dict | None) -> str | None:
    if not isinstance(snapshot, dict):
        return None
    extra = snapshot.get("extra_data") if isinstance(snapshot.get("extra_data"), dict) else {}
    return (
        snapshot.get("state_code")
        or extra.get("state_code")
        or _state_code_from_gstin(snapshot.get("gstin"))
    )


def _normalized_state_key(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"[^a-z0-9]", "", value.strip().lower())
    return cleaned or None


def resolve_is_interstate(payload: dict, *, require_complete_context: bool = False) -> bool:
    company_state = _snapshot_state(payload.get("company_snapshot_json"))
    party_state = _snapshot_state(payload.get("customer_snapshot_json") or payload.get("supplier_snapshot_json"))
    company_state_code = _snapshot_state_code(payload.get("company_snapshot_json"))
    party_state_code = _snapshot_state_code(payload.get("customer_snapshot_json") or payload.get("supplier_snapshot_json"))
    if company_state_code and party_state_code:
        return company_state_code != party_state_code
    normalized_company_state = _normalized_state_key(company_state)
    normalized_party_state = _normalized_state_key(party_state)
    if normalized_company_state and normalized_party_state:
        return normalized_company_state != normalized_party_state
    if payload.get("is_interstate") is not None:
        return bool(payload.get("is_interstate"))
    if require_complete_context:
        if not (company_state_code or normalized_company_state):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Company state or state code is required for GST invoices",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Party state or place of supply is required for GST invoices",
        )
    return False


def _resolve_line_tax_rate(product: Product | None, line: dict, tax_mode: TaxMode, taxable: bool) -> float:
    if tax_mode != TaxMode.GST or not taxable:
        return 0.0
    tax_rate_raw = line.get("tax_rate")
    if tax_rate_raw is not None:
        rate = float(tax_rate_raw)
    elif product and product.tax_rate is not None:
        rate = float(product.tax_rate)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GST rate required for taxable line",
        )
    if rate < 0 or rate > 100:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid GST rate")
    return _round_money(rate)


def _candidate_line_tax_rate(product: Product | None, line: dict) -> float:
    tax_rate_raw = line.get("tax_rate")
    if tax_rate_raw is not None:
        try:
            return float(tax_rate_raw)
        except Exception:
            return 0.0
    if product and product.tax_rate is not None:
        try:
            return float(product.tax_rate)
        except Exception:
            return 0.0
    return 0.0


def _compute_line_tax_breakdown(taxable_value: float, tax_rate: float, is_interstate: bool) -> tuple[float, float, float, float]:
    if tax_rate <= 0 or taxable_value <= 0:
        return 0.0, 0.0, 0.0, 0.0
    tax_amount = _round_money(taxable_value * (tax_rate / 100.0))
    if is_interstate:
        return tax_amount, 0.0, 0.0, tax_amount
    cgst_amount = _round_money(tax_amount / 2)
    sgst_amount = _round_money(tax_amount - cgst_amount)
    return tax_amount, cgst_amount, sgst_amount, 0.0


def _derive_invoice_rate(lines: list[InvoiceLine], is_interstate: bool) -> tuple[float | None, float | None, float | None]:
    taxable_rates = sorted({float(line.tax_rate or 0) for line in lines if float(line.tax_amount or 0) > 0 and float(line.tax_rate or 0) > 0})
    if len(taxable_rates) != 1:
        return None, None, None
    rate = taxable_rates[0]
    if is_interstate:
        return None, None, _round_money(rate)
    half_rate = _round_money(rate / 2)
    return half_rate, half_rate, None


def _prepare_invoice_lines(
    db: Session,
    user: User,
    invoice_type: InvoiceType,
    tax_mode: TaxMode,
    lines: list[dict],
    *,
    is_interstate: bool,
) -> tuple[list[InvoiceLine], dict[str, Product], float, float, float | None, float | None, float | None]:
    subtotal = 0.0
    tax_total = 0.0
    cgst_amount = 0.0
    sgst_amount = 0.0
    igst_amount = 0.0
    invoice_lines: list[InvoiceLine] = []
    product_cache: dict[str, Product] = {}

    for line in lines:
        product = None
        product_id = line.get("product_id")
        if product_id:
            product = product_cache.get(product_id)
            if not product:
                product = db.get(Product, product_id)
                if not product or product.company_id != user.company_id:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid product")
                product_cache[product_id] = product

        qty = float(line.get("qty", 0))
        price = float(line.get("price", 0))
        discount_raw = line.get("discount_percent")
        discount_percent = float(discount_raw) if discount_raw is not None else 0.0
        if discount_percent < 0 or discount_percent > 100:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid discount percent")

        taxable_raw = line.get("taxable")
        taxable = bool(taxable_raw) if taxable_raw is not None else (bool(product.taxable) if product else True)
        if tax_mode == TaxMode.GST and _candidate_line_tax_rate(product, line) > 0:
            taxable = True
        tax_rate = _resolve_line_tax_rate(product, line, tax_mode, taxable)

        gross_total = _round_money(qty * price)
        discount_amount = _round_money(gross_total * (discount_percent / 100.0)) if discount_percent else 0.0
        line_total = _round_money(gross_total - discount_amount)
        line_tax, line_cgst, line_sgst, line_igst = _compute_line_tax_breakdown(line_total, tax_rate, is_interstate)

        subtotal = _round_money(subtotal + line_total)
        tax_total = _round_money(tax_total + line_tax)
        cgst_amount = _round_money(cgst_amount + line_cgst)
        sgst_amount = _round_money(sgst_amount + line_sgst)
        igst_amount = _round_money(igst_amount + line_igst)

        allow_hsn = not (invoice_type == InvoiceType.SALES and tax_mode != TaxMode.GST)
        invoice_lines.append(
            InvoiceLine(
                product_id=product_id,
                description=line.get("description") or "",
                hsn=line.get("hsn") if allow_hsn else None,
                qty=qty,
                unit=line.get("unit"),
                price=price,
                discount_percent=discount_percent,
                taxable=taxable,
                tax_rate=tax_rate if tax_mode == TaxMode.GST else 0,
                line_total=line_total,
                tax_amount=line_tax,
            )
        )

    if cgst_amount <= 0:
        cgst_amount = None
    if sgst_amount <= 0:
        sgst_amount = None
    if igst_amount <= 0:
        igst_amount = None

    return invoice_lines, product_cache, subtotal, tax_total, cgst_amount, sgst_amount, igst_amount


def generate_next_invoice_no(db: Session, company_id: str, invoice_type: InvoiceType) -> str:
    last = (
        db.query(Invoice)
        .filter(Invoice.company_id == company_id, Invoice.invoice_type == invoice_type)
        .order_by(Invoice.created_at.desc())
        .first()
    )
    default_prefix = "S" if invoice_type == InvoiceType.SALES else "P"
    if not last or not last.invoice_no:
        return f"{default_prefix}-0001"

    match = re.search(r"(.*?)(\d+)$", last.invoice_no)
    if not match:
        return f"{default_prefix}-0001"

    prefix, digits = match.groups()
    next_value = str(int(digits) + 1).zfill(len(digits))
    return f"{prefix}{next_value}"


def create_invoice(
    db: Session,
    user: User,
    invoice_type: InvoiceType,
    payload: dict,
) -> Invoice:
    existing = (
        db.query(Invoice)
        .filter(
            Invoice.company_id == user.company_id,
            Invoice.invoice_type == invoice_type,
            Invoice.invoice_no == payload.get("invoice_no"),
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Duplicate invoice number")
    lines = payload.get("lines") or []
    if not lines:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one line is required")

    tax_mode_value = payload.get("tax_mode")
    try:
        tax_mode = tax_mode_value if isinstance(tax_mode_value, TaxMode) else TaxMode(tax_mode_value)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tax mode")
    is_interstate = resolve_is_interstate(payload, require_complete_context=(tax_mode == TaxMode.GST))
    invoice_lines, product_cache, subtotal, tax_total, cgst_amount, sgst_amount, igst_amount = _prepare_invoice_lines(
        db,
        user,
        invoice_type,
        tax_mode,
        lines,
        is_interstate=is_interstate,
    )

    round_off = float(payload.get("round_off") or 0)
    grand_total = _round_money(subtotal + tax_total + round_off)
    cgst_rate, sgst_rate, igst_rate = _derive_invoice_rate(invoice_lines, is_interstate)

    payment_mode = payload.get("payment_mode")
    if payment_mode:
        try:
            payment_mode = payment_mode if isinstance(payment_mode, PaymentMode) else PaymentMode(payment_mode)
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payment mode")

    invoice = Invoice(
        company_id=user.company_id,
        invoice_type=invoice_type,
        tax_mode=tax_mode,
        status=InvoiceStatus.POSTED,
        invoice_no=payload.get("invoice_no"),
        invoice_date=payload.get("invoice_date"),
        customer_id=payload.get("customer_id"),
        supplier_id=payload.get("supplier_id"),
        source_quotation_id=payload.get("source_quotation_id"),
        source_quotation_no=payload.get("source_quotation_no"),
        subtotal=subtotal,
        tax_total=tax_total,
        round_off=round_off,
        grand_total=grand_total,
        cgst_rate=cgst_rate,
        sgst_rate=sgst_rate,
        igst_rate=igst_rate,
        cgst_amount=cgst_amount,
        sgst_amount=sgst_amount,
        igst_amount=igst_amount,
        payment_mode=payment_mode,
        payment_reference=payload.get("payment_reference"),
        customer_snapshot_json=payload.get("customer_snapshot_json"),
        supplier_snapshot_json=payload.get("supplier_snapshot_json"),
        company_snapshot_json=payload.get("company_snapshot_json"),
        extra_json=payload.get("invoice_meta"),
        created_by=user.id,
    )
    db.add(invoice)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Duplicate invoice number")

    for line in invoice_lines:
        line.invoice_id = invoice.id
        db.add(line)

        if line.product_id:
            product = product_cache.get(line.product_id)
            if not product:
                product = db.get(Product, line.product_id)
                if not product or product.company_id != user.company_id:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid product")

            stock = (
                db.query(StockItem)
                .filter(StockItem.company_id == user.company_id, StockItem.product_id == product.id)
                .first()
            )
            if not stock:
                stock = StockItem(company_id=user.company_id, product_id=product.id, qty_on_hand=0)
                db.add(stock)
                db.flush()

            qty_change = -line.qty if invoice_type == InvoiceType.SALES else line.qty
            stock.qty_on_hand = float(stock.qty_on_hand) + qty_change
            stock.updated_at = datetime.utcnow()

            db.add(
                InventoryLedger(
                    company_id=user.company_id,
                    product_id=product.id,
                    qty_change=qty_change,
                    reason=StockReason.SALE if invoice_type == InvoiceType.SALES else StockReason.PURCHASE,
                    ref_type="invoice",
                    ref_id=invoice.id,
                    created_by=user.id,
                )
            )

    # Persist invoice and stock effects first so core sales/purchase flow is not blocked
    # by accounting posting issues.
    payment_status_raw = payload.get("payment_status")
    payment_status = str(payment_status_raw or "").strip().upper()
    has_payment = payment_mode is not None
    if invoice_type == InvoiceType.PURCHASE:
        if payment_status in ("UNPAID", "CREDIT"):
            invoice.paid_amount = 0
            invoice.balance_due = invoice.grand_total
        elif payment_status == "PAID" or has_payment:
            invoice.paid_amount = invoice.grand_total
            invoice.balance_due = 0
        else:
            invoice.paid_amount = 0
            invoice.balance_due = invoice.grand_total
    else:
        if has_payment:
            invoice.paid_amount = invoice.grand_total
            invoice.balance_due = 0
        else:
            invoice.paid_amount = 0
            invoice.balance_due = invoice.grand_total
    db.commit()
    db.refresh(invoice)

    # Auto-post to accounting and link voucher in best-effort mode.
    try:
        voucher = auto_post_invoice(db, invoice)
        invoice.voucher_id = voucher.id
        db.commit()
        db.refresh(invoice)
    except Exception:
        db.rollback()
        logger.exception("Auto-post failed for invoice %s (%s)", invoice.id, invoice.invoice_no)

    return invoice


def cancel_invoice(db: Session, user: User, invoice: Invoice) -> Invoice:
    if invoice.status == InvoiceStatus.CANCELLED:
        return invoice

    invoice.status = InvoiceStatus.CANCELLED
    invoice.cancelled_by = user.id
    invoice.cancelled_at = datetime.utcnow()

    lines = db.query(InvoiceLine).filter(InvoiceLine.invoice_id == invoice.id).all()
    for line in lines:
        if not line.product_id:
            continue
        stock = (
            db.query(StockItem)
            .filter(StockItem.company_id == user.company_id, StockItem.product_id == line.product_id)
            .first()
        )
        if not stock:
            stock = StockItem(company_id=user.company_id, product_id=line.product_id, qty_on_hand=0)
            db.add(stock)
            db.flush()

        qty_value = float(line.qty)
        qty_change = qty_value if invoice.invoice_type == InvoiceType.SALES else -qty_value
        stock.qty_on_hand = float(stock.qty_on_hand) + qty_change
        stock.updated_at = datetime.utcnow()

        db.add(
            InventoryLedger(
                company_id=user.company_id,
                product_id=line.product_id,
                qty_change=qty_change,
                reason=StockReason.CANCEL,
                ref_type="invoice",
                ref_id=invoice.id,
                created_by=user.id,
            )
        )

    return invoice


def update_invoice(
    db: Session,
    user: User,
    invoice: Invoice,
    payload: dict,
) -> Invoice:
    if invoice.status == InvoiceStatus.CANCELLED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cancelled invoice cannot be updated")

    if invoice.invoice_type == InvoiceType.SALES:
        has_returns = (
            db.query(InventoryLedger.id)
            .filter(
                InventoryLedger.company_id == user.company_id,
                InventoryLedger.ref_id == invoice.id,
                InventoryLedger.ref_type == "sale_return",
            )
            .first()
            is not None
        )
        if has_returns:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invoice with sales return cannot be edited",
            )

    existing = (
        db.query(Invoice)
        .filter(
            Invoice.company_id == user.company_id,
            Invoice.invoice_type == invoice.invoice_type,
            Invoice.invoice_no == payload.get("invoice_no"),
            Invoice.id != invoice.id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Duplicate invoice number")

    existing_lines = db.query(InvoiceLine).filter(InvoiceLine.invoice_id == invoice.id).all()
    for line in existing_lines:
        if not line.product_id:
            continue
        stock = (
            db.query(StockItem)
            .filter(StockItem.company_id == user.company_id, StockItem.product_id == line.product_id)
            .first()
        )
        if not stock:
            stock = StockItem(company_id=user.company_id, product_id=line.product_id, qty_on_hand=0)
            db.add(stock)
            db.flush()
        qty_change = float(line.qty) if invoice.invoice_type == InvoiceType.SALES else -float(line.qty)
        stock.qty_on_hand = float(stock.qty_on_hand) + qty_change
        stock.updated_at = datetime.utcnow()

    db.query(InventoryLedger).filter(
        InventoryLedger.company_id == user.company_id,
        InventoryLedger.ref_type == "invoice",
        InventoryLedger.ref_id == invoice.id,
    ).delete()
    db.query(InvoiceLine).filter(InvoiceLine.invoice_id == invoice.id).delete()
    if invoice.voucher_id:
        db.query(JournalLine).filter(JournalLine.voucher_id == invoice.voucher_id).delete()
        db.query(JournalVoucher).filter(JournalVoucher.id == invoice.voucher_id).delete()
        invoice.voucher_id = None
    db.flush()

    lines = payload.get("lines") or []
    if not lines:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one line is required")

    tax_mode_value = payload.get("tax_mode")
    try:
        tax_mode = tax_mode_value if isinstance(tax_mode_value, TaxMode) else TaxMode(tax_mode_value)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tax mode")
    is_interstate = resolve_is_interstate(payload, require_complete_context=(tax_mode == TaxMode.GST))
    invoice_lines, product_cache, subtotal, tax_total, cgst_amount, sgst_amount, igst_amount = _prepare_invoice_lines(
        db,
        user,
        invoice.invoice_type,
        tax_mode,
        lines,
        is_interstate=is_interstate,
    )
    for line in invoice_lines:
        line.invoice_id = invoice.id

    round_off = float(payload.get("round_off") or 0)
    grand_total = _round_money(subtotal + tax_total + round_off)
    cgst_rate, sgst_rate, igst_rate = _derive_invoice_rate(invoice_lines, is_interstate)

    payment_mode = payload.get("payment_mode")
    if payment_mode:
        try:
            payment_mode = payment_mode if isinstance(payment_mode, PaymentMode) else PaymentMode(payment_mode)
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payment mode")

    invoice.tax_mode = tax_mode
    invoice.invoice_no = payload.get("invoice_no")
    invoice.invoice_date = payload.get("invoice_date")
    invoice.customer_id = payload.get("customer_id")
    invoice.supplier_id = payload.get("supplier_id")
    invoice.source_quotation_id = payload.get("source_quotation_id")
    invoice.source_quotation_no = payload.get("source_quotation_no")
    invoice.subtotal = subtotal
    invoice.tax_total = tax_total
    invoice.round_off = round_off
    invoice.grand_total = grand_total
    invoice.cgst_rate = cgst_rate
    invoice.sgst_rate = sgst_rate
    invoice.igst_rate = igst_rate
    invoice.cgst_amount = cgst_amount
    invoice.sgst_amount = sgst_amount
    invoice.igst_amount = igst_amount
    invoice.payment_mode = payment_mode
    invoice.payment_reference = payload.get("payment_reference")
    invoice.customer_snapshot_json = payload.get("customer_snapshot_json")
    invoice.supplier_snapshot_json = payload.get("supplier_snapshot_json")
    invoice.company_snapshot_json = payload.get("company_snapshot_json")
    invoice.extra_json = payload.get("invoice_meta")
    invoice.updated_at = datetime.utcnow()

    for line in invoice_lines:
        db.add(line)
        if line.product_id:
            product = product_cache.get(line.product_id)
            if not product:
                product = db.get(Product, line.product_id)
                if not product or product.company_id != user.company_id:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid product")

            stock = (
                db.query(StockItem)
                .filter(StockItem.company_id == user.company_id, StockItem.product_id == product.id)
                .first()
            )
            if not stock:
                stock = StockItem(company_id=user.company_id, product_id=product.id, qty_on_hand=0)
                db.add(stock)
                db.flush()

            qty_change = -line.qty if invoice.invoice_type == InvoiceType.SALES else line.qty
            stock.qty_on_hand = float(stock.qty_on_hand) + qty_change
            stock.updated_at = datetime.utcnow()

            db.add(
                InventoryLedger(
                    company_id=user.company_id,
                    product_id=product.id,
                    qty_change=qty_change,
                    reason=StockReason.SALE if invoice.invoice_type == InvoiceType.SALES else StockReason.PURCHASE,
                    ref_type="invoice",
                    ref_id=invoice.id,
                    created_by=user.id,
                )
            )

    db.flush()
    voucher = auto_post_invoice(db, invoice)
    invoice.voucher_id = voucher.id
    if payment_mode:
        invoice.paid_amount = invoice.grand_total
        invoice.balance_due = 0
    else:
        invoice.paid_amount = 0
        invoice.balance_due = invoice.grand_total

    db.commit()
    db.refresh(invoice)
    return invoice


def return_sales_items(
    db: Session,
    user: User,
    invoice: Invoice,
    lines: list[dict],
    notes: str | None = None,
) -> None:
    if invoice.invoice_type != InvoiceType.SALES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid invoice type")
    if invoice.status == InvoiceStatus.CANCELLED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cancelled invoices cannot accept returns")
    if not lines:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select at least one return line")

    invoice_lines = (
        db.query(InvoiceLine)
        .filter(InvoiceLine.invoice_id == invoice.id)
        .all()
    )
    sold_by_product: dict[str, float] = {}
    for line in invoice_lines:
        if not line.product_id:
            continue
        sold_by_product[line.product_id] = sold_by_product.get(line.product_id, 0.0) + float(line.qty or 0)

    returned_rows = (
        db.query(InventoryLedger)
        .filter(
            InventoryLedger.company_id == user.company_id,
            InventoryLedger.ref_type == "sale_return",
            InventoryLedger.ref_id == invoice.id,
        )
        .all()
    )
    returned_by_product: dict[str, float] = {}
    for row in returned_rows:
        returned_by_product[row.product_id] = returned_by_product.get(row.product_id, 0.0) + float(row.qty_change or 0)

    for line in lines:
        product_id = line.get("product_id")
        qty = float(line.get("qty") or 0)
        if not product_id or qty <= 0:
            continue
        sold_qty = sold_by_product.get(product_id, 0.0)
        if sold_qty <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid return line product")
        returned_qty = returned_by_product.get(product_id, 0.0)
        remaining = sold_qty - returned_qty
        if qty > remaining:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Return quantity exceeds sold quantity")

        stock = (
            db.query(StockItem)
            .filter(StockItem.company_id == user.company_id, StockItem.product_id == product_id)
            .first()
        )
        if not stock:
            stock = StockItem(company_id=user.company_id, product_id=product_id, qty_on_hand=0)
            db.add(stock)
            db.flush()

        stock.qty_on_hand = float(stock.qty_on_hand) + qty
        stock.updated_at = datetime.utcnow()

        db.add(
            InventoryLedger(
                company_id=user.company_id,
                product_id=product_id,
                qty_change=qty,
                reason=StockReason.RETURN,
                ref_type="sale_return",
                ref_id=invoice.id,
                notes=notes,
                created_by=user.id,
            )
        )
