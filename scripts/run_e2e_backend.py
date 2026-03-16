from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    db_path = os.getenv("E2E_DB_PATH", "testing/.e2e/erp_e2e.db")
    port = int(os.getenv("E2E_BACKEND_PORT", "8000"))

    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    if db_file.exists():
        db_file.unlink()

    os.environ.setdefault("DATABASE_URL", f"sqlite+pysqlite:///{db_path}")
    os.environ.setdefault("APP_ENV", "test")

    from scripts.seed_test_data import main as seed_test_data

    seed_test_data()

    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
