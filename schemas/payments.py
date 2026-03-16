from datetime import datetime
from typing import List
from pydantic import BaseModel, Field

class PaymentCreate(BaseModel):
    counterparty_type: str
    counterparty_id: str | None = None
    mode: str
    amount: float
    ref_no: str | None = None
    ref_date: datetime | None = None
    notes: str | None = None

class PaymentOut(BaseModel):
    id: str
    amount: float
    mode: str
    status: str

class AllocationCreate(BaseModel):
    invoice_id: str
    amount: float

class AllocationRequest(BaseModel):
    allocations: List[AllocationCreate]
