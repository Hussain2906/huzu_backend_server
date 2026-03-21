from __future__ import annotations

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import MobileRelease
from app.schemas.mobile_updates import AndroidLatestReleaseResponse


def get_latest_active_android_release(
    db: Session,
    *,
    environment: str | None = None,
) -> MobileRelease | None:
    target_environment = (environment or settings.app_env).strip() or settings.app_env
    return (
        db.query(MobileRelease)
        .filter(
            MobileRelease.platform == "android",
            MobileRelease.environment == target_environment,
            MobileRelease.is_active.is_(True),
        )
        .order_by(MobileRelease.version_code.desc(), MobileRelease.published_at.desc())
        .first()
    )


def serialize_android_release(
    release: MobileRelease,
) -> AndroidLatestReleaseResponse:
    try:
        return AndroidLatestReleaseResponse(
            versionCode=release.version_code,
            versionName=release.version_name,
            minSupportedVersionCode=release.min_supported_version_code,
            mandatory=release.mandatory,
            apkUrl=release.apk_url,
            sha256=release.sha256,
            releaseNotes=release.release_notes,
            publishedAt=release.published_at,
        )
    except ValidationError as exc:
        raise ValueError(f"Invalid mobile release metadata: {exc.errors()}") from exc
