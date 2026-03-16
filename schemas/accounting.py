from datetime import datetime
from pydantic import BaseModel, Field
from typing import List, Literal

class LedgerCreate(BaseModel):
    code: str = Field(min_length=2)
    name: str
    type: Literal["ASSET", "LIABILITY", "EQUITY", "INCOME", "EXPENSE"]
    parent_id: str | None = None
    is_bank: bool = False

class LedgerOut(BaseModel):
    id: str
    code: str
    name: str
    type: str
    parent_id: str | None
    is_bank: bool
    status: str

class JournalLineIn(BaseModel):
    ledger_id: str
    dr: float = 0
    cr: float = 0
    line_ref: str | None = None

class VoucherCreate(BaseModel):
    voucher_type: str
    number: str
    date: datetime
    narration: str | None = None
    ref_type: str | None = None
    ref_id: str | None = None
    lines: List[JournalLineIn]

class VoucherOut(BaseModel):
    id: str
    voucher_type: str
    number: str
    date: datetime
    status: str
    narration: str | None


class VoucherLineOut(BaseModel):
    id: str
    ledger_id: str
    ledger_code: str | None = None
    ledger_name: str | None = None
    dr: float
    cr: float
    line_ref: str | None = None


class VoucherDetailOut(VoucherOut):
    ref_type: str | None = None
    ref_id: str | None = None
    created_by: str | None = None
    approved_by: str | None = None
    lines: List[VoucherLineOut]
