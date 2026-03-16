from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_company_user
from app.db.models import DownloadJob, User

router = APIRouter(prefix="/v1/downloads", tags=["downloads"])


class DownloadRequest(BaseModel):
    job_type: str
    filters: dict


class DownloadOut(BaseModel):
    id: str
    status: str
    result_path: str | None


@router.post("", response_model=DownloadOut)
def create_download_job(
    payload: DownloadRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_company_user),
) -> DownloadOut:
    job = DownloadJob(
        company_id=user.company_id,
        job_type=payload.job_type,
        filters_json=payload.filters,
        created_by=user.id,
    )
    db.add(job)
    db.commit()

    return DownloadOut(id=job.id, status=job.status, result_path=job.result_path)


@router.get("/{job_id}", response_model=DownloadOut)
def get_download_job(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_company_user),
) -> DownloadOut:
    job = db.get(DownloadJob, job_id)
    if not job or job.company_id != user.company_id:
        return DownloadOut(id=job_id, status="NOT_FOUND", result_path=None)

    return DownloadOut(id=job.id, status=job.status, result_path=job.result_path)
