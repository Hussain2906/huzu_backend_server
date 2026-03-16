from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_company_user
from app.db.models import JournalLine, JournalVoucher, Ledger, LedgerType, User
from app.schemas.accounting import (
    LedgerCreate,
    LedgerOut,
    VoucherCreate,
    VoucherDetailOut,
    VoucherLineOut,
    VoucherOut,
)
from app.services.accounting.ledger_service import create_ledger, ensure_default_ledgers
from app.services.accounting.voucher_service import create_voucher

router = APIRouter(prefix="/v1/accounting", tags=["accounting"])


@router.get("/accounts", response_model=list[LedgerOut])
def list_accounts(db: Session = Depends(get_db), user=Depends(require_company_user)):
    ensure_default_ledgers(db, user.company_id)
    rows = db.query(Ledger).filter(Ledger.company_id == user.company_id).order_by(Ledger.code).all()
    return [
        LedgerOut(
            id=r.id,
            code=r.code,
            name=r.name,
            type=r.type.value,
            parent_id=r.parent_id,
            is_bank=r.is_bank,
            status=r.status,
        )
        for r in rows
    ]


@router.post("/accounts", response_model=LedgerOut)
def add_account(payload: LedgerCreate, db: Session = Depends(get_db), user=Depends(require_company_user)):
    ledger = create_ledger(
        db=db,
        company_id=user.company_id,
        code=payload.code,
        name=payload.name,
        ltype=LedgerType(payload.type),
        parent_id=payload.parent_id,
        is_bank=payload.is_bank,
    )
    return LedgerOut(
        id=ledger.id,
        code=ledger.code,
        name=ledger.name,
        type=ledger.type.value,
        parent_id=ledger.parent_id,
        is_bank=ledger.is_bank,
        status=ledger.status,
    )


@router.get("/vouchers", response_model=list[VoucherOut])
def list_vouchers(db: Session = Depends(get_db), user=Depends(require_company_user)):
    rows = (
        db.query(JournalVoucher)
        .filter(JournalVoucher.company_id == user.company_id)
        .order_by(JournalVoucher.date.desc())
        .all()
    )
    return [
        VoucherOut(
            id=r.id,
            voucher_type=r.voucher_type,
            number=r.number,
            date=r.date,
            status=r.status,
            narration=r.narration,
        )
        for r in rows
    ]


@router.post("/vouchers", response_model=VoucherOut)
def add_voucher(payload: VoucherCreate, db: Session = Depends(get_db), user=Depends(require_company_user)):
    total_dr = round(sum(l.dr for l in payload.lines), 2)
    total_cr = round(sum(l.cr for l in payload.lines), 2)
    if abs(total_dr - total_cr) > 0.01:
        raise HTTPException(status_code=400, detail="Voucher not balanced")

    voucher = create_voucher(
        db=db,
        company_id=user.company_id,
        voucher_type=payload.voucher_type,
        number=payload.number,
        date=payload.date,
        lines=[l.model_dump() for l in payload.lines],
        narration=payload.narration,
        ref_type=payload.ref_type,
        ref_id=payload.ref_id,
        user_id=user.id,
    )
    return VoucherOut(
        id=voucher.id,
        voucher_type=voucher.voucher_type,
        number=voucher.number,
        date=voucher.date,
        status=voucher.status,
        narration=voucher.narration,
    )


@router.get("/vouchers/{voucher_id}", response_model=VoucherDetailOut)
def get_voucher(voucher_id: str, db: Session = Depends(get_db), user=Depends(require_company_user)):
    voucher = (
        db.query(JournalVoucher)
        .filter(JournalVoucher.id == voucher_id, JournalVoucher.company_id == user.company_id)
        .first()
    )
    if not voucher:
        raise HTTPException(status_code=404, detail="Voucher not found")

    lines = (
        db.query(JournalLine)
        .filter(JournalLine.voucher_id == voucher.id)
        .order_by(JournalLine.id.asc())
        .all()
    )
    ledgers = {
        row.id: row
        for row in db.query(Ledger).filter(Ledger.company_id == user.company_id).all()
    }
    user_ids = {value for value in [voucher.created_by, voucher.approved_by] if value}
    users = {
        row.id: row
        for row in db.query(User).filter(User.id.in_(user_ids)).all()
    } if user_ids else {}

    return VoucherDetailOut(
        id=voucher.id,
        voucher_type=voucher.voucher_type,
        number=voucher.number,
        date=voucher.date,
        status=voucher.status,
        narration=voucher.narration,
        ref_type=voucher.ref_type,
        ref_id=voucher.ref_id,
        created_by=(users.get(voucher.created_by).full_name or users.get(voucher.created_by).username) if users.get(voucher.created_by) else None,
        approved_by=(users.get(voucher.approved_by).full_name or users.get(voucher.approved_by).username) if users.get(voucher.approved_by) else None,
        lines=[
            VoucherLineOut(
                id=line.id,
                ledger_id=line.ledger_id,
                ledger_code=ledgers.get(line.ledger_id).code if ledgers.get(line.ledger_id) else None,
                ledger_name=ledgers.get(line.ledger_id).name if ledgers.get(line.ledger_id) else None,
                dr=float(line.dr or 0),
                cr=float(line.cr or 0),
                line_ref=line.line_ref,
            )
            for line in lines
        ],
    )
