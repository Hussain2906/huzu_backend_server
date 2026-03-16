from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db import gst_models  # ensure GST tables are registered


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.utcnow()


class CompanyStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    INACTIVE = "INACTIVE"


class UserStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    LOCKED = "LOCKED"


class InvoiceType(str, enum.Enum):
    SALES = "SALES"
    PURCHASE = "PURCHASE"


class TaxMode(str, enum.Enum):
    GST = "GST"
    NON_GST = "NON_GST"


class InvoiceStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    POSTED = "POSTED"
    CANCELLED = "CANCELLED"


class StockReason(str, enum.Enum):
    SALE = "SALE"
    PURCHASE = "PURCHASE"
    ADJUSTMENT = "ADJUSTMENT"
    CANCEL = "CANCEL"
    RETURN = "RETURN"


class PaymentMode(str, enum.Enum):
    CASH = "CASH"
    CARD = "CARD"
    CHEQUE = "CHEQUE"
    BANK_TRANSFER = "BANK_TRANSFER"
    UPI = "UPI"
    OTHER = "OTHER"


class MoneyDirection(str, enum.Enum):
    IN = "IN"
    OUT = "OUT"


class QuotationStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SENT = "SENT"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    CONVERTED = "CONVERTED"


class QuotationLineType(str, enum.Enum):
    PRODUCT = "PRODUCT"
    DESCRIPTION = "DESCRIPTION"


class QuotationPartyType(str, enum.Enum):
    CUSTOMER = "CUSTOMER"
    SUPPLIER = "SUPPLIER"


class LedgerType(str, enum.Enum):
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"


class Ledger(Base):
    __tablename__ = "chart_of_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"))
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[LedgerType] = mapped_column(Enum(LedgerType))
    parent_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("chart_of_accounts.id"), nullable=True)
    is_bank: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")

    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_coa_code_company"),)


class JournalVoucher(Base):
    __tablename__ = "journal_vouchers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"))
    voucher_type: Mapped[str] = mapped_column(String(50))  # SALES, PURCHASE, RECEIPT, PAYMENT, CONTRA, JOURNAL
    number: Mapped[str] = mapped_column(String(60))
    date: Mapped[datetime] = mapped_column(DateTime, default=_now)
    ref_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ref_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    narration: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="POSTED")
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_voucher_number_company"),)

    lines: Mapped[list["JournalLine"]] = relationship("JournalLine", back_populates="voucher")


class JournalLine(Base):
    __tablename__ = "journal_lines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    voucher_id: Mapped[str] = mapped_column(String(36), ForeignKey("journal_vouchers.id"))
    ledger_id: Mapped[str] = mapped_column(String(36), ForeignKey("chart_of_accounts.id"))
    dr: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    cr: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    line_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)

    voucher: Mapped[JournalVoucher] = relationship("JournalVoucher", back_populates="lines")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"))
    counterparty_type: Mapped[str] = mapped_column(String(20))  # CUSTOMER/SUPPLIER/OTHER
    counterparty_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    mode: Mapped[PaymentMode] = mapped_column(Enum(PaymentMode))
    amount: Mapped[float] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    ref_no: Mapped[str | None] = mapped_column(String(60), nullable=True)
    ref_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="POSTED")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class PaymentAllocation(Base):
    __tablename__ = "payment_allocations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    payment_id: Mapped[str] = mapped_column(String(36), ForeignKey("payments.id"))
    invoice_id: Mapped[str] = mapped_column(String(36), ForeignKey("invoices.id"))
    amount_applied: Mapped[float] = mapped_column(Numeric(14, 2))


class MoneyEntry(Base):
    __tablename__ = "money_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"))
    direction: Mapped[MoneyDirection] = mapped_column(Enum(MoneyDirection))
    amount: Mapped[float] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    entry_date: Mapped[datetime] = mapped_column(DateTime, default=_now)
    mode: Mapped[PaymentMode] = mapped_column(Enum(PaymentMode))
    reference: Mapped[str | None] = mapped_column(String(60), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    voucher_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("journal_vouchers.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[CompanyStatus] = mapped_column(Enum(CompanyStatus), default=CompanyStatus.ACTIVE)
    gstin: Mapped[str | None] = mapped_column(String(20), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pincode: Mapped[str | None] = mapped_column(String(10), nullable=True)

    seat_limit: Mapped[int] = mapped_column(Integer, default=1)
    plan_expiry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    enforce_single_manager: Mapped[bool] = mapped_column(Boolean, default=False)
    enforce_single_cashier: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    users: Mapped[list[User]] = relationship("User", back_populates="company")


class CompanyProfile(Base):
    __tablename__ = "company_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"), unique=True)

    business_name: Mapped[str] = mapped_column(String(200))
    gst_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    extra_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class RoleScope(str, enum.Enum):
    PLATFORM = "PLATFORM"
    COMPANY = "COMPANY"


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    scope: Mapped[RoleScope] = mapped_column(Enum(RoleScope))
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(100))
    is_system: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (UniqueConstraint("scope", "code", name="uq_roles_scope_code"),)


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    scope: Mapped[RoleScope] = mapped_column(Enum(RoleScope))
    code: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (UniqueConstraint("scope", "code", name="uq_permissions_scope_code"),)


class RolePermission(Base):
    __tablename__ = "role_permissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    role_id: Mapped[str] = mapped_column(String(36), ForeignKey("roles.id"))
    permission_id: Mapped[str] = mapped_column(String(36), ForeignKey("permissions.id"))

    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permissions"),)


class CompanyPermissionOverride(Base):
    __tablename__ = "company_permission_overrides"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"))
    role_id: Mapped[str] = mapped_column(String(36), ForeignKey("roles.id"))
    permission_id: Mapped[str] = mapped_column(String(36), ForeignKey("permissions.id"))
    allowed: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint("company_id", "role_id", "permission_id", name="uq_company_permission_overrides"),
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("companies.id"), nullable=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    role_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    allowed_modules: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[UserStatus] = mapped_column(Enum(UserStatus), default=UserStatus.ACTIVE)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    company: Mapped[Company | None] = relationship("Company", back_populates="users")


class UserRole(Base):
    __tablename__ = "user_roles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    role_id: Mapped[str] = mapped_column(String(36), ForeignKey("roles.id"))

    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_roles"),)


class ProductCategory(Base):
    __tablename__ = "product_categories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"))
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    __table_args__ = (UniqueConstraint("company_id", "name", name="uq_category_company_name"),)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"))
    category_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("product_categories.id"), nullable=True)

    name: Mapped[str] = mapped_column(String(200))
    product_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    hsn: Mapped[str | None] = mapped_column(String(20), nullable=True)
    selling_rate: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    purchase_rate: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    taxable: Mapped[bool] = mapped_column(Boolean, default=True)
    tax_rate: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    reorder_level: Mapped[float | None] = mapped_column(Numeric(12, 3), nullable=True)
    extra_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    __table_args__ = (UniqueConstraint("company_id", "product_code", name="uq_products_company_code"),)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"))
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    gstin: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    extra_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"))
    name: Mapped[str] = mapped_column(String(200))
    business_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gstin: Mapped[str | None] = mapped_column(String(20), nullable=True)
    gst_registration_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    gst_state: Mapped[str | None] = mapped_column(String(80), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    state: Mapped[str | None] = mapped_column(String(80), nullable=True)
    pincode: Mapped[str | None] = mapped_column(String(12), nullable=True)
    extra_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"))
    invoice_type: Mapped[InvoiceType] = mapped_column(Enum(InvoiceType))
    tax_mode: Mapped[TaxMode] = mapped_column(Enum(TaxMode))
    status: Mapped[InvoiceStatus] = mapped_column(Enum(InvoiceStatus), default=InvoiceStatus.POSTED)

    invoice_no: Mapped[str] = mapped_column(String(60))
    invoice_date: Mapped[datetime] = mapped_column(DateTime)

    voucher_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("journal_vouchers.id"), nullable=True)
    paid_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    balance_due: Mapped[float] = mapped_column(Numeric(12, 2), default=0)

    customer_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("customers.id"), nullable=True)
    supplier_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("suppliers.id"), nullable=True)
    source_quotation_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("quotations.id"),
        nullable=True,
    )
    source_quotation_no: Mapped[str | None] = mapped_column(String(60), nullable=True)

    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    tax_total: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    round_off: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    grand_total: Mapped[float] = mapped_column(Numeric(12, 2), default=0)

    cgst_rate: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    sgst_rate: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    igst_rate: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    cgst_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    sgst_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    igst_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    payment_mode: Mapped[PaymentMode | None] = mapped_column(Enum(PaymentMode), nullable=True)
    payment_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)

    customer_snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    supplier_snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    company_snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    extra_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    cancelled_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    lines: Mapped[list[InvoiceLine]] = relationship("InvoiceLine", back_populates="invoice")

    __table_args__ = (
        UniqueConstraint("company_id", "invoice_type", "invoice_no", name="uq_company_invoice_no"),
    )


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    invoice_id: Mapped[str] = mapped_column(String(36), ForeignKey("invoices.id"))
    product_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("products.id"), nullable=True)

    description: Mapped[str] = mapped_column(String(255))
    hsn: Mapped[str | None] = mapped_column(String(20), nullable=True)
    qty: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    price: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    discount_percent: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    taxable: Mapped[bool] = mapped_column(Boolean, default=True)
    tax_rate: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    line_total: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    tax_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)

    invoice: Mapped[Invoice] = relationship("Invoice", back_populates="lines")


class Quotation(Base):
    __tablename__ = "quotations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"))
    quotation_no: Mapped[str] = mapped_column(String(60))
    quotation_date: Mapped[datetime] = mapped_column(DateTime, default=_now)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[QuotationStatus] = mapped_column(Enum(QuotationStatus), default=QuotationStatus.DRAFT)
    party_type: Mapped[QuotationPartyType] = mapped_column(Enum(QuotationPartyType), default=QuotationPartyType.CUSTOMER)

    customer_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("customers.id"), nullable=True)
    customer_snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    supplier_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("suppliers.id"), nullable=True)
    supplier_snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    company_snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    salesperson: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    terms: Mapped[str | None] = mapped_column(Text, nullable=True)

    revision_of_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("quotations.id"), nullable=True)
    revision_no: Mapped[int] = mapped_column(Integer, default=1)

    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    grand_total: Mapped[float] = mapped_column(Numeric(12, 2), default=0)

    converted_invoice_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("invoices.id"), nullable=True)
    converted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    lines: Mapped[list["QuotationLine"]] = relationship(
        "QuotationLine",
        back_populates="quotation",
        order_by="QuotationLine.line_order",
    )

    __table_args__ = (
        UniqueConstraint("company_id", "quotation_no", name="uq_company_quotation_no"),
    )


class QuotationLine(Base):
    __tablename__ = "quotation_lines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    quotation_id: Mapped[str] = mapped_column(String(36), ForeignKey("quotations.id"))
    line_type: Mapped[QuotationLineType] = mapped_column(Enum(QuotationLineType))
    line_order: Mapped[int] = mapped_column(Integer, default=0)
    product_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("products.id"), nullable=True)
    description: Mapped[str] = mapped_column(String(255))
    qty: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    price: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    discount_percent: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    line_total: Mapped[float] = mapped_column(Numeric(12, 2), default=0)

    quotation: Mapped[Quotation] = relationship("Quotation", back_populates="lines")


class StockItem(Base):
    __tablename__ = "stock_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"))
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"))
    qty_on_hand: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    __table_args__ = (UniqueConstraint("company_id", "product_id", name="uq_company_product_stock"),)


class InventoryLedger(Base):
    __tablename__ = "inventory_ledger"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"))
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"))
    qty_change: Mapped[float] = mapped_column(Numeric(12, 3))
    reason: Mapped[StockReason] = mapped_column(Enum(StockReason))
    ref_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ref_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("companies.id"), nullable=True)
    actor_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100))
    ref_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ref_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    details_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"))
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    refresh_token_hash: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class DownloadJob(Base):
    __tablename__ = "download_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"))
    job_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    filters_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"))
    job_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    source_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
