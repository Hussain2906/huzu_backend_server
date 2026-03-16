from datetime import datetime
from sqlalchemy.orm import Session

from app.db.models import MoneyEntry, MoneyDirection, PaymentMode, JournalLine, JournalVoucher
from app.services.accounting.ledger_service import ledger_map
from app.services.accounting.voucher_service import create_voucher


BANK_MODES = {
    PaymentMode.BANK_TRANSFER,
    PaymentMode.CARD,
    PaymentMode.CHEQUE,
    PaymentMode.UPI,
}


def _cash_or_bank(ledgers: dict, mode: PaymentMode):
    return ledgers["1100"] if mode in BANK_MODES else ledgers["1000"]


def _expense_ledger(ledgers: dict):
    return ledgers.get("5700") or ledgers.get("5100")


def _build_lines(direction: MoneyDirection, amount: float, mode: PaymentMode, ledgers: dict):
    cash_bank = _cash_or_bank(ledgers, mode)
    if direction == MoneyDirection.IN:
        income = ledgers["4200"]
        return [
            {"ledger_id": cash_bank.id, "dr": amount, "cr": 0},
            {"ledger_id": income.id, "dr": 0, "cr": amount},
        ]
    expense = _expense_ledger(ledgers)
    return [
        {"ledger_id": expense.id, "dr": amount, "cr": 0},
        {"ledger_id": cash_bank.id, "dr": 0, "cr": amount},
    ]


def create_money_entry(db: Session, company_id: str, direction: MoneyDirection, payload: dict) -> MoneyEntry:
    mode = PaymentMode(payload["mode"])
    entry = MoneyEntry(
        company_id=company_id,
        direction=direction,
        amount=payload.get("amount"),
        entry_date=payload.get("entry_date") or datetime.utcnow(),
        mode=mode,
        reference=payload.get("reference"),
        notes=payload.get("notes"),
        category=payload.get("category"),
    )
    db.add(entry)
    db.flush()

    ledgers = ledger_map(db, company_id)
    lines = _build_lines(direction, float(entry.amount), mode, ledgers)
    vtype = "MONEY_IN" if direction == MoneyDirection.IN else "MONEY_OUT"
    number = f"{'MI' if direction == MoneyDirection.IN else 'MO'}-{entry.id[:6]}"
    voucher = create_voucher(
        db=db,
        company_id=company_id,
        voucher_type=vtype,
        number=number,
        date=entry.entry_date,
        lines=lines,
        narration=entry.notes or f"{vtype} entry",
        ref_type="money_entry",
        ref_id=entry.id,
        user_id=None,
    )
    entry.voucher_id = voucher.id
    db.commit()
    return entry


def update_money_entry(db: Session, entry: MoneyEntry, payload: dict) -> MoneyEntry:
    mode = PaymentMode(payload["mode"])
    entry.amount = payload.get("amount", entry.amount)
    entry.entry_date = payload.get("entry_date", entry.entry_date)
    entry.mode = mode
    entry.reference = payload.get("reference")
    entry.notes = payload.get("notes")
    entry.category = payload.get("category")

    if entry.voucher_id:
        voucher = db.get(JournalVoucher, entry.voucher_id)
        if voucher:
            ledgers = ledger_map(db, entry.company_id)
            lines = _build_lines(entry.direction, float(entry.amount), mode, ledgers)
            db.query(JournalLine).filter(JournalLine.voucher_id == voucher.id).delete()
            for line in lines:
                db.add(JournalLine(voucher_id=voucher.id, ledger_id=line["ledger_id"], dr=line["dr"], cr=line["cr"]))
            voucher.date = entry.entry_date
            voucher.narration = entry.notes or voucher.narration
    db.commit()
    return entry


def delete_money_entry(db: Session, entry: MoneyEntry) -> None:
    if entry.voucher_id:
        db.query(JournalLine).filter(JournalLine.voucher_id == entry.voucher_id).delete()
        db.query(JournalVoucher).filter(JournalVoucher.id == entry.voucher_id).delete()
    db.delete(entry)
    db.commit()
