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
    cur.execute("PRAGMA table_info(invoice_lines)")
    existing = {row[1] for row in cur.fetchall()}

    if "discount_percent" not in existing:
        cur.execute("ALTER TABLE invoice_lines ADD COLUMN discount_percent NUMERIC")
        print("Added column discount_percent")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
