from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db, is_company_super_admin, require_sales_access
from app.db.models import Company, CompanyProfile, Customer, Supplier, Invoice, InvoiceLine, InvoiceStatus, InvoiceType, PaymentMode, TaxMode, User
from app.services.invoice_document_service import (
    build_simple_receipt_pdf,
    build_tax_invoice_pdf,
    render_simple_receipt_html,
    render_tax_invoice_html,
)
from app.services.pdf_service import build_text_pdf
from app.services.receipt_settings_service import get_receipt_settings
from app.services.invoice_service import (
    cancel_invoice,
    create_invoice,
    generate_next_invoice_no,
    resolve_is_interstate,
    return_sales_items,
    update_invoice,
)

router = APIRouter(prefix="/v1/sales", tags=["sales"])


class LineIn(BaseModel):
    product_id: str | None = None
    description: str
    hsn: str | None = None
    qty: float
    unit: str | None = None
    price: float
    discount_percent: float | None = None
    taxable: bool = True
    tax_rate: float | None = None


class InvoiceCreate(BaseModel):
    invoice_no: str = Field(min_length=1)
    invoice_date: datetime
    tax_mode: TaxMode
    is_interstate: bool = False
    customer_id: str | None = None
    customer_snapshot_json: dict | None = None
    supplier_id: str | None = None
    supplier_snapshot_json: dict | None = None
    company_snapshot_json: dict | None = None

    lines: list[LineIn]

    round_off: float | None = None
    payment_mode: PaymentMode | None = None
    payment_reference: str | None = None
    invoice_meta: dict | None = None


class InvoiceOut(BaseModel):
    id: str
    invoice_no: str
    invoice_date: datetime
    tax_mode: TaxMode
    status: str
    subtotal: float
    tax_total: float
    grand_total: float
    paid_amount: float
    balance_due: float
    payment_mode: PaymentMode | None = None
    payment_reference: str | None = None
    source_quotation_no: str | None = None
    customer_id: str | None = None
    supplier_id: str | None = None


class InvoiceLineOut(BaseModel):
    id: str
    product_id: str | None = None
    description: str
    hsn: str | None = None
    qty: float
    unit: str | None = None
    price: float
    discount_percent: float | None = None
    taxable: bool
    tax_rate: float | None = None
    line_total: float
    tax_amount: float


class PartyOut(BaseModel):
    name: str
    phone: str | None = None
    gstin: str | None = None
    address: str | None = None
    email: str | None = None
    business_name: str | None = None
    pan: str | None = None
    state: str | None = None
    state_code: str | None = None
    pincode: str | None = None
    extra_data: dict | None = None


class CompanyInvoiceOut(BaseModel):
    name: str
    gstin: str | None = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    business_name: str | None = None
    extra_data: dict | None = None


class TaxSummaryRowOut(BaseModel):
    hsn: str | None = None
    taxable_value: float
    central_tax_rate: float | None = None
    central_tax_amount: float | None = None
    state_tax_rate: float | None = None
    state_tax_amount: float | None = None
    integrated_tax_rate: float | None = None
    integrated_tax_amount: float | None = None
    total_tax_amount: float


class InvoiceDetailOut(InvoiceOut):
    company: CompanyInvoiceOut | None = None
    customer: PartyOut | None = None
    supplier: PartyOut | None = None
    lines: list[InvoiceLineOut]
    cgst_amount: float | None = None
    sgst_amount: float | None = None
    igst_amount: float | None = None
    total_items: int | None = None
    total_quantity: float | None = None
    amount_in_words: str | None = None
    tax_amount_in_words: str | None = None
    tax_summary: list[TaxSummaryRowOut] | None = None
    invoice_meta: dict | None = None
    is_interstate: bool | None = None
    place_of_supply: str | None = None


class InvoicePaymentUpdate(BaseModel):
    payment_mode: PaymentMode | None = None
    payment_reference: str | None = None


class NextInvoiceNoOut(BaseModel):
    invoice_no: str


class ReturnLineIn(BaseModel):
    product_id: str
    qty: float


class InvoiceReturnIn(BaseModel):
    lines: list[ReturnLineIn]
    notes: str | None = None


def _get_sales_invoice_or_404(db: Session, user: User, invoice_id: str) -> Invoice:
    invoice = db.get(Invoice, invoice_id)
    if not invoice or invoice.company_id != user.company_id or invoice.invoice_type != InvoiceType.SALES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return invoice


def _resolve_invoice_party(db: Session, invoice: Invoice) -> PartyOut | None:
    if invoice.customer_id:
        customer = db.get(Customer, invoice.customer_id)
        if customer:
            extra = customer.extra_json or {}
            state_code = extra.get("state_code") or (customer.gstin[:2] if customer.gstin and len(customer.gstin) >= 2 and customer.gstin[:2].isdigit() else None)
            return PartyOut(
                name=customer.name,
                phone=customer.phone,
                gstin=customer.gstin,
                address=customer.address,
                email=extra.get("email"),
                business_name=extra.get("business_name"),
                pan=extra.get("pan"),
                state=extra.get("state"),
                state_code=state_code,
                pincode=extra.get("pincode"),
                extra_data=extra,
            )
    elif invoice.customer_snapshot_json:
        snapshot = invoice.customer_snapshot_json
        return PartyOut(
            name=snapshot.get("name", "Customer"),
            phone=snapshot.get("phone"),
            gstin=snapshot.get("gstin"),
            address=snapshot.get("address"),
            email=snapshot.get("email"),
            business_name=snapshot.get("business_name"),
            pan=snapshot.get("pan"),
            state=snapshot.get("state"),
            state_code=snapshot.get("state_code"),
            pincode=snapshot.get("pincode"),
            extra_data=snapshot.get("extra_data") or {},
        )

    if invoice.supplier_id:
        supplier = db.get(Supplier, invoice.supplier_id)
        if supplier:
            extra = dict(supplier.extra_json or {})
            if supplier.business_name:
                extra.setdefault("business_name", supplier.business_name)
            if supplier.state:
                extra.setdefault("state", supplier.state)
            if supplier.pincode:
                extra.setdefault("pincode", supplier.pincode)
            state_code = extra.get("state_code") or (supplier.gstin[:2] if supplier.gstin and len(supplier.gstin) >= 2 and supplier.gstin[:2].isdigit() else None)
            return PartyOut(
                name=supplier.name,
                phone=supplier.phone,
                gstin=supplier.gstin,
                address=supplier.address or supplier.address_line1,
                email=supplier.email,
                business_name=supplier.business_name,
                pan=extra.get("pan"),
                state=supplier.state,
                state_code=state_code,
                pincode=supplier.pincode,
                extra_data=extra,
            )
    elif invoice.supplier_snapshot_json:
        snapshot = invoice.supplier_snapshot_json
        return PartyOut(
            name=snapshot.get("name", "Supplier"),
            phone=snapshot.get("phone"),
            gstin=snapshot.get("gstin"),
            address=snapshot.get("address"),
            email=snapshot.get("email"),
            business_name=snapshot.get("business_name"),
            pan=snapshot.get("pan"),
            state=snapshot.get("state"),
            state_code=snapshot.get("state_code"),
            pincode=snapshot.get("pincode"),
            extra_data=snapshot.get("extra_data") or {},
        )
    return None


def _resolve_company_snapshot(db: Session, invoice: Invoice) -> CompanyInvoiceOut | None:
    snapshot = invoice.company_snapshot_json or {}
    if snapshot:
        return CompanyInvoiceOut(
            name=snapshot.get("name") or snapshot.get("business_name") or "Company",
            gstin=snapshot.get("gstin"),
            phone=snapshot.get("phone"),
            address=snapshot.get("address"),
            city=snapshot.get("city"),
            state=snapshot.get("state"),
            pincode=snapshot.get("pincode"),
            business_name=snapshot.get("business_name"),
            extra_data=snapshot.get("extra_data") or {},
        )

    company = db.get(Company, invoice.company_id)
    profile = db.query(CompanyProfile).filter(CompanyProfile.company_id == invoice.company_id).first()
    if not company:
        return None
    return CompanyInvoiceOut(
        name=company.name,
        gstin=company.gstin,
        phone=company.phone,
        address=company.address,
        city=company.city,
        state=company.state,
        pincode=company.pincode,
        business_name=profile.business_name if profile else company.name,
        extra_data=(profile.extra_json or {}) if profile else {},
    )


def _load_invoice_lines(db: Session, invoice_id: str) -> list[InvoiceLine]:
    return (
        db.query(InvoiceLine)
        .filter(InvoiceLine.invoice_id == invoice_id)
        .order_by(InvoiceLine.id.asc())
        .all()
    )


def _round_money(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _to_words_under_1000(num: int) -> str:
    ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
            "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
    if num < 20:
        return ones[num]
    if num < 100:
        return (tens[num // 10] + (" " + ones[num % 10] if num % 10 else "")).strip()
    return (ones[num // 100] + " Hundred" + (" " + _to_words_under_1000(num % 100) if num % 100 else "")).strip()


def _amount_in_words(amount: float) -> str:
    whole = int(amount)
    paise = int(round((amount - whole) * 100))
    if whole == 0:
        words = "Zero"
    else:
        parts: list[str] = []
        crore = whole // 10000000
        whole %= 10000000
        lakh = whole // 100000
        whole %= 100000
        thousand = whole // 1000
        whole %= 1000
        hundred = whole
        if crore:
            parts.append(f"{_to_words_under_1000(crore)} Crore")
        if lakh:
            parts.append(f"{_to_words_under_1000(lakh)} Lakh")
        if thousand:
            parts.append(f"{_to_words_under_1000(thousand)} Thousand")
        if hundred:
            parts.append(_to_words_under_1000(hundred))
        words = " ".join(part for part in parts if part).strip()
    suffix = " Only"
    if paise:
        suffix = f" and {_to_words_under_1000(paise)} Paise Only"
    return f"INR {words}{suffix}"


def _line_out(line: InvoiceLine) -> InvoiceLineOut:
    return InvoiceLineOut(
        id=line.id,
        product_id=line.product_id,
        description=line.description,
        hsn=line.hsn,
        qty=float(line.qty),
        unit=line.unit,
        price=float(line.price),
        discount_percent=float(line.discount_percent or 0),
        taxable=line.taxable,
        tax_rate=float(line.tax_rate) if line.tax_rate is not None else None,
        line_total=float(line.line_total),
        tax_amount=float(line.tax_amount),
    )


def _tax_summary(lines: list[InvoiceLine], is_interstate: bool) -> list[TaxSummaryRowOut]:
    grouped: dict[tuple[str | None, float], dict[str, float | str | None]] = {}
    for line in lines:
        if not bool(line.taxable) and float(line.tax_amount or 0) <= 0:
            continue
        rate = float(line.tax_rate or 0)
        if rate <= 0 and float(line.tax_amount or 0) <= 0:
            continue
        key = (line.hsn, rate)
        bucket = grouped.setdefault(
            key,
            {
                "hsn": line.hsn,
                "taxable_value": 0.0,
                "rate": rate,
                "tax_amount": 0.0,
            },
        )
        bucket["taxable_value"] = _round_money(float(bucket["taxable_value"]) + float(line.line_total))
        bucket["tax_amount"] = _round_money(float(bucket["tax_amount"]) + float(line.tax_amount))

    rows: list[TaxSummaryRowOut] = []
    for (_, rate), bucket in grouped.items():
        taxable_value = float(bucket["taxable_value"])
        tax_amount = float(bucket["tax_amount"])
        if is_interstate:
            rows.append(
                TaxSummaryRowOut(
                    hsn=bucket["hsn"],
                    taxable_value=taxable_value,
                    integrated_tax_rate=rate,
                    integrated_tax_amount=tax_amount,
                    total_tax_amount=tax_amount,
                )
            )
        else:
            half_rate = _round_money(rate / 2)
            half_tax = _round_money(tax_amount / 2)
            rows.append(
                TaxSummaryRowOut(
                    hsn=bucket["hsn"],
                    taxable_value=taxable_value,
                    central_tax_rate=half_rate,
                    central_tax_amount=half_tax,
                    state_tax_rate=half_rate,
                    state_tax_amount=half_tax,
                    total_tax_amount=tax_amount,
                )
            )
    return rows


def _invoice_meta(invoice: Invoice) -> dict:
    return dict(invoice.extra_json or {})


def _is_interstate(invoice: Invoice) -> bool:
    meta = _invoice_meta(invoice)
    if "is_interstate" in meta:
        return bool(meta.get("is_interstate"))
    return float(invoice.igst_amount or 0) > 0


def _place_of_supply(invoice: Invoice, party: PartyOut | None, company: CompanyInvoiceOut | None) -> str | None:
    meta = _invoice_meta(invoice)
    if meta.get("place_of_supply"):
        return meta.get("place_of_supply")
    if party and isinstance(party.extra_data, dict):
        if party.extra_data.get("place_of_supply"):
            return party.extra_data.get("place_of_supply")
    if party and party.state:
        return party.state
    if company and isinstance(company.extra_data, dict):
        return company.extra_data.get("place_of_supply_default")
    return None


def _build_invoice_detail(db: Session, invoice: Invoice) -> InvoiceDetailOut:
    customer = None
    supplier = None
    party = _resolve_invoice_party(db, invoice)
    if invoice.customer_id or invoice.customer_snapshot_json:
        customer = party
    else:
        supplier = party
    company = _resolve_company_snapshot(db, invoice)
    lines = _load_invoice_lines(db, invoice.id)
    interstate = _is_interstate(invoice)
    total_quantity = sum(float(line.qty or 0) for line in lines)
    invoice_meta = _invoice_meta(invoice)
    invoice_meta.setdefault("is_interstate", interstate)
    return InvoiceDetailOut(
        id=invoice.id,
        invoice_no=invoice.invoice_no,
        invoice_date=invoice.invoice_date,
        tax_mode=invoice.tax_mode,
        status=invoice.status.value,
        subtotal=float(invoice.subtotal),
        tax_total=float(invoice.tax_total),
        grand_total=float(invoice.grand_total),
        paid_amount=float(invoice.paid_amount or 0),
        balance_due=float(invoice.balance_due or 0),
        payment_mode=invoice.payment_mode,
        payment_reference=invoice.payment_reference,
        source_quotation_no=invoice.source_quotation_no,
        customer_id=invoice.customer_id,
        supplier_id=invoice.supplier_id,
        company=company,
        customer=customer,
        supplier=supplier,
        cgst_amount=float(invoice.cgst_amount) if invoice.cgst_amount is not None else None,
        sgst_amount=float(invoice.sgst_amount) if invoice.sgst_amount is not None else None,
        igst_amount=float(invoice.igst_amount) if invoice.igst_amount is not None else None,
        lines=[_line_out(line) for line in lines],
        total_items=len(lines),
        total_quantity=total_quantity,
        amount_in_words=_amount_in_words(float(invoice.grand_total)),
        tax_amount_in_words=_amount_in_words(float(invoice.tax_total or 0)),
        tax_summary=_tax_summary(lines, interstate),
        invoice_meta=invoice_meta,
        is_interstate=interstate,
        place_of_supply=_place_of_supply(invoice, party, company),
    )


def _build_company_snapshot(company: Company, profile: CompanyProfile | None) -> dict:
    extra = dict(profile.extra_json or {}) if profile else {}
    if company.gstin and not extra.get("state_code") and str(company.gstin)[:2].isdigit():
        extra["state_code"] = str(company.gstin)[:2]
    return {
        "name": company.name,
        "business_name": profile.business_name if profile and profile.business_name else company.name,
        "gstin": company.gstin or (profile.gst_number if profile else None),
        "phone": company.phone or (profile.phone if profile else None),
        "address": company.address or (profile.address if profile else None),
        "city": company.city,
        "state": company.state or (profile.state if profile else None),
        "state_code": extra.get("state_code"),
        "pincode": company.pincode,
        "extra_data": extra,
    }


def _build_customer_snapshot(customer: Customer) -> dict:
    extra = dict(customer.extra_json or {})
    state_code = extra.get("state_code")
    if customer.gstin and not state_code and str(customer.gstin)[:2].isdigit():
        state_code = str(customer.gstin)[:2]
        extra["state_code"] = state_code
    return {
        "name": customer.name,
        "phone": customer.phone,
        "gstin": customer.gstin,
        "address": customer.address,
        "email": extra.get("email"),
        "business_name": extra.get("business_name"),
        "pan": extra.get("pan"),
        "state": extra.get("state"),
        "state_code": state_code,
        "pincode": extra.get("pincode"),
        "extra_data": extra,
    }


def _build_supplier_snapshot(supplier: Supplier) -> dict:
    extra = dict(supplier.extra_json or {})
    if supplier.business_name:
        extra.setdefault("business_name", supplier.business_name)
    state_code = extra.get("state_code")
    if supplier.gstin and not state_code and str(supplier.gstin)[:2].isdigit():
        state_code = str(supplier.gstin)[:2]
        extra["state_code"] = state_code
    return {
        "name": supplier.name,
        "phone": supplier.phone,
        "gstin": supplier.gstin,
        "address": supplier.address or supplier.address_line1,
        "email": supplier.email,
        "business_name": supplier.business_name,
        "pan": extra.get("pan"),
        "state": supplier.state,
        "state_code": state_code,
        "pincode": supplier.pincode,
        "extra_data": extra,
    }


def _build_invoice_pdf(invoice: Invoice, company: Company | None, party: PartyOut | None, lines: list[InvoiceLine]) -> bytes:
    body_lines = [
        "TAX INVOICE",
        "==========================================================================",
        f"Seller: {(company.name if company else 'Company')}",
        f"GSTIN/UIN: {company.gstin if company and company.gstin else '-'}",
        f"Phone: {company.phone if company and company.phone else '-'}",
        f"Address: {', '.join([bit for bit in [company.address if company else None, company.city if company else None, company.state if company else None, company.pincode if company else None] if bit]) or '-'}",
        "--------------------------------------------------------------------------",
        f"Invoice No: {invoice.invoice_no}    Dated: {invoice.invoice_date.strftime('%d/%m/%Y')}",
        f"Buyer: {(party.name if party else '-')}",
        f"Buyer GSTIN: {party.gstin if party and party.gstin else '-'}",
        f"Buyer Address: {party.address if party and party.address else '-'}",
        "--------------------------------------------------------------------------",
        "Sl | Description of Goods                 | HSN/SAC |   Qty |  Rate | Amount",
        "--------------------------------------------------------------------------",
    ]
    for index, line in enumerate(lines, start=1):
        body_lines.append(
            f"{str(index).rjust(2)} | "
            f"{line.description[:34].ljust(34)} | "
            f"{(line.hsn or '-'):>7} | "
            f"{float(line.qty):>5.2f} | "
            f"{float(line.price):>5.2f} | "
            f"{float(line.line_total):>6.2f}"
        )
    body_lines.extend(
        [
            "--------------------------------------------------------------------------",
            f"Subtotal: {float(invoice.subtotal):.2f}",
            f"CGST: {float(invoice.cgst_amount or 0):.2f}  SGST: {float(invoice.sgst_amount or 0):.2f}  IGST: {float(invoice.igst_amount or 0):.2f}",
            f"Grand Total: {float(invoice.grand_total):.2f}",
            f"Amount in Words: {_amount_in_words(float(invoice.grand_total))}",
            "",
            "Declaration:",
            "We declare that this invoice shows the actual price of the goods described",
            "and that all particulars are true and correct.",
            "",
            "This is a Computer Generated Invoice",
        ]
    )
    return build_text_pdf(f"TAX INVOICE {invoice.invoice_no}", body_lines, font="Courier")


def _prepared_invoice_payload(db: Session, user: User, payload: InvoiceCreate) -> dict:
    if payload.customer_id and payload.supplier_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select only one party")

    customer = None
    supplier = None
    if payload.customer_id:
        customer = db.get(Customer, payload.customer_id)
        if not customer or customer.company_id != user.company_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    if payload.supplier_id:
        supplier = db.get(Supplier, payload.supplier_id)
        if not supplier or supplier.company_id != user.company_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")

    party_snapshot = payload.customer_snapshot_json or payload.supplier_snapshot_json or {}
    if customer:
        party_snapshot = _build_customer_snapshot(customer)
    elif supplier:
        party_snapshot = _build_supplier_snapshot(supplier)

    if payload.tax_mode == TaxMode.GST and not party_snapshot.get("gstin"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Party GSTIN required for GST invoices")

    company = db.get(Company, user.company_id)
    profile = db.query(CompanyProfile).filter(CompanyProfile.company_id == user.company_id).first()

    invoice_meta = dict(payload.invoice_meta or {})
    if not invoice_meta.get("place_of_supply"):
        invoice_meta["place_of_supply"] = (
            party_snapshot.get("state")
            or ((party_snapshot.get("extra_data") or {}).get("place_of_supply") if isinstance(party_snapshot.get("extra_data"), dict) else None)
            or ((profile.extra_json or {}).get("place_of_supply_default") if profile and profile.extra_json else None)
        )

    data = payload.model_dump()
    data["customer_snapshot_json"] = _build_customer_snapshot(customer) if customer else (payload.customer_snapshot_json if payload.customer_id or payload.customer_snapshot_json else None)
    data["supplier_snapshot_json"] = _build_supplier_snapshot(supplier) if supplier else (payload.supplier_snapshot_json if payload.supplier_id or payload.supplier_snapshot_json else None)
    data["company_snapshot_json"] = _build_company_snapshot(company, profile) if company else payload.company_snapshot_json
    data["is_interstate"] = resolve_is_interstate(data, require_complete_context=(payload.tax_mode == TaxMode.GST))
    invoice_meta["is_interstate"] = bool(data["is_interstate"])
    data["invoice_meta"] = invoice_meta
    return data


@router.post("/invoices", response_model=InvoiceOut)
def create_sales_invoice(
    payload: InvoiceCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_sales_access),
) -> InvoiceOut:
    if not is_company_super_admin(db, user):
        if payload.invoice_date.date() < datetime.utcnow().date():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Backdated invoices are restricted")
    data = _prepared_invoice_payload(db, user, payload)
    invoice = create_invoice(db, user, InvoiceType.SALES, data)
    db.commit()

    return InvoiceOut(
        id=invoice.id,
        invoice_no=invoice.invoice_no,
        invoice_date=invoice.invoice_date,
        tax_mode=invoice.tax_mode,
        status=invoice.status.value,
        subtotal=float(invoice.subtotal),
        tax_total=float(invoice.tax_total),
        grand_total=float(invoice.grand_total),
        paid_amount=float(invoice.paid_amount),
        balance_due=float(invoice.balance_due),
        payment_mode=invoice.payment_mode,
        payment_reference=invoice.payment_reference,
        source_quotation_no=invoice.source_quotation_no,
        customer_id=invoice.customer_id,
        supplier_id=invoice.supplier_id,
    )


@router.get("/invoices", response_model=list[InvoiceOut])
def list_sales_invoices(
    db: Session = Depends(get_db),
    user: User = Depends(require_sales_access),
) -> list[InvoiceOut]:
    invoices = (
        db.query(Invoice)
        .filter(Invoice.company_id == user.company_id, Invoice.invoice_type == InvoiceType.SALES)
        .order_by(Invoice.invoice_date.desc())
        .all()
    )

    return [
        InvoiceOut(
            id=i.id,
            invoice_no=i.invoice_no,
            invoice_date=i.invoice_date,
            tax_mode=i.tax_mode,
            status=i.status.value,
            subtotal=float(i.subtotal),
            tax_total=float(i.tax_total),
            grand_total=float(i.grand_total),
            paid_amount=float(i.paid_amount or 0),
            balance_due=float(i.balance_due or 0),
            payment_mode=i.payment_mode,
            payment_reference=i.payment_reference,
            source_quotation_no=i.source_quotation_no,
            customer_id=i.customer_id,
            supplier_id=i.supplier_id,
        )
        for i in invoices
    ]


@router.post("/invoices/{invoice_id}/cancel", response_model=InvoiceOut)
def cancel_sales_invoice(
    invoice_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_sales_access),
) -> InvoiceOut:
    invoice = _get_sales_invoice_or_404(db, user, invoice_id)

    cancel_invoice(db, user, invoice)
    db.commit()

    return InvoiceOut(
        id=invoice.id,
        invoice_no=invoice.invoice_no,
        invoice_date=invoice.invoice_date,
        tax_mode=invoice.tax_mode,
        status=invoice.status.value,
        subtotal=float(invoice.subtotal),
        tax_total=float(invoice.tax_total),
        grand_total=float(invoice.grand_total),
        paid_amount=float(invoice.paid_amount or 0),
        balance_due=float(invoice.balance_due or 0),
        payment_mode=invoice.payment_mode,
        payment_reference=invoice.payment_reference,
        source_quotation_no=invoice.source_quotation_no,
        customer_id=invoice.customer_id,
        supplier_id=invoice.supplier_id,
    )


@router.post("/invoices/{invoice_id}/return", response_model=InvoiceOut)
def return_sales_invoice(
    invoice_id: str,
    payload: InvoiceReturnIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_sales_access),
) -> InvoiceOut:
    invoice = _get_sales_invoice_or_404(db, user, invoice_id)

    return_sales_items(db, user, invoice, [line.model_dump() for line in payload.lines], payload.notes)
    db.commit()

    return InvoiceOut(
        id=invoice.id,
        invoice_no=invoice.invoice_no,
        invoice_date=invoice.invoice_date,
        tax_mode=invoice.tax_mode,
        status=invoice.status.value,
        subtotal=float(invoice.subtotal),
        tax_total=float(invoice.tax_total),
        grand_total=float(invoice.grand_total),
        paid_amount=float(invoice.paid_amount or 0),
        balance_due=float(invoice.balance_due or 0),
        payment_mode=invoice.payment_mode,
        payment_reference=invoice.payment_reference,
        source_quotation_no=invoice.source_quotation_no,
        customer_id=invoice.customer_id,
        supplier_id=invoice.supplier_id,
    )


@router.get("/invoices/next-no", response_model=NextInvoiceNoOut)
def next_sales_invoice_no(
    db: Session = Depends(get_db),
    user: User = Depends(require_sales_access),
) -> NextInvoiceNoOut:
    invoice_no = generate_next_invoice_no(db, user.company_id, InvoiceType.SALES)
    return NextInvoiceNoOut(invoice_no=invoice_no)


@router.get("/invoices/{invoice_id}", response_model=InvoiceDetailOut)
def get_sales_invoice_detail(
    invoice_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_sales_access),
) -> InvoiceDetailOut:
    invoice = _get_sales_invoice_or_404(db, user, invoice_id)
    return _build_invoice_detail(db, invoice)


@router.patch("/invoices/{invoice_id}", response_model=InvoiceOut)
def update_sales_invoice(
    invoice_id: str,
    payload: InvoiceCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_sales_access),
) -> InvoiceOut:
    invoice = _get_sales_invoice_or_404(db, user, invoice_id)
    data = _prepared_invoice_payload(db, user, payload)
    invoice = update_invoice(db, user, invoice, data)
    return InvoiceOut(
        id=invoice.id,
        invoice_no=invoice.invoice_no,
        invoice_date=invoice.invoice_date,
        tax_mode=invoice.tax_mode,
        status=invoice.status.value,
        subtotal=float(invoice.subtotal),
        tax_total=float(invoice.tax_total),
        grand_total=float(invoice.grand_total),
        paid_amount=float(invoice.paid_amount or 0),
        balance_due=float(invoice.balance_due or 0),
        payment_mode=invoice.payment_mode,
        payment_reference=invoice.payment_reference,
        source_quotation_no=invoice.source_quotation_no,
        customer_id=invoice.customer_id,
        supplier_id=invoice.supplier_id,
    )


@router.get("/invoices/{invoice_id}/pdf")
def get_sales_invoice_pdf(
    invoice_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_sales_access),
) -> Response:
    invoice = _build_invoice_detail(db, _get_sales_invoice_or_404(db, user, invoice_id))
    profile = db.query(CompanyProfile).filter(CompanyProfile.company_id == user.company_id).first()
    settings = get_receipt_settings(profile)
    if invoice.tax_mode == TaxMode.GST:
        pdf_bytes = build_tax_invoice_pdf(invoice, settings)
    else:
        pdf_bytes = build_simple_receipt_pdf(invoice, settings, profile)
    filename = f"sale-{invoice.invoice_no}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/invoices/{invoice_id}/html")
def get_sales_invoice_html(
    invoice_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_sales_access),
) -> Response:
    invoice = _build_invoice_detail(db, _get_sales_invoice_or_404(db, user, invoice_id))
    profile = db.query(CompanyProfile).filter(CompanyProfile.company_id == user.company_id).first()
    settings = get_receipt_settings(profile)
    html = render_tax_invoice_html(invoice, settings) if invoice.tax_mode == TaxMode.GST else render_simple_receipt_html(invoice, settings, profile)
    return Response(content=html, media_type="text/html; charset=utf-8")


@router.post("/invoices/{invoice_id}/payment", response_model=InvoiceOut)
def update_sales_payment(
    invoice_id: str,
    payload: InvoicePaymentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_sales_access),
) -> InvoiceOut:
    invoice = _get_sales_invoice_or_404(db, user, invoice_id)
    if invoice.status == InvoiceStatus.CANCELLED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cancelled invoice cannot be updated")

    invoice.payment_mode = payload.payment_mode
    invoice.payment_reference = payload.payment_reference
    if payload.payment_mode:
        invoice.paid_amount = invoice.grand_total
        invoice.balance_due = 0
    else:
        invoice.paid_amount = 0
        invoice.balance_due = invoice.grand_total

    db.commit()

    return InvoiceOut(
        id=invoice.id,
        invoice_no=invoice.invoice_no,
        invoice_date=invoice.invoice_date,
        tax_mode=invoice.tax_mode,
        status=invoice.status.value,
        subtotal=float(invoice.subtotal),
        tax_total=float(invoice.tax_total),
        grand_total=float(invoice.grand_total),
        paid_amount=float(invoice.paid_amount or 0),
        balance_due=float(invoice.balance_due or 0),
        payment_mode=invoice.payment_mode,
        payment_reference=invoice.payment_reference,
        source_quotation_no=invoice.source_quotation_no,
    )
