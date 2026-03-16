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
    cur.execute("PRAGMA table_info(suppliers)")
    existing = {row[1] for row in cur.fetchall()}

    columns = {
        "business_name": "TEXT",
        "email": "TEXT",
        "gst_registration_type": "TEXT",
        "gst_state": "TEXT",
        "address_line1": "TEXT",
        "address_line2": "TEXT",
        "city": "TEXT",
        "state": "TEXT",
        "pincode": "TEXT",
    }

    for name, ddl in columns.items():
        if name in existing:
            continue
        cur.execute(f"ALTER TABLE suppliers ADD COLUMN {name} {ddl}")
        print(f"Added column {name}")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
