from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import re
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import Customer, Party, PartyRole, PartyRoleType, Supplier

INVALID_PHONE_TOKENS = {"", "-", "$PHONE", "NA", "N/A", "NULL", "NONE"}
GSTIN_REGEX = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][A-Z0-9]Z[A-Z0-9]$")
EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")



def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()



def null_if_blank(value: Any) -> str | None:
    cleaned = clean_text(value)
    return cleaned or None



def normalize_name(value: Any) -> str | None:
    cleaned = " ".join(clean_text(value).split())
    return cleaned or None



def normalize_phone(value: Any) -> str | None:
    raw = clean_text(value)
    if not raw:
        return None
    if raw.strip().upper() in INVALID_PHONE_TOKENS:
        return None

    has_plus = raw.strip().startswith("+")
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) < 7:
        return None
    return f"+{digits}" if has_plus else digits



def normalize_email(value: Any) -> str | None:
    cleaned = clean_text(value).lower()
    return cleaned or None



def is_valid_email(value: str | None) -> bool:
    if not value:
        return False
    return bool(EMAIL_REGEX.match(value))



def normalize_gstin(value: Any) -> str | None:
    cleaned = clean_text(value).replace(" ", "").upper()
    return cleaned or None



def is_valid_gstin(value: str | None) -> bool:
    if not value:
        return False
    return bool(GSTIN_REGEX.match(value))



def derive_balance_nature(amount: Decimal | float | int | None) -> str | None:
    value = Decimal(str(amount or 0))
    if value > 0:
        return "DEBIT"
    if value < 0:
        return "CREDIT"
    return None



def generate_party_code(db: Session, company_id: str) -> str:
    rows = db.query(Party.code).filter(Party.company_id == company_id, Party.code.like("PTY-%")).all()
    max_no = 0
    for (code,) in rows:
        text = clean_text(code)
        if not text.startswith("PTY-"):
            continue
        suffix = text[4:]
        if suffix.isdigit():
            max_no = max(max_no, int(suffix))
    return f"PTY-{max_no + 1:06d}"



def _party_defaults_from_customer(customer: Customer) -> dict[str, Any]:
    extra = dict(customer.extra_json or {})
    return {
        "name": normalize_name(customer.name) or "Unknown Party",
        "display_name": normalize_name(customer.name),
        "phone": normalize_phone(customer.phone),
        "email": normalize_email(extra.get("email")),
        "gstin": normalize_gstin(customer.gstin),
        "business_name": normalize_name(extra.get("business_name")),
        "billing_address_line": null_if_blank(customer.address),
        "billing_state": null_if_blank(extra.get("state")),
        "billing_postal_code": null_if_blank(extra.get("pincode")),
        "source": "legacy_customer",
        "status": customer.status or "ACTIVE",
    }



def _party_defaults_from_supplier(supplier: Supplier) -> dict[str, Any]:
    extra = dict(supplier.extra_json or {})
    billing_address = supplier.address or supplier.address_line1
    return {
        "name": normalize_name(supplier.name) or "Unknown Party",
        "display_name": normalize_name(supplier.name),
        "phone": normalize_phone(supplier.phone),
        "email": normalize_email(supplier.email),
        "gstin": normalize_gstin(supplier.gstin),
        "business_name": normalize_name(supplier.business_name),
        "billing_address_line": null_if_blank(billing_address),
        "billing_state": null_if_blank(supplier.state or supplier.gst_state or extra.get("state")),
        "billing_postal_code": null_if_blank(supplier.pincode or extra.get("pincode")),
        "source": "legacy_supplier",
        "status": supplier.status or "ACTIVE",
    }



def apply_party_updates(party: Party, updates: dict[str, Any], *, overwrite: bool = True) -> None:
    for field, value in updates.items():
        if value is None:
            continue
        current = getattr(party, field, None)
        if overwrite or current in (None, ""):
            setattr(party, field, value)
    party.updated_at = datetime.utcnow()



def ensure_party_role(
    db: Session,
    *,
    company_id: str,
    party_id: str,
    role: PartyRoleType,
    customer_id: str | None = None,
    supplier_id: str | None = None,
) -> PartyRole:
    row = (
        db.query(PartyRole)
        .filter(
            PartyRole.company_id == company_id,
            PartyRole.party_id == party_id,
            PartyRole.role == role,
        )
        .first()
    )
    if not row:
        row = PartyRole(company_id=company_id, party_id=party_id, role=role)
        db.add(row)
        db.flush()

    if customer_id:
        row.customer_id = customer_id
    if supplier_id:
        row.supplier_id = supplier_id
    return row



def _find_party_match_for_customer(db: Session, company_id: str, customer: Customer) -> Party | None:
    gstin = normalize_gstin(customer.gstin)
    if gstin:
        row = db.query(Party).filter(Party.company_id == company_id, Party.gstin == gstin).first()
        if row:
            return row

    phone = normalize_phone(customer.phone)
    name = normalize_name(customer.name)
    if phone and name:
        row = (
            db.query(Party)
            .filter(
                Party.company_id == company_id,
                Party.phone == phone,
                func.lower(Party.name) == name.lower(),
            )
            .first()
        )
        if row:
            return row

    if name and customer.address:
        row = (
            db.query(Party)
            .join(PartyRole, PartyRole.party_id == Party.id)
            .filter(
                Party.company_id == company_id,
                PartyRole.role == PartyRoleType.CUSTOMER,
                func.lower(Party.name) == name.lower(),
                func.lower(func.coalesce(Party.billing_address_line, "")) == customer.address.strip().lower(),
            )
            .first()
        )
        if row:
            return row
    return None



def _find_party_match_for_supplier(db: Session, company_id: str, supplier: Supplier) -> Party | None:
    gstin = normalize_gstin(supplier.gstin)
    if gstin:
        row = db.query(Party).filter(Party.company_id == company_id, Party.gstin == gstin).first()
        if row:
            return row

    phone = normalize_phone(supplier.phone)
    name = normalize_name(supplier.name)
    if phone and name:
        row = (
            db.query(Party)
            .filter(
                Party.company_id == company_id,
                Party.phone == phone,
                func.lower(Party.name) == name.lower(),
            )
            .first()
        )
        if row:
            return row

    addr = supplier.address or supplier.address_line1
    if name and addr:
        row = (
            db.query(Party)
            .join(PartyRole, PartyRole.party_id == Party.id)
            .filter(
                Party.company_id == company_id,
                PartyRole.role == PartyRoleType.SUPPLIER,
                func.lower(Party.name) == name.lower(),
                func.lower(func.coalesce(Party.billing_address_line, "")) == addr.strip().lower(),
            )
            .first()
        )
        if row:
            return row
    return None



def link_customer_to_party(db: Session, customer: Customer) -> Party:
    party = db.get(Party, customer.party_id) if customer.party_id else None
    if not party:
        party = _find_party_match_for_customer(db, customer.company_id, customer)
    if not party:
        party = Party(company_id=customer.company_id, code=generate_party_code(db, customer.company_id), name=customer.name)
        db.add(party)
        db.flush()

    apply_party_updates(party, _party_defaults_from_customer(customer), overwrite=False)
    customer.party_id = party.id
    ensure_party_role(
        db,
        company_id=customer.company_id,
        party_id=party.id,
        role=PartyRoleType.CUSTOMER,
        customer_id=customer.id,
    )
    return party



def link_supplier_to_party(db: Session, supplier: Supplier) -> Party:
    party = db.get(Party, supplier.party_id) if supplier.party_id else None
    if not party:
        party = _find_party_match_for_supplier(db, supplier.company_id, supplier)
    if not party:
        party = Party(company_id=supplier.company_id, code=generate_party_code(db, supplier.company_id), name=supplier.name)
        db.add(party)
        db.flush()

    apply_party_updates(party, _party_defaults_from_supplier(supplier), overwrite=False)
    supplier.party_id = party.id
    ensure_party_role(
        db,
        company_id=supplier.company_id,
        party_id=party.id,
        role=PartyRoleType.SUPPLIER,
        supplier_id=supplier.id,
    )
    return party



def ensure_party_links_for_legacy_data(db: Session) -> None:
    customers = db.query(Customer).all()
    for customer in customers:
        link_customer_to_party(db, customer)

    suppliers = db.query(Supplier).all()
    for supplier in suppliers:
        link_supplier_to_party(db, supplier)

    db.flush()



def upsert_customer_profile_from_party(db: Session, party: Party, *, customer: Customer | None = None) -> Customer:
    role = (
        db.query(PartyRole)
        .filter(
            PartyRole.company_id == party.company_id,
            PartyRole.party_id == party.id,
            PartyRole.role == PartyRoleType.CUSTOMER,
        )
        .first()
    )
    if not customer and role and role.customer_id:
        customer = db.get(Customer, role.customer_id)
    if not customer:
        customer = (
            db.query(Customer)
            .filter(Customer.company_id == party.company_id, Customer.party_id == party.id)
            .first()
        )

    extra = {
        "email": party.email,
        "business_name": party.business_name,
        "state": party.billing_state,
        "pincode": party.billing_postal_code,
    }
    if not customer:
        customer = Customer(
            company_id=party.company_id,
            party_id=party.id,
            name=party.name,
            phone=party.phone,
            gstin=party.gstin,
            address=party.billing_address_line,
            customer_type=party.category_name,
            extra_json={k: v for k, v in extra.items() if v},
            status=party.status,
        )
        db.add(customer)
        db.flush()
    else:
        customer.party_id = party.id
        customer.name = party.name
        customer.phone = party.phone
        customer.gstin = party.gstin
        customer.address = party.billing_address_line
        customer.customer_type = party.category_name
        customer.status = party.status
        existing_extra = dict(customer.extra_json or {})
        for key, value in extra.items():
            if value is not None:
                existing_extra[key] = value
        customer.extra_json = existing_extra

    ensure_party_role(
        db,
        company_id=party.company_id,
        party_id=party.id,
        role=PartyRoleType.CUSTOMER,
        customer_id=customer.id,
    )
    return customer



def upsert_supplier_profile_from_party(db: Session, party: Party, *, supplier: Supplier | None = None) -> Supplier:
    role = (
        db.query(PartyRole)
        .filter(
            PartyRole.company_id == party.company_id,
            PartyRole.party_id == party.id,
            PartyRole.role == PartyRoleType.SUPPLIER,
        )
        .first()
    )
    if not supplier and role and role.supplier_id:
        supplier = db.get(Supplier, role.supplier_id)
    if not supplier:
        supplier = (
            db.query(Supplier)
            .filter(Supplier.company_id == party.company_id, Supplier.party_id == party.id)
            .first()
        )

    if not supplier:
        supplier = Supplier(
            company_id=party.company_id,
            party_id=party.id,
            name=party.name,
            business_name=party.business_name,
            phone=party.phone,
            email=party.email,
            gstin=party.gstin,
            gst_state=party.billing_state,
            address=party.billing_address_line,
            address_line1=party.billing_address_line,
            state=party.billing_state,
            pincode=party.billing_postal_code,
            extra_json={},
            status=party.status,
        )
        db.add(supplier)
        db.flush()
    else:
        supplier.party_id = party.id
        supplier.name = party.name
        supplier.business_name = party.business_name
        supplier.phone = party.phone
        supplier.email = party.email
        supplier.gstin = party.gstin
        supplier.gst_state = party.billing_state
        supplier.address = party.billing_address_line
        supplier.address_line1 = party.billing_address_line
        supplier.state = party.billing_state
        supplier.pincode = party.billing_postal_code
        supplier.status = party.status

    ensure_party_role(
        db,
        company_id=party.company_id,
        party_id=party.id,
        role=PartyRoleType.SUPPLIER,
        supplier_id=supplier.id,
    )
    return supplier
