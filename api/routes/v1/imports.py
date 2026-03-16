from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel
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
    format: str = "xlsx",
    user: User = Depends(require_company_user),
):
    content, media_type, filename = build_template(module, output_format=format)
    return Response(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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
