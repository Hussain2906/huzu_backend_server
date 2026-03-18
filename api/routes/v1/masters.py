from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_company_user
from app.db.models import Customer, Invoice, Party, PartyRole, PartyRoleType, Payment, Quotation, Supplier, User
from app.services.party_service import (
    apply_party_updates,
    ensure_party_role,
    generate_party_code,
    normalize_email,
    normalize_gstin,
    normalize_name,
    normalize_phone,
    upsert_customer_profile_from_party,
    upsert_supplier_profile_from_party,
)

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
    party_id: str | None = None
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
    party_id: str | None = None
    status: str


class DeleteOut(BaseModel):
    deleted: bool
    message: str


class PartyMasterOut(BaseModel):
    id: str
    code: str
    name: str
    display_name: str | None = None
    roles: list[str]
    customer_id: str | None = None
    supplier_id: str | None = None
    phone: str | None = None
    alternate_phone: str | None = None
    email: str | None = None
    gstin: str | None = None
    business_name: str | None = None
    dob: datetime | None = None
    billing_type: str | None = None
    payment_term: str | None = None
    send_alerts: bool
    favourite_party: bool
    opening_balance: float
    balance_nature: str | None = None
    category_name: str | None = None
    billing_address_line: str | None = None
    billing_state: str | None = None
    billing_postal_code: str | None = None
    delivery_address_line: str | None = None
    delivery_state: str | None = None
    delivery_postal_code: str | None = None
    source: str | None = None
    source_row_no: int | None = None
    status: str
    created_at: datetime
    updated_at: datetime



def _customer_out(row: Customer, party: Party | None) -> CustomerOut:
    extra_data = dict(row.extra_json or {})
    if party:
        if party.email:
            extra_data.setdefault("email", party.email)
        if party.business_name:
            extra_data.setdefault("business_name", party.business_name)
        if party.billing_state:
            extra_data.setdefault("state", party.billing_state)
        if party.billing_postal_code:
            extra_data.setdefault("pincode", party.billing_postal_code)

    return CustomerOut(
        id=row.id,
        party_id=row.party_id,
        name=(party.name if party and party.name else row.name),
        phone=(party.phone if party and party.phone else row.phone),
        gstin=(party.gstin if party and party.gstin else row.gstin),
        address=(party.billing_address_line if party and party.billing_address_line else row.address),
        customer_type=row.customer_type or (party.category_name if party else None),
        extra_data=extra_data,
        status=(party.status if party and party.status else row.status),
    )



def _supplier_out(row: Supplier, party: Party | None) -> SupplierOut:
    extra_data = dict(row.extra_json or {})
    return SupplierOut(
        id=row.id,
        party_id=row.party_id,
        name=(party.name if party and party.name else row.name),
        business_name=(party.business_name if party and party.business_name else row.business_name),
        phone=(party.phone if party and party.phone else row.phone),
        email=(party.email if party and party.email else row.email),
        gstin=(party.gstin if party and party.gstin else row.gstin),
        gst_registration_type=row.gst_registration_type,
        gst_state=(party.billing_state if party and party.billing_state else row.gst_state),
        address=(party.billing_address_line if party and party.billing_address_line else row.address),
        address_line1=(party.billing_address_line if party and party.billing_address_line else row.address_line1),
        address_line2=row.address_line2,
        city=row.city,
        state=(party.billing_state if party and party.billing_state else row.state),
        pincode=(party.billing_postal_code if party and party.billing_postal_code else row.pincode),
        extra_data=extra_data,
        status=(party.status if party and party.status else row.status),
    )



def _resolve_party(db: Session, party_id: str | None) -> Party | None:
    if not party_id:
        return None
    return db.get(Party, party_id)



def _build_party_out(party: Party, roles: list[PartyRole]) -> PartyMasterOut:
    role_names = [role.role.value if hasattr(role.role, "value") else str(role.role) for role in roles]
    customer_role = next((role for role in roles if role.role == PartyRoleType.CUSTOMER), None)
    supplier_role = next((role for role in roles if role.role == PartyRoleType.SUPPLIER), None)
    return PartyMasterOut(
        id=party.id,
        code=party.code,
        name=party.name,
        display_name=party.display_name,
        roles=role_names,
        customer_id=customer_role.customer_id if customer_role else None,
        supplier_id=supplier_role.supplier_id if supplier_role else None,
        phone=party.phone,
        alternate_phone=party.alternate_phone,
        email=party.email,
        gstin=party.gstin,
        business_name=party.business_name,
        dob=party.dob,
        billing_type=party.billing_type,
        payment_term=party.payment_term,
        send_alerts=bool(party.send_alerts),
        favourite_party=bool(party.favourite_party),
        opening_balance=float(party.opening_balance or 0),
        balance_nature=party.balance_nature,
        category_name=party.category_name,
        billing_address_line=party.billing_address_line,
        billing_state=party.billing_state,
        billing_postal_code=party.billing_postal_code,
        delivery_address_line=party.delivery_address_line,
        delivery_state=party.delivery_state,
        delivery_postal_code=party.delivery_postal_code,
        source=party.source,
        source_row_no=party.source_row_no,
        status=party.status,
        created_at=party.created_at,
        updated_at=party.updated_at,
    )



def _cleanup_orphan_party(db: Session, party_id: str | None, company_id: str) -> None:
    if not party_id:
        return
    remaining_customer = (
        db.query(Customer.id)
        .filter(Customer.company_id == company_id, Customer.party_id == party_id)
        .first()
    )
    remaining_supplier = (
        db.query(Supplier.id)
        .filter(Supplier.company_id == company_id, Supplier.party_id == party_id)
        .first()
    )
    if remaining_customer or remaining_supplier:
        return

    db.query(PartyRole).filter(PartyRole.company_id == company_id, PartyRole.party_id == party_id).delete()
    party = db.get(Party, party_id)
    if party and party.company_id == company_id:
        db.delete(party)


@router.get("/customers", response_model=list[CustomerOut])
def list_customers(db: Session = Depends(get_db), user: User = Depends(require_company_user)) -> list[CustomerOut]:
    rows = db.query(Customer).filter(Customer.company_id == user.company_id).all()
    return [_customer_out(r, _resolve_party(db, r.party_id)) for r in rows]


@router.get("/customers/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: str, db: Session = Depends(get_db), user: User = Depends(require_company_user)) -> CustomerOut:
    row = db.get(Customer, customer_id)
    if not row or row.company_id != user.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return _customer_out(row, _resolve_party(db, row.party_id))


@router.post("/customers", response_model=CustomerOut)
def create_customer(payload: CustomerIn, db: Session = Depends(get_db), user: User = Depends(require_company_user)) -> CustomerOut:
    data = payload.model_dump()
    extra = dict(data.pop("extra_data", None) or {})

    party = Party(
        company_id=user.company_id,
        code=generate_party_code(db, user.company_id),
        name=normalize_name(data.get("name")) or data.get("name") or "Customer",
    )
    apply_party_updates(
        party,
        {
            "display_name": normalize_name(data.get("name")),
            "phone": normalize_phone(data.get("phone")),
            "gstin": normalize_gstin(data.get("gstin")),
            "billing_address_line": data.get("address"),
            "billing_state": extra.get("state"),
            "billing_postal_code": extra.get("pincode"),
            "email": normalize_email(extra.get("email")),
            "business_name": normalize_name(extra.get("business_name")),
            "category_name": data.get("customer_type"),
            "source": "masters_customer_api",
        },
        overwrite=True,
    )
    db.add(party)
    db.flush()

    row = upsert_customer_profile_from_party(db, party)
    row.customer_type = data.get("customer_type")
    existing_extra = dict(row.extra_json or {})
    existing_extra.update(extra)
    row.extra_json = existing_extra
    row.status = "ACTIVE"

    ensure_party_role(
        db,
        company_id=user.company_id,
        party_id=party.id,
        role=PartyRoleType.CUSTOMER,
        customer_id=row.id,
    )

    db.commit()
    db.refresh(row)
    return _customer_out(row, party)


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

    updates = payload.model_dump(exclude_unset=True)
    extra_updates = updates.pop("extra_data", None)

    party = _resolve_party(db, row.party_id)
    if not party:
        party = Party(company_id=user.company_id, code=generate_party_code(db, user.company_id), name=row.name)
        db.add(party)
        db.flush()
        row.party_id = party.id

    if extra_updates is not None:
        merged_extra = dict(row.extra_json or {})
        merged_extra.update(extra_updates or {})
        row.extra_json = merged_extra

    for field, value in updates.items():
        setattr(row, field, value)

    party_updates = {
        "name": normalize_name(updates.get("name")) if "name" in updates else None,
        "display_name": normalize_name(updates.get("name")) if "name" in updates else None,
        "phone": normalize_phone(updates.get("phone")) if "phone" in updates else None,
        "gstin": normalize_gstin(updates.get("gstin")) if "gstin" in updates else None,
        "billing_address_line": updates.get("address") if "address" in updates else None,
        "category_name": updates.get("customer_type") if "customer_type" in updates else None,
    }
    if extra_updates:
        if "email" in extra_updates:
            party_updates["email"] = normalize_email(extra_updates.get("email"))
        if "business_name" in extra_updates:
            party_updates["business_name"] = normalize_name(extra_updates.get("business_name"))
        if "state" in extra_updates:
            party_updates["billing_state"] = extra_updates.get("state")
        if "pincode" in extra_updates:
            party_updates["billing_postal_code"] = extra_updates.get("pincode")

    apply_party_updates(party, party_updates, overwrite=True)
    upsert_customer_profile_from_party(db, party, customer=row)

    db.commit()
    db.refresh(row)

    return _customer_out(row, party)


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

    party_id = row.party_id
    db.query(PartyRole).filter(
        PartyRole.company_id == user.company_id,
        PartyRole.customer_id == row.id,
        PartyRole.role == PartyRoleType.CUSTOMER,
    ).delete()
    db.delete(row)
    _cleanup_orphan_party(db, party_id, user.company_id)
    db.commit()
    return DeleteOut(deleted=True, message="Customer deleted")


@router.get("/suppliers", response_model=list[SupplierOut])
def list_suppliers(db: Session = Depends(get_db), user: User = Depends(require_company_user)) -> list[SupplierOut]:
    rows = db.query(Supplier).filter(Supplier.company_id == user.company_id).all()
    return [_supplier_out(r, _resolve_party(db, r.party_id)) for r in rows]


@router.get("/suppliers/{supplier_id}", response_model=SupplierOut)
def get_supplier(supplier_id: str, db: Session = Depends(get_db), user: User = Depends(require_company_user)) -> SupplierOut:
    row = db.get(Supplier, supplier_id)
    if not row or row.company_id != user.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    return _supplier_out(row, _resolve_party(db, row.party_id))


@router.post("/suppliers", response_model=SupplierOut)
def create_supplier(payload: SupplierIn, db: Session = Depends(get_db), user: User = Depends(require_company_user)) -> SupplierOut:
    data = payload.model_dump()
    extra = dict(data.pop("extra_data", None) or {})
    if not data.get("address") and data.get("address_line1"):
        data["address"] = data.get("address_line1")

    party = Party(
        company_id=user.company_id,
        code=generate_party_code(db, user.company_id),
        name=normalize_name(data.get("name")) or data.get("name") or "Supplier",
    )
    apply_party_updates(
        party,
        {
            "display_name": normalize_name(data.get("name")),
            "phone": normalize_phone(data.get("phone")),
            "email": normalize_email(data.get("email")),
            "gstin": normalize_gstin(data.get("gstin")),
            "business_name": normalize_name(data.get("business_name")),
            "billing_address_line": data.get("address") or data.get("address_line1"),
            "billing_state": data.get("state") or data.get("gst_state"),
            "billing_postal_code": data.get("pincode"),
            "source": "masters_supplier_api",
        },
        overwrite=True,
    )
    db.add(party)
    db.flush()

    row = upsert_supplier_profile_from_party(db, party)
    row.gst_registration_type = data.get("gst_registration_type")
    row.address_line2 = data.get("address_line2")
    row.city = data.get("city")
    row.extra_json = {**dict(row.extra_json or {}), **extra}

    ensure_party_role(
        db,
        company_id=user.company_id,
        party_id=party.id,
        role=PartyRoleType.SUPPLIER,
        supplier_id=row.id,
    )

    db.commit()
    db.refresh(row)
    return _supplier_out(row, party)


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

    updates = payload.model_dump(exclude_unset=True)
    extra_updates = updates.pop("extra_data", None)
    if "address" not in updates and updates.get("address_line1"):
        updates["address"] = updates.get("address_line1")

    party = _resolve_party(db, row.party_id)
    if not party:
        party = Party(company_id=user.company_id, code=generate_party_code(db, user.company_id), name=row.name)
        db.add(party)
        db.flush()
        row.party_id = party.id

    if extra_updates is not None:
        merged_extra = dict(row.extra_json or {})
        merged_extra.update(extra_updates or {})
        row.extra_json = merged_extra

    for field, value in updates.items():
        setattr(row, field, value)

    party_updates = {
        "name": normalize_name(updates.get("name")) if "name" in updates else None,
        "display_name": normalize_name(updates.get("name")) if "name" in updates else None,
        "phone": normalize_phone(updates.get("phone")) if "phone" in updates else None,
        "email": normalize_email(updates.get("email")) if "email" in updates else None,
        "gstin": normalize_gstin(updates.get("gstin")) if "gstin" in updates else None,
        "business_name": normalize_name(updates.get("business_name")) if "business_name" in updates else None,
        "billing_address_line": updates.get("address") if "address" in updates else updates.get("address_line1"),
        "billing_state": updates.get("state") if "state" in updates else updates.get("gst_state"),
        "billing_postal_code": updates.get("pincode") if "pincode" in updates else None,
    }
    apply_party_updates(party, party_updates, overwrite=True)

    upsert_supplier_profile_from_party(db, party, supplier=row)

    if row.address_line1 and not row.address:
        row.address = row.address_line1
    db.commit()
    db.refresh(row)

    return _supplier_out(row, party)


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

    party_id = row.party_id
    db.query(PartyRole).filter(
        PartyRole.company_id == user.company_id,
        PartyRole.supplier_id == row.id,
        PartyRole.role == PartyRoleType.SUPPLIER,
    ).delete()
    db.delete(row)
    _cleanup_orphan_party(db, party_id, user.company_id)
    db.commit()
    return DeleteOut(deleted=True, message="Supplier deleted")


@router.get("/parties", response_model=list[PartyMasterOut])
def list_parties(
    role: str | None = Query(default=None, description="CUSTOMER or SUPPLIER"),
    q: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_company_user),
) -> list[PartyMasterOut]:
    query = db.query(Party).filter(Party.company_id == user.company_id, Party.deleted_at.is_(None))

    if q:
        token = f"%{q.strip().lower()}%"
        query = query.filter(
            func.lower(Party.name).like(token)
            | func.lower(func.coalesce(Party.phone, "")).like(token)
            | func.lower(func.coalesce(Party.gstin, "")).like(token)
            | func.lower(func.coalesce(Party.code, "")).like(token)
        )

    role_filter = None
    if role:
        normalized = role.strip().upper()
        if normalized not in {PartyRoleType.CUSTOMER.value, PartyRoleType.SUPPLIER.value}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role filter")
        role_filter = PartyRoleType(normalized)
        query = query.join(PartyRole, PartyRole.party_id == Party.id).filter(
            PartyRole.company_id == user.company_id,
            PartyRole.role == role_filter,
        )

    parties = query.order_by(Party.name.asc()).all()
    if not parties:
        return []

    party_ids = [party.id for party in parties]
    role_rows = (
        db.query(PartyRole)
        .filter(PartyRole.company_id == user.company_id, PartyRole.party_id.in_(party_ids))
        .all()
    )
    role_map: dict[str, list[PartyRole]] = {}
    for row in role_rows:
        role_map.setdefault(row.party_id, []).append(row)

    if role_filter:
        return [_build_party_out(party, [r for r in role_map.get(party.id, []) if r.role == role_filter]) for party in parties]
    return [_build_party_out(party, role_map.get(party.id, [])) for party in parties]


@router.get("/parties/{party_id}", response_model=PartyMasterOut)
def get_party(
    party_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_company_user),
) -> PartyMasterOut:
    party = db.get(Party, party_id)
    if not party or party.company_id != user.company_id or party.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Party not found")

    roles = (
        db.query(PartyRole)
        .filter(PartyRole.company_id == user.company_id, PartyRole.party_id == party_id)
        .all()
    )
    return _build_party_out(party, roles)
