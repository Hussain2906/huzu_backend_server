from __future__ import annotations

from datetime import datetime
from sqlalchemy import String, DateTime, JSON, Numeric, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
import enum
import uuid


def _uuid() -> str:
    return str(uuid.uuid4())


class GstrPeriodStatus(str, enum.Enum):
    OPEN = "OPEN"
    LOCKED = "LOCKED"
    FILED = "FILED"


class GstPeriod(Base):
    __tablename__ = "gst_periods"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"))
    period: Mapped[str] = mapped_column(String(10))  # YYYY-MM
    status: Mapped[GstrPeriodStatus] = mapped_column(Enum(GstrPeriodStatus), default=GstrPeriodStatus.OPEN)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Gstr1Doc(Base):
    __tablename__ = "gstr1_docs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"))
    invoice_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("invoices.id"), nullable=True)
    section: Mapped[str] = mapped_column(String(20))  # B2B/B2C/EXP/SEZ
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    ack_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Gstr2bLine(Base):
    __tablename__ = "gstr2b_lines"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"))
    supplier_gstin: Mapped[str] = mapped_column(String(20))
    doc_no: Mapped[str] = mapped_column(String(60))
    doc_date: Mapped[datetime] = mapped_column(DateTime)
    taxable_value: Mapped[float] = mapped_column(Numeric(12, 2))
    tax_value: Mapped[float] = mapped_column(Numeric(12, 2))
    igst: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    cgst: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    sgst: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    cess: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    match_status: Mapped[str] = mapped_column(String(20), default="UNMATCHED")  # MATCHED/MISMATCH/MISSING
    match_ref_invoice_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("invoices.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
