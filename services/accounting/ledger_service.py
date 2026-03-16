from sqlalchemy.orm import Session

from app.db.models import Ledger, LedgerType

DEFAULT_LEDGERS = [
    ("1000", "Cash", LedgerType.ASSET, False),
    ("1100", "Bank", LedgerType.ASSET, True),
    ("1200", "Accounts Receivable", LedgerType.ASSET, False),
    ("2100", "Accounts Payable", LedgerType.LIABILITY, False),
    ("3100", "Equity", LedgerType.EQUITY, False),
    ("4100", "Sales", LedgerType.INCOME, False),
    ("4200", "Other Income", LedgerType.INCOME, False),
    ("5100", "Purchases", LedgerType.EXPENSE, False),
    ("5200", "COGS", LedgerType.EXPENSE, False),
    ("5300", "Inventory", LedgerType.ASSET, False),
    ("5400", "Output GST", LedgerType.LIABILITY, False),
    ("5500", "Input GST", LedgerType.ASSET, False),
    ("5600", "Rounding", LedgerType.EXPENSE, False),
    ("5700", "Expenses", LedgerType.EXPENSE, False),
]


def ensure_default_ledgers(db: Session, company_id: str) -> dict[str, Ledger]:
    existing = {
        (l.code): l
        for l in db.query(Ledger).filter(Ledger.company_id == company_id).all()
    }
    created = {}
    for code, name, ltype, is_bank in DEFAULT_LEDGERS:
        if code in existing:
            created[code] = existing[code]
            continue
        row = Ledger(company_id=company_id, code=code, name=name, type=ltype, is_bank=is_bank)
        db.add(row)
        db.flush()
        created[code] = row
    db.commit()
    return {**existing, **created}


def ledger_map(db: Session, company_id: str) -> dict[str, Ledger]:
    return ensure_default_ledgers(db, company_id)


def create_ledger(db: Session, company_id: str, code: str, name: str, ltype: LedgerType, parent_id: str | None, is_bank: bool) -> Ledger:
    ledger = Ledger(
        company_id=company_id,
        code=code,
        name=name,
        type=ltype,
        parent_id=parent_id,
        is_bank=is_bank,
    )
    db.add(ledger)
    db.commit()
    return ledger
