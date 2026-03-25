from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.db.session import engine
from app.services.party_service import ensure_party_links_for_legacy_data


def _has_table(inspector, table: str) -> bool:
    return table in inspector.get_table_names()


def _has_column(inspector, table: str, column: str) -> bool:
    if not _has_table(inspector, table):
        return False
    cols = inspector.get_columns(table)
    return any(col.get("name") == column for col in cols)


def _add_party_id_column(conn, inspector, table: str) -> None:
    if not _has_table(inspector, table):
        print(f"[skip] table '{table}' not found")
        return
    if _has_column(inspector, table, "party_id"):
        print(f"[ok] {table}.party_id already exists")
        return
    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN party_id VARCHAR(36)"))
    print(f"[done] added {table}.party_id")


def _add_index(conn, table: str) -> None:
    conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table}_party_id ON {table}(party_id)"))
    print(f"[done] ensured index ix_{table}_party_id")


def main() -> None:
    inspector = inspect(engine)
    with engine.begin() as conn:
        _add_party_id_column(conn, inspector, "customers")
        _add_party_id_column(conn, inspector, "suppliers")
        _add_index(conn, "customers")
        _add_index(conn, "suppliers")

    # Try to backfill links; keep migration success even if party backfill fails.
    try:
        with Session(engine) as session:
            ensure_party_links_for_legacy_data(session)
            session.commit()
        print("[done] ensured legacy customer/supplier party links")
    except Exception as exc:
        print(f"[warn] columns created but backfill failed: {exc}")

    print("[ok] migration complete")


if __name__ == "__main__":
    main()
