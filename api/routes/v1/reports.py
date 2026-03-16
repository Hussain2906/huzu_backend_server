from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_company_user
from app.services.accounting.report_service import trial_balance, ledger_report, pl_summary, balance_sheet

router = APIRouter(prefix="/v1/reports", tags=["reports"])


@router.get("/trial-balance")
def get_trial_balance(as_of: datetime, db: Session = Depends(get_db), user=Depends(require_company_user)):
    return trial_balance(db, user.company_id, as_of)


@router.get("/ledger/{ledger_id}")
def get_ledger(ledger_id: str, date_from: datetime, date_to: datetime, db: Session = Depends(get_db), user=Depends(require_company_user)):
    return ledger_report(db, user.company_id, ledger_id, date_from, date_to)


@router.get("/pl")
def get_pl(date_from: datetime, date_to: datetime, db: Session = Depends(get_db), user=Depends(require_company_user)):
    return pl_summary(db, user.company_id, date_from, date_to)


@router.get("/balance-sheet")
def get_bs(as_of: datetime, db: Session = Depends(get_db), user=Depends(require_company_user)):
    return balance_sheet(db, user.company_id, as_of)
