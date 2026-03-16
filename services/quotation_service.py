from __future__ import annotations

from datetime import datetime
import re

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db.models import (
    InvoiceType,
    Product,
    Quotation,
    QuotationLine,
    QuotationLineType,
    QuotationPartyType,
    QuotationStatus,
    TaxMode,
    User,
)
from app.services.invoice_service import create_invoice, generate_next_invoice_no


def generate_next_quotation_no(db: Session, company_id: str) -> str:
    last = (
        db.query(Quotation)
        .filter(Quotation.company_id == company_id)
        .order_by(Quotation.created_at.desc())
        .first()
    )
    default_prefix = "Q-"
    if not last or not last.quotation_no:
        return f"{default_prefix}0001"

    match = re.search(r"(.*?)(\d+)$", last.quotation_no)
    if not match:
        return f"{default_prefix}0001"

    prefix, digits = match.groups()
    next_value = str(int(digits) + 1).zfill(len(digits))
    return f"{prefix}{next_value}"


def _coerce_line_type(raw: str | QuotationLineType | None) -> QuotationLineType:
    if isinstance(raw, QuotationLineType):
        return raw
    if not raw:
        return QuotationLineType.PRODUCT
    try:
        return QuotationLineType(raw)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid quotation line type")


def _compute_line_total(qty: float, price: float, discount_percent: float) -> float:
    gross = round(qty * price, 2)
    discount_amount = round(gross * (discount_percent / 100.0), 2) if discount_percent else 0.0
    return round(gross - discount_amount, 2)


def _build_lines(
    db: Session,
    user: User,
    lines: list[dict],
) -> tuple[list[QuotationLine], float]:
    if not lines:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one line is required")

    subtotal = 0.0
    rows: list[QuotationLine] = []
    product_cache: dict[str, Product] = {}

    for idx, line in enumerate(lines):
        line_type = _coerce_line_type(line.get("line_type"))
        product_id = line.get("product_id")
        product = None
        if product_id:
            product = product_cache.get(product_id)
            if not product:
                product = db.get(Product, product_id)
                if not product or product.company_id != user.company_id:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid product")
                product_cache[product_id] = product

        qty_raw = line.get("qty")
        qty = float(qty_raw) if qty_raw is not None else 0.0
        if line_type == QuotationLineType.DESCRIPTION and qty <= 0:
            qty = 1.0

        price_raw = line.get("price")
        price = float(price_raw) if price_raw is not None else 0.0
        discount_raw = line.get("discount_percent")
        discount_percent = float(discount_raw) if discount_raw is not None else 0.0
        if discount_percent < 0 or discount_percent > 100:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid discount percent")

        if line_type == QuotationLineType.DESCRIPTION:
            price = 0.0
            discount_percent = 0.0
            line_total = 0.0
        else:
            line_total = _compute_line_total(qty, price, discount_percent)
            subtotal += line_total

        rows.append(
            QuotationLine(
                line_order=idx,
                line_type=line_type,
                product_id=product_id,
                description=line.get("description") or (product.name if product else ""),
                qty=qty,
                unit=line.get("unit"),
                price=price,
                discount_percent=discount_percent,
                line_total=line_total,
            )
        )

    return rows, subtotal


def create_quotation(db: Session, user: User, payload: dict) -> Quotation:
    existing = (
        db.query(Quotation)
        .filter(Quotation.company_id == user.company_id, Quotation.quotation_no == payload.get("quotation_no"))
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Duplicate quotation number")

    lines_payload = payload.get("lines") or []
    lines, subtotal = _build_lines(db, user, lines_payload)

    party_type_raw = payload.get("party_type")
    party_type = None
    if party_type_raw:
        party_type = QuotationPartyType(party_type_raw)
    elif payload.get("supplier_id"):
        party_type = QuotationPartyType.SUPPLIER
    else:
        party_type = QuotationPartyType.CUSTOMER

    quotation = Quotation(
        company_id=user.company_id,
        quotation_no=payload.get("quotation_no"),
        quotation_date=payload.get("quotation_date") or datetime.utcnow(),
        valid_until=payload.get("valid_until"),
        status=QuotationStatus(payload.get("status") or QuotationStatus.DRAFT),
        party_type=party_type,
        customer_id=payload.get("customer_id") if party_type == QuotationPartyType.CUSTOMER else None,
        customer_snapshot_json=payload.get("customer_snapshot_json") if party_type == QuotationPartyType.CUSTOMER else None,
        supplier_id=payload.get("supplier_id") if party_type == QuotationPartyType.SUPPLIER else None,
        supplier_snapshot_json=payload.get("supplier_snapshot_json") if party_type == QuotationPartyType.SUPPLIER else None,
        company_snapshot_json=payload.get("company_snapshot_json"),
        salesperson=payload.get("salesperson"),
        notes=payload.get("notes"),
        terms=payload.get("terms"),
        revision_of_id=payload.get("revision_of_id"),
        revision_no=int(payload.get("revision_no") or 1),
        subtotal=subtotal,
        grand_total=subtotal,
        created_by=user.id,
    )
    db.add(quotation)
    db.flush()

    for line in lines:
        line.quotation_id = quotation.id
        db.add(line)

    db.commit()
    db.refresh(quotation)
    return quotation


def update_quotation(db: Session, user: User, quotation: Quotation, payload: dict) -> Quotation:
    if quotation.status in (QuotationStatus.CONVERTED, QuotationStatus.CANCELLED):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot edit converted/cancelled quotation")

    updates = payload.copy()
    if "quotation_no" in updates and updates["quotation_no"]:
        existing = (
            db.query(Quotation)
            .filter(
                Quotation.company_id == user.company_id,
                Quotation.quotation_no == updates["quotation_no"],
                Quotation.id != quotation.id,
            )
            .first()
        )
        if existing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Duplicate quotation number")

    if "status" in updates and updates["status"]:
        next_status = QuotationStatus(updates["status"])
        allowed = {
            QuotationStatus.DRAFT: {QuotationStatus.SENT, QuotationStatus.CONFIRMED, QuotationStatus.CANCELLED},
            QuotationStatus.SENT: {QuotationStatus.CONFIRMED, QuotationStatus.CANCELLED},
            QuotationStatus.CONFIRMED: {QuotationStatus.CANCELLED},
            QuotationStatus.CANCELLED: set(),
            QuotationStatus.CONVERTED: set(),
        }
        if next_status != quotation.status and next_status not in allowed.get(quotation.status, set()):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status transition")
        updates["status"] = next_status

    party_type_raw = updates.get("party_type")
    if party_type_raw:
        updates["party_type"] = QuotationPartyType(party_type_raw)
    elif updates.get("supplier_id"):
        updates["party_type"] = QuotationPartyType.SUPPLIER
    elif updates.get("customer_id"):
        updates["party_type"] = QuotationPartyType.CUSTOMER

    if updates.get("party_type") == QuotationPartyType.SUPPLIER:
        updates["customer_id"] = None
        updates["customer_snapshot_json"] = None
    elif updates.get("party_type") == QuotationPartyType.CUSTOMER:
        updates["supplier_id"] = None
        updates["supplier_snapshot_json"] = None

    lines_payload = updates.pop("lines", None)
    if lines_payload is not None:
        lines, subtotal = _build_lines(db, user, lines_payload)
        db.query(QuotationLine).filter(QuotationLine.quotation_id == quotation.id).delete()
        for line in lines:
            line.quotation_id = quotation.id
            db.add(line)
        quotation.subtotal = subtotal
        quotation.grand_total = subtotal

    for field, value in updates.items():
        setattr(quotation, field, value)

    quotation.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(quotation)
    return quotation


def duplicate_quotation(db: Session, user: User, quotation: Quotation) -> Quotation:
    next_no = generate_next_quotation_no(db, user.company_id)
    new_payload = {
        "quotation_no": next_no,
        "quotation_date": datetime.utcnow(),
        "valid_until": quotation.valid_until,
        "status": QuotationStatus.DRAFT,
        "party_type": quotation.party_type,
        "customer_id": quotation.customer_id,
        "customer_snapshot_json": quotation.customer_snapshot_json,
        "supplier_id": quotation.supplier_id,
        "supplier_snapshot_json": quotation.supplier_snapshot_json,
        "company_snapshot_json": quotation.company_snapshot_json,
        "salesperson": quotation.salesperson,
        "notes": quotation.notes,
        "terms": quotation.terms,
        "revision_of_id": quotation.id,
        "revision_no": int(quotation.revision_no or 1) + 1,
    }
    lines = [
        {
            "line_type": line.line_type,
            "product_id": line.product_id,
            "description": line.description,
            "qty": float(line.qty),
            "unit": line.unit,
            "price": float(line.price),
            "discount_percent": float(line.discount_percent or 0),
        }
        for line in quotation.lines
    ]
    new_payload["lines"] = lines
    return create_quotation(db, user, new_payload)


def delete_quotation(db: Session, quotation: Quotation) -> None:
    if quotation.status == QuotationStatus.CONVERTED or quotation.converted_invoice_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Converted quotations cannot be deleted")

    db.query(QuotationLine).filter(QuotationLine.quotation_id == quotation.id).delete()
    db.delete(quotation)
    db.commit()


def convert_to_sale(
    db: Session,
    user: User,
    quotation: Quotation,
    tax_mode: TaxMode,
    is_interstate: bool = False,
    invoice_date: datetime | None = None,
    payment_mode: str | None = None,
    payment_reference: str | None = None,
) -> str:
    if quotation.party_type == QuotationPartyType.SUPPLIER:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Supplier quotations cannot be converted to sales")
    if quotation.status == QuotationStatus.CONVERTED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Quotation already converted")
    if quotation.status == QuotationStatus.CANCELLED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot convert cancelled quotation")

    invoice_no = generate_next_invoice_no(db, user.company_id, InvoiceType.SALES)
    lines = []
    product_cache: dict[str, Product] = {}

    for line in quotation.lines:
        product = None
        if line.product_id:
            product = product_cache.get(line.product_id)
            if not product:
                product = db.get(Product, line.product_id)
                if product:
                    product_cache[line.product_id] = product
        hsn = product.hsn if (product and tax_mode == TaxMode.GST) else None
        lines.append(
            {
                "product_id": line.product_id,
                "description": line.description,
                "hsn": hsn,
                "qty": float(line.qty or 0) if line.line_type == QuotationLineType.PRODUCT else 1,
                "unit": line.unit,
                "price": float(line.price or 0),
                "discount_percent": float(line.discount_percent or 0),
                "taxable": bool(product.taxable) if product else True,
                "tax_rate": float(product.tax_rate) if product and product.tax_rate is not None else None,
            }
        )

    payload = {
        "invoice_no": invoice_no,
        "invoice_date": invoice_date or datetime.utcnow(),
        "tax_mode": tax_mode,
        "is_interstate": is_interstate,
        "customer_id": quotation.customer_id,
        "customer_snapshot_json": quotation.customer_snapshot_json,
        "company_snapshot_json": quotation.company_snapshot_json,
        "lines": lines,
        "payment_mode": payment_mode,
        "payment_reference": payment_reference,
        "source_quotation_id": quotation.id,
        "source_quotation_no": quotation.quotation_no,
    }

    invoice = create_invoice(db, user, InvoiceType.SALES, payload)

    quotation.status = QuotationStatus.CONVERTED
    quotation.converted_invoice_id = invoice.id
    quotation.converted_at = datetime.utcnow()
    quotation.updated_at = datetime.utcnow()
    db.commit()

    return invoice.id
