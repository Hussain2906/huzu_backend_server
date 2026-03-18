from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_company_user
from app.db.models import ImportJob, User
from app.services.import_service import (
    build_template,
    import_inventory,
    import_inventory_report,
    import_products,
    import_purchases,
    import_sales,
    parse_stock_summary_report_content,
    parse_tabular_upload,
    parse_tabular_upload_content,
)
from app.services.party_import_service import (
    commit_party_import,
    get_party_import_batch_detail,
    list_party_import_batches,
    preview_party_import,
)

router = APIRouter(prefix="/v1/imports", tags=["imports"])


class ImportRequest(BaseModel):
    job_type: str
    source_path: str | None = None


class ImportOut(BaseModel):
    id: str
    status: str
    result_json: dict | None


class ImportError(BaseModel):
    row: int
    field: str | None = None
    message: str


class ImportResult(BaseModel):
    status: str
    imported: int
    errors: list[ImportError] | None = None
    summary: dict | None = None


class PartyImportPreviewRow(BaseModel):
    row_number: int
    parsed_values: dict
    detected_role: str | None = None
    warnings: list[dict] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)
    action: str
    matched_party_id: str | None = None
    match_confidence: str | None = None
    match_reason: str | None = None


class PartyImportPreviewOut(BaseModel):
    batch_id: str
    file_name: str
    file_hash: str
    summary: dict
    rows: list[PartyImportPreviewRow]


class PartyImportCommitIn(BaseModel):
    batch_id: str
    duplicate_policy: str = "UPDATE_MATCHED"


class PartyImportCommitOut(BaseModel):
    batch_id: str
    status: str
    summary: dict


class PartyImportHistoryRow(BaseModel):
    batch_id: str
    source: str
    file_name: str | None = None
    status: str
    duplicate_policy: str | None = None
    total_rows: int
    create_count: int
    update_count: int
    duplicate_count: int
    error_count: int
    warning_count: int
    success_count: int
    fail_count: int
    skipped_count: int
    created_at: str | None = None
    committed_at: str | None = None


class PartyImportBatchDetailOut(BaseModel):
    batch_id: str
    status: str
    file_name: str | None = None
    duplicate_policy: str | None = None
    created_at: str | None = None
    committed_at: str | None = None
    summary: dict
    rows: list[dict]


@router.post("", response_model=ImportOut)
def create_import_job(
    payload: ImportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_company_user),
) -> ImportOut:
    job = ImportJob(
        company_id=user.company_id,
        job_type=payload.job_type,
        source_path=payload.source_path,
        created_by=user.id,
    )
    db.add(job)
    db.commit()

    return ImportOut(id=job.id, status=job.status, result_json=job.result_json)


@router.get("/{job_id}", response_model=ImportOut)
def get_import_job(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_company_user),
) -> ImportOut:
    job = db.get(ImportJob, job_id)
    if not job or job.company_id != user.company_id:
        return ImportOut(id=job_id, status="NOT_FOUND", result_json=None)

    return ImportOut(id=job.id, status=job.status, result_json=job.result_json)


@router.get("/templates/{module}")
def download_template(
    module: str,
    format: str = "csv",
    user: User = Depends(require_company_user),
):
    content, media_type, filename = build_template(module, output_format=format)
    return Response(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/parties/preview", response_model=PartyImportPreviewOut)
def preview_party_import_endpoint(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_company_user),
) -> PartyImportPreviewOut:
    content = file.file.read()
    result = preview_party_import(
        db,
        user,
        filename=file.filename or "party_import.xlsx",
        content=content,
    )
    return PartyImportPreviewOut(**result)


@router.post("/parties/commit", response_model=PartyImportCommitOut)
def commit_party_import_endpoint(
    payload: PartyImportCommitIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_company_user),
) -> PartyImportCommitOut:
    result = commit_party_import(
        db,
        user,
        batch_id=payload.batch_id,
        duplicate_policy=payload.duplicate_policy,
    )
    return PartyImportCommitOut(**result)


@router.get("/parties/history", response_model=list[PartyImportHistoryRow])
def party_import_history(
    limit: int = 20,
    db: Session = Depends(get_db),
    user: User = Depends(require_company_user),
) -> list[PartyImportHistoryRow]:
    rows = list_party_import_batches(db, user, limit=limit)
    return [
        PartyImportHistoryRow(
            **{
                **row,
                "created_at": row.get("created_at").isoformat() if row.get("created_at") else None,
                "committed_at": row.get("committed_at").isoformat() if row.get("committed_at") else None,
            }
        )
        for row in rows
    ]


@router.get("/parties/{batch_id}", response_model=PartyImportBatchDetailOut)
def get_party_import_batch(
    batch_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_company_user),
) -> PartyImportBatchDetailOut:
    row = get_party_import_batch_detail(db, user, batch_id)
    return PartyImportBatchDetailOut(
        **{
            **row,
            "created_at": row.get("created_at").isoformat() if row.get("created_at") else None,
            "committed_at": row.get("committed_at").isoformat() if row.get("committed_at") else None,
        }
    )


@router.post("/{module}", response_model=ImportResult)
def import_module(
    module: str,
    file: UploadFile = File(...),
    create_missing_products: bool = Form(True),
    create_missing_categories: bool = Form(True),
    update_existing_prices: bool = Form(False),
    update_existing_reorder_level: bool = Form(True),
    update_stock: bool = Form(True),
    db: Session = Depends(get_db),
    user: User = Depends(require_company_user),
) -> ImportResult:
    filename = (file.filename or "").lower()
    if not (filename.endswith(".csv") or filename.endswith(".xlsx") or filename.endswith(".xlsm")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only CSV and XLSX files are supported")

    content = file.file.read()
    options = {
        "create_missing_products": create_missing_products,
        "create_missing_categories": create_missing_categories,
        "update_existing_prices": update_existing_prices,
        "update_existing_reorder_level": update_existing_reorder_level,
        "update_stock": update_stock,
    }
    job = ImportJob(
        company_id=user.company_id,
        job_type=module,
        source_path=file.filename,
        created_by=user.id,
        status="PROCESSING",
    )
    db.add(job)
    db.flush()
    try:
        if module == "inventory_report":
            rows, headers = parse_stock_summary_report_content(file.filename or "inventory_report.xlsx", content)
        else:
            rows, headers = parse_tabular_upload_content(file.filename or "import.xlsx", content)
        if not rows:
            response = ImportResult(status="FAILED", imported=0, errors=[ImportError(row=0, field=None, message="No data rows")])
        elif module == "products":
            result = import_products(db, user, rows, headers)
            errors = result.get("errors")
            response = ImportResult(
                status=result.get("status", "SUCCESS" if not errors else "FAILED"),
                imported=result.get("imported", 0),
                errors=[ImportError(**err) for err in errors] if errors else None,
                summary=result.get("summary"),
            )
        elif module == "purchases":
            result = import_purchases(db, user, rows, headers)
            errors = result.get("errors")
            response = ImportResult(
                status=result.get("status", "SUCCESS" if not errors else "FAILED"),
                imported=result.get("imported", 0),
                errors=[ImportError(**err) for err in errors] if errors else None,
                summary=result.get("summary"),
            )
        elif module == "sales":
            result = import_sales(db, user, rows, headers)
            errors = result.get("errors")
            response = ImportResult(
                status=result.get("status", "SUCCESS" if not errors else "FAILED"),
                imported=result.get("imported", 0),
                errors=[ImportError(**err) for err in errors] if errors else None,
                summary=result.get("summary"),
            )
        elif module == "inventory":
            result = import_inventory(db, user, rows, headers)
            errors = result.get("errors")
            response = ImportResult(
                status=result.get("status", "SUCCESS" if not errors else "FAILED"),
                imported=result.get("imported", 0),
                errors=[ImportError(**err) for err in errors] if errors else None,
                summary=result.get("summary"),
            )
        elif module == "inventory_report":
            result = import_inventory_report(db, user, rows, headers, options=options)
            errors = result.get("errors")
            response = ImportResult(
                status=result.get("status", "SUCCESS" if not errors else "FAILED"),
                imported=result.get("imported", 0),
                errors=[ImportError(**err) for err in errors] if errors else None,
                summary=result.get("summary"),
            )
        else:
            response = ImportResult(
                status="FAILED",
                imported=0,
                errors=[ImportError(row=0, field=None, message="Unknown module")],
            )
    except HTTPException as exc:
        db.rollback()
        response = ImportResult(
            status="FAILED",
            imported=0,
            errors=[ImportError(row=0, field=None, message=str(exc.detail))],
        )
        db.add(job)
    except Exception as exc:
        db.rollback()
        response = ImportResult(
            status="FAILED",
            imported=0,
            errors=[ImportError(row=0, field=None, message=str(exc))],
        )
        db.add(job)

    job.status = response.status
    job.result_json = response.model_dump()
    db.commit()
    return response
