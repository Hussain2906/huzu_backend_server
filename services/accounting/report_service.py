from datetime import datetime
from typing import List, Dict

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import JournalLine, JournalVoucher, Ledger, LedgerType


def trial_balance(db: Session, company_id: str, as_of: datetime) -> List[Dict]:
    rows = (
        db.query(
            Ledger.id.label("ledger_id"),
            Ledger.code,
            Ledger.name,
            func.sum(JournalLine.dr).label("dr"),
            func.sum(JournalLine.cr).label("cr"),
        )
        .join(JournalVoucher, JournalVoucher.id == JournalLine.voucher_id)
        .join(Ledger, Ledger.id == JournalLine.ledger_id)
        .filter(JournalVoucher.company_id == company_id, JournalVoucher.date <= as_of)
        .group_by(Ledger.id, Ledger.code, Ledger.name)
        .order_by(Ledger.code)
        .all()
    )
    return [
        {
            "ledger_id": r.ledger_id,
            "code": r.code,
            "name": r.name,
            "dr": float(r.dr or 0),
            "cr": float(r.cr or 0),
            "balance": float(r.dr or 0) - float(r.cr or 0),
        }
        for r in rows
    ]


def ledger_report(db: Session, company_id: str, ledger_id: str, date_from: datetime, date_to: datetime) -> List[Dict]:
    rows = (
        db.query(JournalVoucher.date, JournalVoucher.number, JournalLine.dr, JournalLine.cr, JournalVoucher.narration)
        .join(JournalVoucher, JournalVoucher.id == JournalLine.voucher_id)
        .filter(
            JournalVoucher.company_id == company_id,
            JournalLine.ledger_id == ledger_id,
            JournalVoucher.date >= date_from,
            JournalVoucher.date <= date_to,
        )
        .order_by(JournalVoucher.date, JournalVoucher.number)
        .all()
    )
    return [
        {
            "date": r.date,
            "number": r.number,
            "dr": float(r.dr or 0),
            "cr": float(r.cr or 0),
            "narration": r.narration,
        }
        for r in rows
    ]


def pl_summary(db: Session, company_id: str, date_from: datetime, date_to: datetime) -> Dict:
    rows = (
        db.query(
            Ledger.type,
            func.sum(JournalLine.dr).label("dr"),
            func.sum(JournalLine.cr).label("cr"),
        )
        .join(JournalVoucher, JournalVoucher.id == JournalLine.voucher_id)
        .join(Ledger, Ledger.id == JournalLine.ledger_id)
        .filter(
            JournalVoucher.company_id == company_id,
            JournalVoucher.date >= date_from,
            JournalVoucher.date <= date_to,
            Ledger.type.in_([LedgerType.INCOME, LedgerType.EXPENSE]),
        )
        .group_by(Ledger.type)
        .all()
    )
    income = expense = 0.0
    for r in rows:
        bal = float(r.cr or 0) - float(r.dr or 0)
        if r.type == LedgerType.INCOME:
            income += bal
        else:
            expense += -bal  # expenses usually dr>cr
    return {"income": income, "expense": expense, "net_profit": income - expense}


def balance_sheet(db: Session, company_id: str, as_of: datetime) -> Dict:
    rows = (
        db.query(
            Ledger.type,
            func.sum(JournalLine.dr).label("dr"),
            func.sum(JournalLine.cr).label("cr"),
        )
        .join(JournalVoucher, JournalVoucher.id == JournalLine.voucher_id)
        .join(Ledger, Ledger.id == JournalLine.ledger_id)
        .filter(JournalVoucher.company_id == company_id, JournalVoucher.date <= as_of)
        .group_by(Ledger.type)
        .all()
    )
    sums = {t: 0.0 for t in LedgerType}
    for r in rows:
        bal = float(r.dr or 0) - float(r.cr or 0)
        sums[r.type] = bal
    assets = sums.get(LedgerType.ASSET, 0.0)
    liabilities = -sums.get(LedgerType.LIABILITY, 0.0)
    equity = -sums.get(LedgerType.EQUITY, 0.0)
    return {
        "assets": assets,
        "liabilities": liabilities,
        "equity": equity,
        "balance": assets - liabilities - equity,
    }
