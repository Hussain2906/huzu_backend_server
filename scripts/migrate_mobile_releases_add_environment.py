from __future__ import annotations

from pathlib import Path
import sys

from sqlalchemy import inspect, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.db.session import engine


def main() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("mobile_releases"):
        print("Table mobile_releases does not exist. Nothing to migrate.")
        return

    existing_columns = {
        column["name"]
        for column in inspector.get_columns("mobile_releases")
    }

    with engine.begin() as conn:
        if "environment" not in existing_columns:
            conn.execute(
                text("ALTER TABLE mobile_releases ADD COLUMN environment VARCHAR(20)")
            )
            print("Added mobile_releases.environment")

        conn.execute(
            text(
                "UPDATE mobile_releases "
                "SET environment = :environment "
                "WHERE environment IS NULL OR TRIM(environment) = ''"
            ),
            {"environment": settings.app_env},
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS "
                "ix_mobile_releases_platform_environment_active "
                "ON mobile_releases(platform, environment, is_active)"
            )
        )

    print(
        "Backfilled mobile_releases.environment using "
        f"APP_ENV={settings.app_env!r} and ensured the lookup index exists."
    )


if __name__ == "__main__":
    main()
