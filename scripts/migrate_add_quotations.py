from __future__ import annotations

import sqlite3
from pathlib import Path


def table_exists(cur: sqlite3.Cursor, name: str) -> bool:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def main() -> None:
    db_path = Path(__file__).resolve().parents[1] / "erp.db"
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    if not table_exists(cur, "quotations"):
        cur.execute(
            """
            CREATE TABLE quotations (
                id TEXT PRIMARY KEY,
                company_id TEXT,
                quotation_no TEXT,
                quotation_date DATETIME,
                valid_until DATETIME,
                status TEXT,
                customer_id TEXT,
                customer_snapshot_json TEXT,
                company_snapshot_json TEXT,
                salesperson TEXT,
                notes TEXT,
                terms TEXT,
                revision_of_id TEXT,
                revision_no INTEGER,
                subtotal NUMERIC,
                grand_total NUMERIC,
                converted_invoice_id TEXT,
                converted_at DATETIME,
                created_by TEXT,
                created_at DATETIME,
                updated_at DATETIME,
                UNIQUE(company_id, quotation_no)
            )
            """
        )
        print("Created quotations table")

    if not table_exists(cur, "quotation_lines"):
        cur.execute(
            """
            CREATE TABLE quotation_lines (
                id TEXT PRIMARY KEY,
                quotation_id TEXT,
                line_type TEXT,
                product_id TEXT,
                description TEXT,
                qty NUMERIC,
                unit TEXT,
                price NUMERIC,
                discount_percent NUMERIC,
                line_total NUMERIC
            )
            """
        )
        print("Created quotation_lines table")

    cur.execute("PRAGMA table_info(invoices)")
    existing = {row[1] for row in cur.fetchall()}
    if "source_quotation_id" not in existing:
        cur.execute("ALTER TABLE invoices ADD COLUMN source_quotation_id TEXT")
        print("Added source_quotation_id to invoices")
    if "source_quotation_no" not in existing:
        cur.execute("ALTER TABLE invoices ADD COLUMN source_quotation_no TEXT")
        print("Added source_quotation_no to invoices")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
