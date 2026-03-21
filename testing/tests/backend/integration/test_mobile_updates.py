from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.core.config import settings
from app.db.models import MobileRelease


def _release(
    *,
    environment: str,
    version_code: int,
    version_name: str,
    min_supported_version_code: int,
    apk_url: str = "https://api.example.com/downloads/myapp.apk",
    sha256: str = "a" * 64,
    mandatory: bool = False,
    is_active: bool = True,
    published_at: datetime | None = None,
) -> MobileRelease:
    return MobileRelease(
        platform="android",
        environment=environment,
        version_code=version_code,
        version_name=version_name,
        min_supported_version_code=min_supported_version_code,
        mandatory=mandatory,
        apk_url=apk_url,
        sha256=sha256,
        release_notes="Bug fixes and improvements",
        published_at=published_at or datetime.utcnow(),
        is_active=is_active,
    )


@pytest.mark.integration
def test_mobile_latest_returns_latest_active_release_for_current_environment(
    client,
    db_session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "app_env", "production")
    db_session.add_all(
        [
            _release(
                environment="production",
                version_code=14,
                version_name="1.4.0",
                min_supported_version_code=12,
                published_at=datetime.utcnow() - timedelta(days=1),
            ),
            _release(
                environment="production",
                version_code=15,
                version_name="1.5.0",
                min_supported_version_code=13,
                mandatory=True,
                apk_url="https://api.example.com/downloads/myapp-1.5.0+15.apk",
            ),
            _release(
                environment="staging",
                version_code=99,
                version_name="9.9.9",
                min_supported_version_code=99,
                apk_url="https://staging.example.com/downloads/myapp-9.9.9+99.apk",
            ),
            _release(
                environment="production",
                version_code=16,
                version_name="1.6.0",
                min_supported_version_code=14,
                is_active=False,
                apk_url="https://api.example.com/downloads/myapp-1.6.0+16.apk",
            ),
        ]
    )
    db_session.commit()

    response = client.get("/mobile/android/latest")
    body = response.json()

    assert response.status_code == 200, response.text
    assert body["versionCode"] == 15
    assert body["versionName"] == "1.5.0"
    assert body["minSupportedVersionCode"] == 13
    assert body["mandatory"] is True
    assert body["apkUrl"] == "https://api.example.com/downloads/myapp-1.5.0+15.apk"
    assert body["sha256"] == "a" * 64
    assert body["releaseNotes"] == "Bug fixes and improvements"
    assert body["publishedAt"].endswith("Z")


@pytest.mark.integration
def test_mobile_latest_returns_404_when_no_active_release_for_environment(
    client,
    db_session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "app_env", "production")
    db_session.add(
        _release(
            environment="staging",
            version_code=15,
            version_name="1.5.0",
            min_supported_version_code=13,
        )
    )
    db_session.commit()

    response = client.get("/mobile/android/latest")

    assert response.status_code == 404
    assert response.json()["detail"] == "No active Android release configured."


@pytest.mark.integration
def test_mobile_latest_returns_500_for_invalid_release_metadata(
    client,
    db_session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "app_env", "production")
    db_session.add(
        _release(
            environment="production",
            version_code=15,
            version_name="1.5.0",
            min_supported_version_code=13,
            apk_url="http://api.example.com/downloads/myapp-1.5.0+15.apk",
            sha256="not-a-valid-checksum",
        )
    )
    db_session.commit()

    response = client.get("/mobile/android/latest")

    assert response.status_code == 500
    assert "Invalid mobile release metadata" in response.json()["detail"]
