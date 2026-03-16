from __future__ import annotations

from sqlalchemy import text

from app.db.base import Base
from app.db.bootstrap_admins import ensure_platform_admin_users
from app.db.session import engine


def _column_names(conn, table: str) -> set[str]:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).mappings().all()
    return {row.get("name") for row in rows}


def ensure_sqlite_schema() -> None:
    if not engine.url.drivername.startswith("sqlite"):
        return

    # Ensure tables exist before we attempt to alter them.
    import app.db.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    ensure_platform_admin_users()

    with engine.begin() as conn:
        company_profile_cols = _column_names(conn, "company_profiles")
        if "extra_json" not in company_profile_cols:
            conn.execute(text("ALTER TABLE company_profiles ADD COLUMN extra_json TEXT"))

        customer_cols = _column_names(conn, "customers")
        if "extra_json" not in customer_cols:
            conn.execute(text("ALTER TABLE customers ADD COLUMN extra_json TEXT"))

        supplier_cols = _column_names(conn, "suppliers")
        if "extra_json" not in supplier_cols:
            conn.execute(text("ALTER TABLE suppliers ADD COLUMN extra_json TEXT"))

        invoice_cols = _column_names(conn, "invoices")
        if "extra_json" not in invoice_cols:
            conn.execute(text("ALTER TABLE invoices ADD COLUMN extra_json TEXT"))

        product_cols = _column_names(conn, "products")
        if "extra_json" not in product_cols:
            conn.execute(text("ALTER TABLE products ADD COLUMN extra_json TEXT"))

        quote_cols = _column_names(conn, "quotations")
        if "party_type" not in quote_cols:
            conn.execute(
                text("ALTER TABLE quotations ADD COLUMN party_type VARCHAR(20) DEFAULT 'CUSTOMER'")
            )
            conn.execute(text("UPDATE quotations SET party_type = 'CUSTOMER' WHERE party_type IS NULL"))
        if "supplier_id" not in quote_cols:
            conn.execute(text("ALTER TABLE quotations ADD COLUMN supplier_id VARCHAR(36)"))
        if "supplier_snapshot_json" not in quote_cols:
            conn.execute(text("ALTER TABLE quotations ADD COLUMN supplier_snapshot_json TEXT"))

        line_cols = _column_names(conn, "quotation_lines")
        if "line_order" not in line_cols:
            conn.execute(text("ALTER TABLE quotation_lines ADD COLUMN line_order INTEGER DEFAULT 0"))
            conn.execute(text("UPDATE quotation_lines SET line_order = 0 WHERE line_order IS NULL"))
