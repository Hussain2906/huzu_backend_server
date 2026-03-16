from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_purchase_access
from app.db.models import Customer, Invoice, InvoiceLine, InvoiceStatus, InvoiceType, PaymentMode, Supplier, TaxMode, User
from app.services.invoice_service import cancel_invoice, create_invoice, generate_next_invoice_no

router = APIRouter(prefix="/v1/purchase", tags=["purchase"])


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
    supplier_id: str | None = None
    supplier_snapshot_json: dict | None = None
    customer_id: str | None = None
    customer_snapshot_json: dict | None = None
    company_snapshot_json: dict | None = None

    lines: list[LineIn]

    round_off: float | None = None
    payment_mode: PaymentMode | None = None
    payment_reference: str | None = None
    payment_status: str | None = None


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
    supplier_id: str | None = None
    customer_id: str | None = None


class InvoiceLineOut(BaseModel):
    id: str
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


class InvoiceDetailOut(InvoiceOut):
    supplier: PartyOut | None = None
    customer: PartyOut | None = None
    lines: list[InvoiceLineOut]
    cgst_amount: float | None = None
    sgst_amount: float | None = None
    igst_amount: float | None = None


class InvoicePaymentUpdate(BaseModel):
    payment_status: str | None = None
    payment_mode: PaymentMode | None = None
    payment_reference: str | None = None


class NextInvoiceNoOut(BaseModel):
    invoice_no: str


@router.post("/invoices", response_model=InvoiceOut)
def create_purchase_invoice(
    payload: InvoiceCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_purchase_access),
) -> InvoiceOut:
    if payload.supplier_id and payload.customer_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select only one party")
    if payload.tax_mode == TaxMode.GST:
        if payload.supplier_id:
            supplier = db.get(Supplier, payload.supplier_id)
            if not supplier or supplier.company_id != user.company_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
            if not supplier.gstin:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Supplier GSTIN required for GST bills"
                )
        elif payload.customer_id:
            customer = db.get(Customer, payload.customer_id)
            if not customer or customer.company_id != user.company_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
            if not customer.gstin:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Customer GSTIN required for GST bills"
                )
        else:
            snapshot = payload.supplier_snapshot_json or payload.customer_snapshot_json or {}
            if not snapshot.get("gstin"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Party GSTIN required for GST bills"
                )
    data = payload.model_dump()
    invoice = create_invoice(db, user, InvoiceType.PURCHASE, data)
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
        supplier_id=invoice.supplier_id,
        customer_id=invoice.customer_id,
    )


@router.get("/invoices", response_model=list[InvoiceOut])
def list_purchase_invoices(
    db: Session = Depends(get_db),
    user: User = Depends(require_purchase_access),
) -> list[InvoiceOut]:
    invoices = (
        db.query(Invoice)
        .filter(Invoice.company_id == user.company_id, Invoice.invoice_type == InvoiceType.PURCHASE)
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
            supplier_id=i.supplier_id,
            customer_id=i.customer_id,
        )
        for i in invoices
    ]


@router.post("/invoices/{invoice_id}/cancel", response_model=InvoiceOut)
def cancel_purchase_invoice(
    invoice_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_purchase_access),
) -> InvoiceOut:
    invoice = db.get(Invoice, invoice_id)
    if not invoice or invoice.company_id != user.company_id or invoice.invoice_type != InvoiceType.PURCHASE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

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
        supplier_id=invoice.supplier_id,
        customer_id=invoice.customer_id,
    )


@router.get("/invoices/next-no", response_model=NextInvoiceNoOut)
def next_purchase_invoice_no(
    db: Session = Depends(get_db),
    user: User = Depends(require_purchase_access),
) -> NextInvoiceNoOut:
    invoice_no = generate_next_invoice_no(db, user.company_id, InvoiceType.PURCHASE)
    return NextInvoiceNoOut(invoice_no=invoice_no)


@router.get("/invoices/{invoice_id}", response_model=InvoiceDetailOut)
def get_purchase_invoice_detail(
    invoice_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_purchase_access),
) -> InvoiceDetailOut:
    invoice = db.get(Invoice, invoice_id)
    if not invoice or invoice.company_id != user.company_id or invoice.invoice_type != InvoiceType.PURCHASE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    supplier = None
    if invoice.supplier_id:
        s = db.get(Supplier, invoice.supplier_id)
        if s:
            address_parts = [s.address_line1 or s.address, s.city, s.state, s.pincode]
            address = ", ".join([part for part in address_parts if part])
            supplier = PartyOut(name=s.name, phone=s.phone, gstin=s.gstin, address=address or None)
    elif invoice.supplier_snapshot_json:
        snapshot = invoice.supplier_snapshot_json
        supplier = PartyOut(
            name=snapshot.get("name", "Supplier"),
            phone=snapshot.get("phone"),
            gstin=snapshot.get("gstin"),
            address=snapshot.get("address"),
        )

    customer = None
    if invoice.customer_id:
        c = db.get(Customer, invoice.customer_id)
        if c:
            customer = PartyOut(name=c.name, phone=c.phone, gstin=c.gstin, address=c.address)
    elif invoice.customer_snapshot_json:
        snapshot = invoice.customer_snapshot_json
        customer = PartyOut(
            name=snapshot.get("name", "Customer"),
            phone=snapshot.get("phone"),
            gstin=snapshot.get("gstin"),
            address=snapshot.get("address"),
        )

    lines = (
        db.query(InvoiceLine)
        .filter(InvoiceLine.invoice_id == invoice.id)
        .order_by(InvoiceLine.id.asc())
        .all()
    )

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
        supplier_id=invoice.supplier_id,
        supplier=supplier,
        customer=customer,
        cgst_amount=float(invoice.cgst_amount) if invoice.cgst_amount is not None else None,
        sgst_amount=float(invoice.sgst_amount) if invoice.sgst_amount is not None else None,
        igst_amount=float(invoice.igst_amount) if invoice.igst_amount is not None else None,
        lines=[
            InvoiceLineOut(
                id=line.id,
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
            for line in lines
        ],
    )


@router.post("/invoices/{invoice_id}/payment", response_model=InvoiceOut)
def update_purchase_payment(
    invoice_id: str,
    payload: InvoicePaymentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_purchase_access),
) -> InvoiceOut:
    invoice = db.get(Invoice, invoice_id)
    if not invoice or invoice.company_id != user.company_id or invoice.invoice_type != InvoiceType.PURCHASE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    if invoice.status == InvoiceStatus.CANCELLED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cancelled invoice cannot be updated")

    status_raw = str(payload.payment_status or "").strip().upper()
    invoice.payment_mode = payload.payment_mode
    invoice.payment_reference = payload.payment_reference
    if status_raw in ("UNPAID", "CREDIT"):
        invoice.paid_amount = 0
        invoice.balance_due = invoice.grand_total
    elif status_raw == "PAID" or payload.payment_mode:
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
        supplier_id=invoice.supplier_id,
        customer_id=invoice.customer_id,
    )
