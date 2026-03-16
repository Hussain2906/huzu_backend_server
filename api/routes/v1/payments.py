from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_company_user
from app.schemas.payments import PaymentCreate, PaymentOut, AllocationRequest
from app.services.payments.payment_service import create_payment, allocate_payment
from app.db.models import Payment

router = APIRouter(prefix="/v1/payments", tags=["payments"])


@router.get("", response_model=list[PaymentOut])
def list_payments(db: Session = Depends(get_db), user=Depends(require_company_user)):
    payments = (
        db.query(Payment)
        .filter(Payment.company_id == user.company_id)
        .order_by(Payment.created_at.desc())
        .all()
    )
    return [
        PaymentOut(
            id=p.id,
            amount=float(p.amount),
            mode=p.mode.value if hasattr(p.mode, "value") else str(p.mode),
            status=p.status,
        )
        for p in payments
    ]

@router.post("", response_model=PaymentOut)
def add_payment(payload: PaymentCreate, db: Session = Depends(get_db), user=Depends(require_company_user)):
    try:
        payment = create_payment(db, user.company_id, payload.model_dump())
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return PaymentOut(id=payment.id, amount=float(payment.amount), mode=payment.mode.value, status=payment.status)


@router.post("/{payment_id}/allocate")
def allocate(payment_id: str, payload: AllocationRequest, db: Session = Depends(get_db), user=Depends(require_company_user)):
    try:
        rows = allocate_payment(db, payment_id, user.company_id, [a.model_dump() for a in payload.allocations])
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"allocations": len(rows)}
