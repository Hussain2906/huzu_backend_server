from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.db.models import Company, ProductCategory, Product, Customer, Supplier, Role, RoleScope, User, UserRole
from app.security.passwords import hash_password
from scripts.seed_core import main as seed_core
from scripts.seed_platform_admin_db import main as seed_platform_admin


def _ensure_company(db) -> Company:
    company = db.query(Company).filter(Company.name == "Demo Traders").first()
    if company:
        return company
    company = Company(
        name="Demo Traders",
        seat_limit=5,
        plan_expiry_at=datetime.utcnow() + timedelta(days=30),
    )
    db.add(company)
    db.flush()
    return company


def _ensure_role(db, code: str) -> Role | None:
    return db.query(Role).filter(Role.scope == RoleScope.COMPANY, Role.code == code).first()


def _ensure_user(db, company: Company, username: str, password: str, role_code: str, allowed_modules: list[str] | None = None) -> User:
    user = db.query(User).filter(User.username == username).first()
    if user:
        return user
    user = User(
        company_id=company.id,
        username=username,
        email=None,
        password_hash=hash_password(password),
        is_platform_admin=False,
        allowed_modules=allowed_modules,
    )
    db.add(user)
    db.flush()
    role = _ensure_role(db, role_code)
    if role:
        db.add(UserRole(user_id=user.id, role_id=role.id))
    db.commit()
    return user


def main() -> None:
    Base.metadata.create_all(bind=engine)
    seed_core()
    seed_platform_admin()

    db = SessionLocal()
    try:
        company = _ensure_company(db)
        _ensure_user(db, company, "owner", "Pass@1234", "SUPER_ADMIN")
        _ensure_user(db, company, "limited", "Pass@1234", "EMPLOYEE", allowed_modules=["inventory"])

        # seed reference data
        category = db.query(ProductCategory).filter(ProductCategory.company_id == company.id, ProductCategory.name == "General").first()
        if not category:
            category = ProductCategory(company_id=company.id, name="General")
            db.add(category)
            db.flush()

        product = (
            db.query(Product)
            .filter(Product.company_id == company.id, Product.product_code == "PRD-001")
            .first()
        )
        if not product:
            product = Product(
                company_id=company.id,
                category_id=category.id,
                name="Sample Product",
                product_code="PRD-001",
                selling_rate=100,
                purchase_rate=80,
                unit="Nos",
                taxable=True,
                tax_rate=18,
                hsn="1234",
            )
            db.add(product)

        customer = db.query(Customer).filter(Customer.company_id == company.id, Customer.name == "Sample Customer").first()
        if not customer:
            customer = Customer(
                company_id=company.id,
                name="Sample Customer",
                phone="9000000000",
                gstin="22AAAAA0000A1Z5",
                address="Main Street",
            )
            db.add(customer)

        supplier = db.query(Supplier).filter(Supplier.company_id == company.id, Supplier.name == "Sample Supplier").first()
        if not supplier:
            supplier = Supplier(
                company_id=company.id,
                name="Sample Supplier",
                phone="9111111111",
                gstin="22AAAAA0000A1Z5",
                address="Market Road",
            )
            db.add(supplier)

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
