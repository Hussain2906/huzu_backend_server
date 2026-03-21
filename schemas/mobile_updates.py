from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field, ValidationInfo, field_serializer, field_validator


class AndroidLatestReleaseResponse(BaseModel):
    versionCode: int = Field(..., ge=1)
    versionName: str = Field(..., min_length=1, max_length=40)
    minSupportedVersionCode: int = Field(..., ge=1)
    mandatory: bool
    apkUrl: str = Field(..., min_length=1, max_length=1024)
    sha256: str = Field(..., min_length=64, max_length=64)
    releaseNotes: str | None = None
    publishedAt: datetime

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        normalized = value.strip().lower()
        if len(normalized) != 64:
            raise ValueError("sha256 must be 64 hex characters")
        if any(char not in "0123456789abcdef" for char in normalized):
            raise ValueError("sha256 must be a lowercase hex string")
        return normalized

    @field_validator("apkUrl")
    @classmethod
    def validate_apk_url(cls, value: str) -> str:
        url = value.strip()
        if not url.startswith("https://"):
            raise ValueError("apkUrl must be an HTTPS URL")
        return url

    @field_validator("minSupportedVersionCode")
    @classmethod
    def validate_min_supported(
        cls,
        min_supported: int,
        info: ValidationInfo,
    ) -> int:
        version_code = info.data.get("versionCode")
        if version_code is not None and min_supported > version_code:
            raise ValueError("minSupportedVersionCode cannot exceed versionCode")
        return min_supported

    @field_serializer("publishedAt")
    def serialize_published_at(self, value: datetime) -> str:
        normalized = (
            value.replace(tzinfo=timezone.utc)
            if value.tzinfo is None
            else value.astimezone(timezone.utc)
        )
        return normalized.isoformat().replace("+00:00", "Z")
