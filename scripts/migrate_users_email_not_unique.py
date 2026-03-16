from __future__ import annotations

import re
import sqlite3
from pathlib import Path


def main() -> None:
    db_path = Path(__file__).resolve().parents[1] / "erp.db"
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'")
    row = cur.fetchone()
    if not row or not row[0]:
        print("Users table not found.")
        conn.close()
        return

    create_sql = row[0].lower()
    if not re.search(r"email[^,]*unique", create_sql):
        print("Users email already non-unique. No migration needed.")
        conn.close()
        return

    cur.execute("PRAGMA foreign_keys=off")
    cur.execute("BEGIN")
    cur.execute(
        """
        CREATE TABLE users_new (
            id TEXT PRIMARY KEY,
            company_id TEXT,
            username TEXT UNIQUE,
            email TEXT,
            password_hash TEXT NOT NULL,
            full_name TEXT,
            phone TEXT,
            role_label TEXT,
            allowed_modules TEXT,
            is_platform_admin INTEGER,
            status TEXT,
            created_at TEXT,
            last_seen_at TEXT,
            FOREIGN KEY(company_id) REFERENCES companies(id)
        )
        """
    )
    cur.execute(
        """
        INSERT INTO users_new (
            id, company_id, username, email, password_hash, full_name, phone,
            role_label, allowed_modules, is_platform_admin, status, created_at, last_seen_at
        )
        SELECT
            id, company_id, username, email, password_hash, full_name, phone,
            role_label, allowed_modules, is_platform_admin, status, created_at, last_seen_at
        FROM users
        """
    )
    cur.execute("DROP TABLE users")
    cur.execute("ALTER TABLE users_new RENAME TO users")
    cur.execute("COMMIT")
    cur.execute("PRAGMA foreign_keys=on")
    conn.close()
    print("Migration complete: users.email is no longer unique.")


if __name__ == "__main__":
    main()
