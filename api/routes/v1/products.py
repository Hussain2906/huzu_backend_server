from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_db, require_company_user
from app.db.models import (
    InventoryLedger,
    InvoiceLine,
    Product,
    ProductCategory,
    QuotationLine,
    StockItem,
    StockReason,
    User,
)

router = APIRouter(prefix="/v1/products", tags=["products"])


class CategoryIn(BaseModel):
    name: str


class CategoryOut(BaseModel):
    id: str
    name: str
    status: str


class ProductIn(BaseModel):
    name: str
    product_code: str | None = None
    category_id: str | None = None
    hsn: str | None = None
    selling_rate: float | None = None
    purchase_rate: float | None = None
    unit: str | None = None
    taxable: bool = True
    tax_rate: float | None = None
    reorder_level: float | None = None
    opening_stock: float | None = None
    extra_data: dict | None = None


class ProductUpdate(BaseModel):
    name: str | None = None
    product_code: str | None = None
    category_id: str | None = None
    hsn: str | None = None
    selling_rate: float | None = None
    purchase_rate: float | None = None
    unit: str | None = None
    taxable: bool | None = None
    tax_rate: float | None = None
    reorder_level: float | None = None
    opening_stock: float | None = None
    extra_data: dict | None = None


class ProductOut(BaseModel):
    id: str
    name: str
    product_code: str | None
    category_id: str | None
    hsn: str | None
    selling_rate: float | None
    purchase_rate: float | None
    unit: str | None
    taxable: bool
    tax_rate: float | None
    reorder_level: float | None
    opening_stock: float | None = None
    extra_data: dict | None = None
    status: str


class ProductDeleteOut(BaseModel):
    ok: bool
    message: str


def _generate_product_code(db: Session, user: User) -> str:
    while True:
        code = f"PRD-{uuid4().hex[:8].upper()}"
        exists = (
            db.query(Product)
            .filter(Product.company_id == user.company_id, Product.product_code == code)
            .first()
        )
        if not exists:
            return code


def _product_out(row: Product, opening_stock: float | None = None) -> ProductOut:
    return ProductOut(
        id=row.id,
        name=row.name,
        product_code=row.product_code,
        category_id=row.category_id,
        hsn=row.hsn,
        selling_rate=float(row.selling_rate) if row.selling_rate is not None else None,
        purchase_rate=float(row.purchase_rate) if row.purchase_rate is not None else None,
        unit=row.unit,
        taxable=row.taxable,
        tax_rate=float(row.tax_rate) if row.tax_rate is not None else None,
        reorder_level=float(row.reorder_level) if row.reorder_level is not None else None,
        opening_stock=opening_stock,
        extra_data=row.extra_json or {},
        status=row.status,
    )


def _apply_opening_stock(db: Session, user: User, product: Product, opening_stock: float | None) -> None:
    if opening_stock is None:
        return
    stock = (
        db.query(StockItem)
        .filter(StockItem.company_id == user.company_id, StockItem.product_id == product.id)
        .first()
    )
    current_qty = float(stock.qty_on_hand) if stock and stock.qty_on_hand is not None else 0.0
    target_qty = float(opening_stock)
    if stock is None and target_qty == 0:
        return
    if stock is None:
        stock = StockItem(company_id=user.company_id, product_id=product.id, qty_on_hand=0)
        db.add(stock)
        db.flush()
    delta = target_qty - current_qty
    stock.qty_on_hand = target_qty
    stock.updated_at = datetime.utcnow()
    if delta != 0:
        db.add(
            InventoryLedger(
                company_id=user.company_id,
                product_id=product.id,
                qty_change=delta,
                reason=StockReason.ADJUSTMENT,
                ref_type="manual",
                ref_id=None,
                notes="Opening stock updated from product form",
                created_by=user.id,
            )
        )


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(
    db: Session = Depends(get_db),
    user: User = Depends(require_company_user),
) -> list[CategoryOut]:
    rows = db.query(ProductCategory).filter(ProductCategory.company_id == user.company_id).all()
    return [CategoryOut(id=r.id, name=r.name, status=r.status) for r in rows]


@router.post("/categories", response_model=CategoryOut)
def create_category(
    payload: CategoryIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_company_user),
) -> CategoryOut:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category name required")
    existing = (
        db.query(ProductCategory)
        .filter(
            ProductCategory.company_id == user.company_id,
            func.lower(ProductCategory.name) == name.lower(),
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category already exists")

    row = ProductCategory(company_id=user.company_id, name=name)
    db.add(row)
    db.commit()
    return CategoryOut(id=row.id, name=row.name, status=row.status)


@router.patch("/categories/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: str,
    payload: CategoryIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_company_user),
) -> CategoryOut:
    row = db.get(ProductCategory, category_id)
    if not row or row.company_id != user.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category name required")
    existing = (
        db.query(ProductCategory)
        .filter(
            ProductCategory.company_id == user.company_id,
            func.lower(ProductCategory.name) == name.lower(),
            ProductCategory.id != row.id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category already exists")

    row.name = name
    db.commit()
    return CategoryOut(id=row.id, name=row.name, status=row.status)


@router.get("", response_model=list[ProductOut])
def list_products(
    db: Session = Depends(get_db),
    user: User = Depends(require_company_user),
) -> list[ProductOut]:
    rows = db.query(Product).filter(Product.company_id == user.company_id).all()
    stocks = (
        db.query(StockItem)
        .filter(StockItem.company_id == user.company_id)
        .all()
    )
    stock_map = {row.product_id: float(row.qty_on_hand or 0) for row in stocks}
    return [_product_out(r, stock_map.get(r.id)) for r in rows]


@router.get("/{product_id}", response_model=ProductOut)
def get_product(
    product_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_company_user),
) -> ProductOut:
    row = db.get(Product, product_id)
    if not row or row.company_id != user.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    stock = (
        db.query(StockItem)
        .filter(StockItem.company_id == user.company_id, StockItem.product_id == row.id)
        .first()
    )
    return _product_out(row, float(stock.qty_on_hand or 0) if stock else None)


@router.post("", response_model=ProductOut)
def create_product(
    payload: ProductIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_company_user),
) -> ProductOut:
    next_code = (payload.product_code or "").strip()
    next_code = next_code or _generate_product_code(db, user)
    next_category_id = (payload.category_id or "").strip() or None
    if next_code:
        exists = (
            db.query(Product)
            .filter(Product.company_id == user.company_id, Product.product_code == next_code)
            .first()
        )
        if exists:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Product code already exists")

    row = Product(
        company_id=user.company_id,
        name=payload.name.strip(),
        product_code=next_code,
        category_id=next_category_id,
        hsn=payload.hsn,
        selling_rate=payload.selling_rate,
        purchase_rate=payload.purchase_rate,
        unit=payload.unit,
        taxable=payload.taxable,
        tax_rate=payload.tax_rate,
        reorder_level=payload.reorder_level,
        extra_json=payload.extra_data or {},
    )
    db.add(row)
    try:
        db.flush()
        _apply_opening_stock(db, user, row, payload.opening_stock)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Product code already exists")
    return _product_out(row, payload.opening_stock)


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: str,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_company_user),
) -> ProductOut:
    row = db.get(Product, product_id)
    if not row or row.company_id != user.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    updates = payload.model_dump(exclude_unset=True)
    opening_stock = updates.pop("opening_stock", None) if "opening_stock" in updates else None
    if "category_id" in updates:
        updates["category_id"] = (updates["category_id"] or "").strip() or None
    if "product_code" in updates:
        raw_code = updates["product_code"] or ""
        next_code = raw_code.strip() or None
        if next_code:
            exists = (
                db.query(Product)
                .filter(
                    Product.company_id == user.company_id,
                    Product.product_code == next_code,
                    Product.id != row.id,
                )
                .first()
            )
            if exists:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Product code already exists")
        updates["product_code"] = next_code

    if "name" in updates and updates["name"] is not None:
        updates["name"] = updates["name"].strip()

    for field, value in updates.items():
        if field == "extra_data":
            row.extra_json = value or {}
        else:
            setattr(row, field, value)

    row.updated_at = datetime.utcnow()
    try:
        _apply_opening_stock(db, user, row, opening_stock)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Product code already exists")
    stock = (
        db.query(StockItem)
        .filter(StockItem.company_id == user.company_id, StockItem.product_id == row.id)
        .first()
    )
    return _product_out(row, float(stock.qty_on_hand or 0) if stock else None)


@router.post("/{product_id}/deactivate", response_model=ProductOut)
def deactivate_product(
    product_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_company_user),
) -> ProductOut:
    row = db.get(Product, product_id)
    if not row or row.company_id != user.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    row.status = "INACTIVE"
    db.commit()

    stock = (
        db.query(StockItem)
        .filter(StockItem.company_id == user.company_id, StockItem.product_id == row.id)
        .first()
    )
    return _product_out(row, float(stock.qty_on_hand or 0) if stock else None)


@router.delete("/{product_id}", response_model=ProductDeleteOut)
def delete_product(
    product_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_company_user),
) -> ProductDeleteOut:
    row = db.get(Product, product_id)
    if not row or row.company_id != user.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    has_invoice_refs = (
        db.query(InvoiceLine.id)
        .filter(InvoiceLine.product_id == row.id)
        .first()
        is not None
    )
    if has_invoice_refs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Product cannot be deleted because it is used in invoices",
        )

    has_quotation_refs = (
        db.query(QuotationLine.id)
        .filter(QuotationLine.product_id == row.id)
        .first()
        is not None
    )
    if has_quotation_refs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Product cannot be deleted because it is used in quotations",
        )

    stock = (
        db.query(StockItem)
        .filter(StockItem.company_id == user.company_id, StockItem.product_id == row.id)
        .first()
    )
    if stock and float(stock.qty_on_hand or 0) != 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Product cannot be deleted while stock is available",
        )

    has_inventory_history = (
        db.query(InventoryLedger.id)
        .filter(InventoryLedger.company_id == user.company_id, InventoryLedger.product_id == row.id)
        .first()
        is not None
    )
    if has_inventory_history:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Product cannot be deleted because stock history exists",
        )

    if stock:
        db.delete(stock)
    db.delete(row)
    db.commit()

    return ProductDeleteOut(ok=True, message="Product deleted")
