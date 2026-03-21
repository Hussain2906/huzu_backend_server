from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.mobile_updates import AndroidLatestReleaseResponse
from app.services.mobile_release_service import (
    get_latest_active_android_release,
    serialize_android_release,
)

router = APIRouter(prefix="/mobile/android", tags=["mobile-updates"])


@router.get("/latest", response_model=AndroidLatestReleaseResponse)
def latest_android_release(db: Session = Depends(get_db)) -> AndroidLatestReleaseResponse:
    release = get_latest_active_android_release(db)
    if not release:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active Android release configured.",
        )

    try:
        return serialize_android_release(release)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )
