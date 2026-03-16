from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_company_user
from app.db.models import MoneyDirection, MoneyEntry, User
from app.schemas.money import MoneyEntryCreate, MoneyEntryOut
from app.services.money_service import create_money_entry, update_money_entry, delete_money_entry

router = APIRouter(prefix="/v1", tags=["money"])


def _list_entries(db: Session, company_id: str, direction: MoneyDirection, date_from: datetime | None, date_to: datetime | None):
    query = db.query(MoneyEntry).filter(MoneyEntry.company_id == company_id, MoneyEntry.direction == direction)
    if date_from:
        query = query.filter(MoneyEntry.entry_date >= date_from)
    if date_to:
        query = query.filter(MoneyEntry.entry_date <= date_to)
    return query.order_by(MoneyEntry.entry_date.desc()).all()


def _to_out(entry: MoneyEntry) -> MoneyEntryOut:
    return MoneyEntryOut(
        id=entry.id,
        direction=entry.direction.value,
        amount=float(entry.amount),
        currency=entry.currency,
        entry_date=entry.entry_date,
        mode=entry.mode.value,
        reference=entry.reference,
        notes=entry.notes,
        category=entry.category,
    )


@router.get("/money-in", response_model=list[MoneyEntryOut])
def list_money_in(
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_company_user),
):
    rows = _list_entries(db, user.company_id, MoneyDirection.IN, date_from, date_to)
    return [_to_out(row) for row in rows]


@router.get("/money-out", response_model=list[MoneyEntryOut])
def list_money_out(
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_company_user),
):
    rows = _list_entries(db, user.company_id, MoneyDirection.OUT, date_from, date_to)
    return [_to_out(row) for row in rows]


@router.get("/money-in/{entry_id}", response_model=MoneyEntryOut)
def get_money_in(entry_id: str, db: Session = Depends(get_db), user: User = Depends(require_company_user)):
    entry = db.get(MoneyEntry, entry_id)
    if not entry or entry.company_id != user.company_id or entry.direction != MoneyDirection.IN:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Money entry not found")
    return _to_out(entry)


@router.get("/money-out/{entry_id}", response_model=MoneyEntryOut)
def get_money_out(entry_id: str, db: Session = Depends(get_db), user: User = Depends(require_company_user)):
    entry = db.get(MoneyEntry, entry_id)
    if not entry or entry.company_id != user.company_id or entry.direction != MoneyDirection.OUT:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Money entry not found")
    return _to_out(entry)


@router.post("/money-in", response_model=MoneyEntryOut)
def create_money_in(payload: MoneyEntryCreate, db: Session = Depends(get_db), user: User = Depends(require_company_user)):
    entry = create_money_entry(db, user.company_id, MoneyDirection.IN, payload.model_dump())
    return _to_out(entry)


@router.post("/money-out", response_model=MoneyEntryOut)
def create_money_out(payload: MoneyEntryCreate, db: Session = Depends(get_db), user: User = Depends(require_company_user)):
    entry = create_money_entry(db, user.company_id, MoneyDirection.OUT, payload.model_dump())
    return _to_out(entry)


@router.patch("/money-in/{entry_id}", response_model=MoneyEntryOut)
def update_money_in(
    entry_id: str, payload: MoneyEntryCreate, db: Session = Depends(get_db), user: User = Depends(require_company_user)
):
    entry = db.get(MoneyEntry, entry_id)
    if not entry or entry.company_id != user.company_id or entry.direction != MoneyDirection.IN:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Money entry not found")
    entry = update_money_entry(db, entry, payload.model_dump())
    return _to_out(entry)


@router.patch("/money-out/{entry_id}", response_model=MoneyEntryOut)
def update_money_out(
    entry_id: str, payload: MoneyEntryCreate, db: Session = Depends(get_db), user: User = Depends(require_company_user)
):
    entry = db.get(MoneyEntry, entry_id)
    if not entry or entry.company_id != user.company_id or entry.direction != MoneyDirection.OUT:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Money entry not found")
    entry = update_money_entry(db, entry, payload.model_dump())
    return _to_out(entry)


@router.delete("/money-in/{entry_id}")
def delete_money_in(entry_id: str, db: Session = Depends(get_db), user: User = Depends(require_company_user)):
    entry = db.get(MoneyEntry, entry_id)
    if not entry or entry.company_id != user.company_id or entry.direction != MoneyDirection.IN:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Money entry not found")
    delete_money_entry(db, entry)
    return {"ok": True}


@router.delete("/money-out/{entry_id}")
def delete_money_out(entry_id: str, db: Session = Depends(get_db), user: User = Depends(require_company_user)):
    entry = db.get(MoneyEntry, entry_id)
    if not entry or entry.company_id != user.company_id or entry.direction != MoneyDirection.OUT:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Money entry not found")
    delete_money_entry(db, entry)
    return {"ok": True}
