from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_company_user
from app.db.models import InventoryLedger, Invoice, InvoiceType, Product, StockItem, StockReason, User

router = APIRouter(prefix="/v1/inventory", tags=["inventory"])


class StockOut(BaseModel):
    product_id: str
    product_name: str
    qty_on_hand: float


class AdjustRequest(BaseModel):
    product_id: str
    new_qty: float = Field(ge=0)
    notes: str | None = None


class StockMoveOut(BaseModel):
    id: str
    created_at: datetime
    reference: str
    qty_in: float
    qty_out: float
    balance: float
    reason: StockReason
    notes: str | None


def _move_reference(row: InventoryLedger, invoice: Invoice | None) -> str:
    if invoice:
        if row.ref_type == "invoice":
            label = "Sale" if invoice.invoice_type == InvoiceType.SALES else "Purchase"
            return f"{label} {invoice.invoice_no}"
        if row.ref_type == "sale_return":
            return f"Return {invoice.invoice_no}"
        if row.reason == StockReason.CANCEL:
            return f"Cancel {invoice.invoice_no}"
    if row.ref_type == "import":
        return "Import"
    if row.ref_type == "manual" or row.reason == StockReason.ADJUSTMENT:
        return "Adjustment"
    return row.reason.value.title()


@router.get("/stock", response_model=list[StockOut])
def list_stock(
    db: Session = Depends(get_db),
    user: User = Depends(require_company_user),
) -> list[StockOut]:
    rows = (
        db.query(Product, StockItem)
        .outerjoin(
            StockItem,
            and_(StockItem.product_id == Product.id, StockItem.company_id == user.company_id),
        )
        .filter(Product.company_id == user.company_id)
        .order_by(Product.name.asc())
        .all()
    )
    return [
        StockOut(
            product_id=product.id,
            product_name=product.name,
            qty_on_hand=float(stock.qty_on_hand) if stock else 0.0,
        )
        for product, stock in rows
    ]


@router.post("/adjust", response_model=StockOut)
def adjust_stock(
    payload: AdjustRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_company_user),
) -> StockOut:
    product = db.get(Product, payload.product_id)
    if not product or product.company_id != user.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    stock = (
        db.query(StockItem)
        .filter(StockItem.company_id == user.company_id, StockItem.product_id == product.id)
        .first()
    )
    if not stock:
        stock = StockItem(company_id=user.company_id, product_id=product.id, qty_on_hand=0)
        db.add(stock)
        db.flush()

    change = float(payload.new_qty) - float(stock.qty_on_hand)
    stock.qty_on_hand = payload.new_qty
    stock.updated_at = datetime.utcnow()

    db.add(
        InventoryLedger(
            company_id=user.company_id,
            product_id=product.id,
            qty_change=change,
            reason=StockReason.ADJUSTMENT,
            ref_type="manual",
            ref_id=None,
            notes=payload.notes,
            created_by=user.id,
        )
    )
    db.commit()

    return StockOut(product_id=product.id, product_name=product.name, qty_on_hand=float(stock.qty_on_hand))


@router.get("/moves/{product_id}", response_model=list[StockMoveOut])
def list_stock_moves(
    product_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_company_user),
) -> list[StockMoveOut]:
    product = db.get(Product, product_id)
    if not product or product.company_id != user.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    rows = (
        db.query(InventoryLedger, Invoice)
        .outerjoin(Invoice, InventoryLedger.ref_id == Invoice.id)
        .filter(InventoryLedger.company_id == user.company_id, InventoryLedger.product_id == product_id)
        .order_by(InventoryLedger.created_at.asc(), InventoryLedger.id.asc())
        .all()
    )

    balance = 0.0
    moves: list[StockMoveOut] = []
    for ledger, invoice in rows:
        change = float(ledger.qty_change)
        balance += change
        qty_in = change if change > 0 else 0.0
        qty_out = abs(change) if change < 0 else 0.0
        moves.append(
            StockMoveOut(
                id=ledger.id,
                created_at=ledger.created_at,
                reference=_move_reference(ledger, invoice),
                qty_in=qty_in,
                qty_out=qty_out,
                balance=balance,
                reason=ledger.reason,
                notes=ledger.notes,
            )
        )

    return list(reversed(moves))
