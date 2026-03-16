from datetime import datetime
from pydantic import BaseModel


class MoneyEntryCreate(BaseModel):
    amount: float
    entry_date: datetime
    mode: str
    reference: str | None = None
    notes: str | None = None
    category: str | None = None


class MoneyEntryOut(MoneyEntryCreate):
    id: str
    direction: str
    currency: str | None = None
