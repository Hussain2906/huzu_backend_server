from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import random

from app.db.models import Company, User, UserStatus, Role, RoleScope, UserRole, ProductCategory, Product, Customer, Supplier
from app.services.party_service import link_customer_to_party, link_supplier_to_party
from app.security.passwords import hash_password


@dataclass
class Factory:
    rng: random.Random
    counter: int = 0

    def _next(self, prefix: str) -> str:
        self.counter += 1
        return f"{prefix}{self.counter:04d}"

    def username(self, prefix: str = "user") -> str:
        return self._next(prefix)

    def company_name(self) -> str:
        return f"{self._next('Company')} Pvt Ltd"

    def phone(self) -> str:
        # deterministic 10-digit
        return f"9{self.rng.randint(100000000, 999999999)}"

    def gstin(self) -> str:
        # Not validated in backend, but keep format-like
        state = self.rng.randint(10, 35)
        return f"{state:02d}ABCDE1234F1Z5"

    def company_payload(self, username: str = "owner", password: str = "Pass@1234") -> dict:
        return {
            "name": self.company_name(),
            "gstin": self.gstin(),
            "phone": self.phone(),
            "address": "Street 1",
            "city": "Pune",
            "state": "MH",
            "pincode": "411001",
            "seat_limit": 5,
            "plan_days": 30,
            "super_admin_username": username,
            "super_admin_email": f"{username}@example.com",
            "super_admin_password": password,
        }


def create_company(db, name: str = "Test Co", seat_limit: int = 5, plan_days: int = 30) -> Company:
    expiry = datetime.utcnow() + timedelta(days=plan_days)
    company = Company(name=name, seat_limit=seat_limit, plan_expiry_at=expiry)
    db.add(company)
    db.flush()
    return company


def create_user(
    db,
    username: str,
    password: str,
    company_id: str | None = None,
    role_code: str | None = None,
    allowed_modules: list[str] | None = None,
    is_platform_admin: bool = False,
    status: UserStatus = UserStatus.ACTIVE,
) -> User:
    user = User(
        company_id=company_id,
        username=username,
        email=None,
        password_hash=hash_password(password),
        is_platform_admin=is_platform_admin,
        status=status,
        allowed_modules=allowed_modules,
    )
    db.add(user)
    db.flush()
    if role_code:
        role = (
            db.query(Role)
            .filter(Role.scope == (RoleScope.PLATFORM if is_platform_admin else RoleScope.COMPANY), Role.code == role_code)
            .first()
        )
        if role:
            db.add(UserRole(user_id=user.id, role_id=role.id))
    db.commit()
    return user


def create_category(db, company_id: str, name: str = "General") -> ProductCategory:
    row = ProductCategory(company_id=company_id, name=name)
    db.add(row)
    db.commit()
    return row


def create_product(
    db,
    company_id: str,
    category_id: str | None,
    name: str = "Sample Product",
    product_code: str | None = None,
    selling_rate: float = 100,
    purchase_rate: float = 80,
    taxable: bool = True,
    tax_rate: float = 18,
    unit: str = "pcs",
    hsn: str | None = "1234",
) -> Product:
    row = Product(
        company_id=company_id,
        category_id=category_id,
        name=name,
        product_code=product_code,
        selling_rate=selling_rate,
        purchase_rate=purchase_rate,
        taxable=taxable,
        tax_rate=tax_rate,
        unit=unit,
        hsn=hsn,
    )
    db.add(row)
    db.commit()
    return row


def create_customer(db, company_id: str, name: str = "Customer") -> Customer:
    row = Customer(company_id=company_id, name=name, phone="9000000000")
    db.add(row)
    db.flush()
    link_customer_to_party(db, row)
    db.commit()
    return row


def create_supplier(db, company_id: str, name: str = "Supplier") -> Supplier:
    row = Supplier(company_id=company_id, name=name, phone="9111111111")
    db.add(row)
    db.flush()
    link_supplier_to_party(db, row)
    db.commit()
    return row
