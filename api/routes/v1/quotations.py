from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import (
    get_db,
    require_quotation_convert_access,
    require_quotation_create_access,
    require_quotation_delete_access,
    require_quotation_edit_access,
    require_quotation_view_access,
)
from app.db.models import (
    Customer,
    Supplier,
    Quotation,
    QuotationLine,
    QuotationLineType,
    QuotationPartyType,
    QuotationStatus,
    TaxMode,
    User,
)
from app.services.quotation_service import (
    convert_to_sale,
    create_quotation,
    delete_quotation,
    duplicate_quotation,
    generate_next_quotation_no,
    update_quotation,
)

router = APIRouter(prefix="/v1/quotations", tags=["quotations"])


class LineIn(BaseModel):
    line_type: QuotationLineType = QuotationLineType.PRODUCT
    product_id: str | None = None
    description: str
    qty: float | None = None
    unit: str | None = None
    price: float
    discount_percent: float | None = None


class QuotationCreate(BaseModel):
    quotation_no: str = Field(min_length=1)
    quotation_date: datetime
    valid_until: datetime | None = None
    status: QuotationStatus | None = None
    party_type: QuotationPartyType | None = None
    customer_id: str | None = None
    supplier_id: str | None = None
    customer_snapshot_json: dict | None = None
    supplier_snapshot_json: dict | None = None
    company_snapshot_json: dict | None = None
    salesperson: str | None = None
    notes: str | None = None
    terms: str | None = None
    lines: list[LineIn]


class QuotationUpdate(BaseModel):
    quotation_no: str | None = None
    quotation_date: datetime | None = None
    valid_until: datetime | None = None
    status: QuotationStatus | None = None
    party_type: QuotationPartyType | None = None
    customer_id: str | None = None
    supplier_id: str | None = None
    customer_snapshot_json: dict | None = None
    supplier_snapshot_json: dict | None = None
    company_snapshot_json: dict | None = None
    salesperson: str | None = None
    notes: str | None = None
    terms: str | None = None
    lines: list[LineIn] | None = None


class QuotationOut(BaseModel):
    id: str
    quotation_no: str
    quotation_date: datetime
    valid_until: datetime | None
    status: str
    party_type: str
    party_id: str | None = None
    party_name: str | None = None
    customer_id: str | None = None
    customer_name: str | None = None
    subtotal: float
    grand_total: float
    revision_no: int


class QuotationLineOut(BaseModel):
    id: str
    line_type: str
    product_id: str | None = None
    description: str
    qty: float
    unit: str | None = None
    price: float
    discount_percent: float
    line_total: float


class PartyOut(BaseModel):
    name: str
    phone: str | None = None
    gstin: str | None = None
    address: str | None = None


class QuotationDeleteOut(BaseModel):
    success: bool = True


class QuotationDetailOut(QuotationOut):
    party: PartyOut | None = None
    customer: PartyOut | None = None
    supplier: PartyOut | None = None
    company_snapshot_json: dict | None = None
    salesperson: str | None = None
    notes: str | None = None
    terms: str | None = None
    created_by: str | None = None
    lines: list[QuotationLineOut]
    converted_invoice_id: str | None = None


class NextQuotationNoOut(BaseModel):
    quotation_no: str


class ConvertQuotationIn(BaseModel):
    tax_mode: TaxMode
    is_interstate: bool = False
    invoice_date: datetime | None = None
    payment_mode: str | None = None
    payment_reference: str | None = None


class ConvertQuotationOut(BaseModel):
    invoice_id: str


@router.post("", response_model=QuotationOut)
def create_new_quotation(
    payload: QuotationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_quotation_create_access),
) -> QuotationOut:
    quotation = create_quotation(db, user, payload.model_dump())
    party_id = quotation.customer_id if quotation.party_type == QuotationPartyType.CUSTOMER else quotation.supplier_id
    party_name = None
    customer_name = None
    if quotation.party_type == QuotationPartyType.CUSTOMER and quotation.customer_id:
        c = db.get(Customer, quotation.customer_id)
        if c:
            party_name = c.name
            customer_name = c.name
    if quotation.party_type == QuotationPartyType.SUPPLIER and quotation.supplier_id:
        s = db.get(Supplier, quotation.supplier_id)
        if s:
            party_name = s.name
    return QuotationOut(
        id=quotation.id,
        quotation_no=quotation.quotation_no,
        quotation_date=quotation.quotation_date,
        valid_until=quotation.valid_until,
        status=quotation.status.value,
        party_type=quotation.party_type.value,
        party_id=party_id,
        party_name=party_name,
        customer_id=quotation.customer_id,
        customer_name=customer_name,
        subtotal=float(quotation.subtotal),
        grand_total=float(quotation.grand_total),
        revision_no=quotation.revision_no,
    )


@router.get("", response_model=list[QuotationOut])
def list_quotations(
    db: Session = Depends(get_db),
    user: User = Depends(require_quotation_view_access),
) -> list[QuotationOut]:
    rows = (
        db.query(Quotation)
        .filter(Quotation.company_id == user.company_id)
        .order_by(Quotation.quotation_date.desc())
        .all()
    )
    customer_map: dict[str, str] = {}
    supplier_map: dict[str, str] = {}
    customer_ids = [row.customer_id for row in rows if row.party_type == QuotationPartyType.CUSTOMER and row.customer_id]
    supplier_ids = [row.supplier_id for row in rows if row.party_type == QuotationPartyType.SUPPLIER and row.supplier_id]
    if customer_ids:
        customers = db.query(Customer).filter(Customer.id.in_(customer_ids)).all()
        customer_map = {c.id: c.name for c in customers}
    if supplier_ids:
        suppliers = db.query(Supplier).filter(Supplier.id.in_(supplier_ids)).all()
        supplier_map = {s.id: s.name for s in suppliers}

    return [
        QuotationOut(
            id=row.id,
            quotation_no=row.quotation_no,
            quotation_date=row.quotation_date,
            valid_until=row.valid_until,
            status=row.status.value,
            party_type=row.party_type.value,
            party_id=row.customer_id if row.party_type == QuotationPartyType.CUSTOMER else row.supplier_id,
            party_name=customer_map.get(row.customer_id) if row.party_type == QuotationPartyType.CUSTOMER else supplier_map.get(row.supplier_id),
            customer_id=row.customer_id,
            customer_name=customer_map.get(row.customer_id) if row.customer_id else None,
            subtotal=float(row.subtotal),
            grand_total=float(row.grand_total),
            revision_no=row.revision_no,
        )
        for row in rows
    ]


@router.get("/next-no", response_model=NextQuotationNoOut)
def next_quotation_no(
    db: Session = Depends(get_db),
    user: User = Depends(require_quotation_create_access),
) -> NextQuotationNoOut:
    quotation_no = generate_next_quotation_no(db, user.company_id)
    return NextQuotationNoOut(quotation_no=quotation_no)


@router.get("/{quotation_id}", response_model=QuotationDetailOut)
def get_quotation_detail(
    quotation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_quotation_view_access),
) -> QuotationDetailOut:
    quotation = db.get(Quotation, quotation_id)
    if not quotation or quotation.company_id != user.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quotation not found")

    customer = None
    supplier = None
    party = None
    if quotation.party_type == QuotationPartyType.CUSTOMER and quotation.customer_snapshot_json:
        customer = PartyOut(
            name=quotation.customer_snapshot_json.get("name") or "Customer",
            phone=quotation.customer_snapshot_json.get("phone"),
            gstin=quotation.customer_snapshot_json.get("gstin"),
            address=quotation.customer_snapshot_json.get("address"),
        )
        party = customer
    elif quotation.party_type == QuotationPartyType.CUSTOMER and quotation.customer_id:
        c = db.get(Customer, quotation.customer_id)
        if c:
            customer = PartyOut(name=c.name, phone=c.phone, gstin=c.gstin, address=c.address)
            party = customer
    if quotation.party_type == QuotationPartyType.SUPPLIER and quotation.supplier_snapshot_json:
        supplier = PartyOut(
            name=quotation.supplier_snapshot_json.get("name") or "Supplier",
            phone=quotation.supplier_snapshot_json.get("phone"),
            gstin=quotation.supplier_snapshot_json.get("gstin"),
            address=quotation.supplier_snapshot_json.get("address"),
        )
        party = supplier
    elif quotation.party_type == QuotationPartyType.SUPPLIER and quotation.supplier_id:
        s = db.get(Supplier, quotation.supplier_id)
        if s:
            supplier = PartyOut(name=s.name, phone=s.phone, gstin=s.gstin, address=s.address_line1 or s.address)
            party = supplier

    lines = (
        db.query(QuotationLine)
        .filter(QuotationLine.quotation_id == quotation.id)
        .order_by(QuotationLine.line_order.asc())
        .all()
    )

    return QuotationDetailOut(
        id=quotation.id,
        quotation_no=quotation.quotation_no,
        quotation_date=quotation.quotation_date,
        valid_until=quotation.valid_until,
        status=quotation.status.value,
        party_type=quotation.party_type.value,
        party_id=quotation.customer_id if quotation.party_type == QuotationPartyType.CUSTOMER else quotation.supplier_id,
        party_name=party.name if party else None,
        customer_id=quotation.customer_id,
        customer_name=customer.name if customer else None,
        subtotal=float(quotation.subtotal),
        grand_total=float(quotation.grand_total),
        revision_no=quotation.revision_no,
        party=party,
        customer=customer,
        supplier=supplier,
        company_snapshot_json=quotation.company_snapshot_json,
        salesperson=quotation.salesperson,
        notes=quotation.notes,
        terms=quotation.terms,
        created_by=quotation.created_by,
        converted_invoice_id=quotation.converted_invoice_id,
        lines=[
            QuotationLineOut(
                id=line.id,
                line_type=line.line_type.value,
                product_id=line.product_id,
                description=line.description,
                qty=float(line.qty),
                unit=line.unit,
                price=float(line.price),
                discount_percent=float(line.discount_percent or 0),
                line_total=float(line.line_total),
            )
            for line in lines
        ],
    )


@router.patch("/{quotation_id}", response_model=QuotationOut)
def edit_quotation(
    quotation_id: str,
    payload: QuotationUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_quotation_edit_access),
) -> QuotationOut:
    quotation = db.get(Quotation, quotation_id)
    if not quotation or quotation.company_id != user.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quotation not found")

    updated = update_quotation(db, user, quotation, payload.model_dump(exclude_unset=True))
    party_id = updated.customer_id if updated.party_type == QuotationPartyType.CUSTOMER else updated.supplier_id
    party_name = None
    customer_name = None
    if updated.party_type == QuotationPartyType.CUSTOMER and updated.customer_id:
        c = db.get(Customer, updated.customer_id)
        if c:
            party_name = c.name
            customer_name = c.name
    if updated.party_type == QuotationPartyType.SUPPLIER and updated.supplier_id:
        s = db.get(Supplier, updated.supplier_id)
        if s:
            party_name = s.name
    return QuotationOut(
        id=updated.id,
        quotation_no=updated.quotation_no,
        quotation_date=updated.quotation_date,
        valid_until=updated.valid_until,
        status=updated.status.value,
        party_type=updated.party_type.value,
        party_id=party_id,
        party_name=party_name,
        customer_id=updated.customer_id,
        customer_name=customer_name,
        subtotal=float(updated.subtotal),
        grand_total=float(updated.grand_total),
        revision_no=updated.revision_no,
    )


@router.delete("/{quotation_id}", response_model=QuotationDeleteOut)
def remove_quotation(
    quotation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_quotation_delete_access),
) -> QuotationDeleteOut:
    quotation = db.get(Quotation, quotation_id)
    if not quotation or quotation.company_id != user.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quotation not found")

    delete_quotation(db, quotation)
    return QuotationDeleteOut()


@router.post("/{quotation_id}/convert", response_model=ConvertQuotationOut)
def convert_quotation(
    quotation_id: str,
    payload: ConvertQuotationIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_quotation_convert_access),
) -> ConvertQuotationOut:
    quotation = db.get(Quotation, quotation_id)
    if not quotation or quotation.company_id != user.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quotation not found")

    invoice_id = convert_to_sale(
        db,
        user,
        quotation,
        payload.tax_mode,
        is_interstate=payload.is_interstate,
        invoice_date=payload.invoice_date,
        payment_mode=payload.payment_mode,
        payment_reference=payload.payment_reference,
    )
    return ConvertQuotationOut(invoice_id=invoice_id)


@router.post("/{quotation_id}/duplicate", response_model=QuotationOut)
def duplicate_as_revision(
    quotation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_quotation_create_access),
) -> QuotationOut:
    quotation = db.get(Quotation, quotation_id)
    if not quotation or quotation.company_id != user.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quotation not found")

    new_quote = duplicate_quotation(db, user, quotation)
    party_id = new_quote.customer_id if new_quote.party_type == QuotationPartyType.CUSTOMER else new_quote.supplier_id
    party_name = None
    customer_name = None
    if new_quote.party_type == QuotationPartyType.CUSTOMER and new_quote.customer_id:
        c = db.get(Customer, new_quote.customer_id)
        if c:
            party_name = c.name
            customer_name = c.name
    if new_quote.party_type == QuotationPartyType.SUPPLIER and new_quote.supplier_id:
        s = db.get(Supplier, new_quote.supplier_id)
        if s:
            party_name = s.name
    return QuotationOut(
        id=new_quote.id,
        quotation_no=new_quote.quotation_no,
        quotation_date=new_quote.quotation_date,
        valid_until=new_quote.valid_until,
        status=new_quote.status.value,
        party_type=new_quote.party_type.value,
        party_id=party_id,
        party_name=party_name,
        customer_id=new_quote.customer_id,
        customer_name=customer_name,
        subtotal=float(new_quote.subtotal),
        grand_total=float(new_quote.grand_total),
        revision_no=new_quote.revision_no,
    )
