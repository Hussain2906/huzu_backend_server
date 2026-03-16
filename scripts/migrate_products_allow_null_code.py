from __future__ import annotations

import sqlite3
from pathlib import Path


def main() -> None:
    db_path = Path(__file__).resolve().parents[1] / "erp.db"
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(products)")
    info = cur.fetchall()
    if not info:
        print("Products table not found")
        conn.close()
        return

    notnull = {row[1]: row[3] for row in info}
    if notnull.get("product_code") == 0:
        print("product_code already nullable")
        conn.close()
        return

    cur.execute(
        """
        CREATE TABLE products_new (
            id TEXT PRIMARY KEY,
            company_id TEXT,
            category_id TEXT,
            name TEXT NOT NULL,
            product_code TEXT,
            hsn TEXT,
            selling_rate NUMERIC,
            purchase_rate NUMERIC,
            unit TEXT,
            taxable BOOLEAN,
            tax_rate NUMERIC,
            reorder_level NUMERIC,
            status TEXT,
            created_at DATETIME,
            updated_at DATETIME,
            UNIQUE(company_id, product_code)
        )
        """
    )
    cur.execute(
        """
        INSERT INTO products_new (
            id,
            company_id,
            category_id,
            name,
            product_code,
            hsn,
            selling_rate,
            purchase_rate,
            unit,
            taxable,
            tax_rate,
            reorder_level,
            status,
            created_at,
            updated_at
        )
        SELECT
            id,
            company_id,
            category_id,
            name,
            product_code,
            hsn,
            selling_rate,
            purchase_rate,
            unit,
            taxable,
            tax_rate,
            reorder_level,
            status,
            created_at,
            updated_at
        FROM products
        """
    )
    cur.execute("DROP TABLE products")
    cur.execute("ALTER TABLE products_new RENAME TO products")

    conn.commit()
    conn.close()
    print("Rebuilt products table with nullable product_code")


if __name__ == "__main__":
    main()
