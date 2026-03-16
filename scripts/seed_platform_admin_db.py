import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.bootstrap_admins import ensure_platform_admin_users


def main() -> None:
    ensure_platform_admin_users()


if __name__ == "__main__":
    main()
