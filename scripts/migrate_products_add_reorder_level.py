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
    existing = {row[1] for row in cur.fetchall()}

    if "reorder_level" not in existing:
        cur.execute("ALTER TABLE products ADD COLUMN reorder_level NUMERIC")
        print("Added column reorder_level")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
