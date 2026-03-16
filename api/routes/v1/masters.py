from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_company_user
from app.db.models import Customer, Invoice, Payment, Quotation, Supplier, User

router = APIRouter(prefix="/v1/masters", tags=["masters"])


class CustomerIn(BaseModel):
    name: str
    phone: str | None = None
    gstin: str | None = None
    address: str | None = None
    customer_type: str | None = None
    extra_data: dict | None = None


class CustomerOut(CustomerIn):
    id: str
    status: str


class SupplierIn(BaseModel):
    name: str
    business_name: str | None = None
    phone: str | None = None
    email: str | None = None
    gstin: str | None = None
    gst_registration_type: str | None = None
    gst_state: str | None = None
    address: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    extra_data: dict | None = None


class CustomerUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    gstin: str | None = None
    address: str | None = None
    customer_type: str | None = None
    extra_data: dict | None = None


class SupplierUpdate(BaseModel):
    name: str | None = None
    business_name: str | None = None
    phone: str | None = None
    email: str | None = None
    gstin: str | None = None
    gst_registration_type: str | None = None
    gst_state: str | None = None
    address: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    extra_data: dict | None = None


class SupplierOut(SupplierIn):
    id: str
    status: str


class DeleteOut(BaseModel):
    deleted: bool
    message: str


def _customer_out(row: Customer) -> CustomerOut:
    return CustomerOut(
        id=row.id,
        name=row.name,
        phone=row.phone,
        gstin=row.gstin,
        address=row.address,
        customer_type=row.customer_type,
        extra_data=row.extra_json or {},
        status=row.status,
    )


def _supplier_out(row: Supplier) -> SupplierOut:
    return SupplierOut(
        id=row.id,
        name=row.name,
        business_name=row.business_name,
        phone=row.phone,
        email=row.email,
        gstin=row.gstin,
        gst_registration_type=row.gst_registration_type,
        gst_state=row.gst_state,
        address=row.address,
        address_line1=row.address_line1,
        address_line2=row.address_line2,
        city=row.city,
        state=row.state,
        pincode=row.pincode,
        extra_data=row.extra_json or {},
        status=row.status,
    )


@router.get("/customers", response_model=list[CustomerOut])
def list_customers(db: Session = Depends(get_db), user: User = Depends(require_company_user)) -> list[CustomerOut]:
    rows = db.query(Customer).filter(Customer.company_id == user.company_id).all()
    return [_customer_out(r) for r in rows]


@router.get("/customers/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: str, db: Session = Depends(get_db), user: User = Depends(require_company_user)) -> CustomerOut:
    row = db.get(Customer, customer_id)
    if not row or row.company_id != user.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return _customer_out(row)


@router.post("/customers", response_model=CustomerOut)
def create_customer(payload: CustomerIn, db: Session = Depends(get_db), user: User = Depends(require_company_user)) -> CustomerOut:
    data = payload.model_dump()
    extra = data.pop("extra_data", None)
    row = Customer(company_id=user.company_id, **data, extra_json=extra or {})
    db.add(row)
    db.commit()
    db.refresh(row)
    return _customer_out(row)


@router.patch("/customers/{customer_id}", response_model=CustomerOut)
def update_customer(
    customer_id: str,
    payload: CustomerUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_company_user),
) -> CustomerOut:
    row = db.get(Customer, customer_id)
    if not row or row.company_id != user.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "extra_data":
            row.extra_json = value or {}
        else:
            setattr(row, field, value)
    db.commit()
    db.refresh(row)

    return _customer_out(row)


@router.delete("/customers/{customer_id}", response_model=DeleteOut)
def delete_customer(
    customer_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_company_user),
) -> DeleteOut:
    row = db.get(Customer, customer_id)
    if not row or row.company_id != user.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    invoice_ref = db.query(Invoice.id).filter(Invoice.company_id == user.company_id, Invoice.customer_id == customer_id).first()
    quotation_ref = db.query(Quotation.id).filter(Quotation.company_id == user.company_id, Quotation.customer_id == customer_id).first()
    payment_ref = db.query(Payment.id).filter(Payment.company_id == user.company_id, Payment.counterparty_id == customer_id).first()
    if invoice_ref or quotation_ref or payment_ref:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Customer is used in transactions and cannot be deleted")
    db.delete(row)
    db.commit()
    return DeleteOut(deleted=True, message="Customer deleted")


@router.get("/suppliers", response_model=list[SupplierOut])
def list_suppliers(db: Session = Depends(get_db), user: User = Depends(require_company_user)) -> list[SupplierOut]:
    rows = db.query(Supplier).filter(Supplier.company_id == user.company_id).all()
    return [_supplier_out(r) for r in rows]


@router.get("/suppliers/{supplier_id}", response_model=SupplierOut)
def get_supplier(supplier_id: str, db: Session = Depends(get_db), user: User = Depends(require_company_user)) -> SupplierOut:
    row = db.get(Supplier, supplier_id)
    if not row or row.company_id != user.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    return _supplier_out(row)


@router.post("/suppliers", response_model=SupplierOut)
def create_supplier(payload: SupplierIn, db: Session = Depends(get_db), user: User = Depends(require_company_user)) -> SupplierOut:
    data = payload.model_dump()
    extra = data.pop("extra_data", None)
    if not data.get("address") and data.get("address_line1"):
        data["address"] = data.get("address_line1")
    row = Supplier(company_id=user.company_id, **data, extra_json=extra or {})
    db.add(row)
    db.commit()
    db.refresh(row)
    return _supplier_out(row)


@router.patch("/suppliers/{supplier_id}", response_model=SupplierOut)
def update_supplier(
    supplier_id: str,
    payload: SupplierUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_company_user),
) -> SupplierOut:
    row = db.get(Supplier, supplier_id)
    if not row or row.company_id != user.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "extra_data":
            row.extra_json = value or {}
        else:
            setattr(row, field, value)
    if row.address_line1 and not row.address:
        row.address = row.address_line1
    db.commit()
    db.refresh(row)

    return _supplier_out(row)


@router.delete("/suppliers/{supplier_id}", response_model=DeleteOut)
def delete_supplier(
    supplier_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_company_user),
) -> DeleteOut:
    row = db.get(Supplier, supplier_id)
    if not row or row.company_id != user.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    invoice_ref = db.query(Invoice.id).filter(Invoice.company_id == user.company_id, Invoice.supplier_id == supplier_id).first()
    quotation_ref = db.query(Quotation.id).filter(Quotation.company_id == user.company_id, Quotation.supplier_id == supplier_id).first()
    payment_ref = db.query(Payment.id).filter(Payment.company_id == user.company_id, Payment.counterparty_id == supplier_id).first()
    if invoice_ref or quotation_ref or payment_ref:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Supplier is used in transactions and cannot be deleted")
    db.delete(row)
    db.commit()
    return DeleteOut(deleted=True, message="Supplier deleted")
