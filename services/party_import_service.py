from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import (
    Party,
    PartyImportBatch,
    PartyImportRow,
    PartyRole,
    PartyRoleType,
    User,
)
from app.services.import_service import parse_tabular_upload_content
from app.services.party_service import (
    apply_party_updates,
    derive_balance_nature,
    generate_party_code,
    is_valid_email,
    is_valid_gstin,
    normalize_email,
    normalize_gstin,
    normalize_name,
    normalize_phone,
    upsert_customer_profile_from_party,
    upsert_supplier_profile_from_party,
)

IMPORT_SOURCE = "import_old_party_report"

REQUIRED_COLUMNS = {
    "sr no",
    "name",
    "phone",
    "category",
    "credit",
    "type",
    "gst no",
    "billing type",
    "dob",
    "business name",
    "email",
    "billing address",
    "billing states & u.t.",
    "billing postal code",
    "delivery address",
    "delivery states & u.t.",
    "delivery postal code",
    "payment term",
    "send alerts",
    "favourite party",
}

HEADER_MAP = {
    "sr no": "source_row_no",
    "name": "name",
    "phone": "phone",
    "category": "category_name",
    "credit": "opening_balance",
    "type": "role",
    "gst no": "gstin",
    "billing type": "billing_type",
    "dob": "dob",
    "business name": "business_name",
    "email": "email",
    "billing address": "billing_address_line",
    "billing states & u.t.": "billing_state",
    "billing postal code": "billing_postal_code",
    "delivery address": "delivery_address_line",
    "delivery states & u.t.": "delivery_state",
    "delivery postal code": "delivery_postal_code",
    "payment term": "payment_term",
    "send alerts": "send_alerts",
    "favourite party": "favourite_party",
}

INVALID_PHONE_TOKENS = {"", "-", "$PHONE", "NA", "N/A", "NULL", "NONE"}



def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()



def _normalize_header(value: str) -> str:
    cleaned = _clean(value).lower()
    for token in ("/", "\\", "(", ")", ".", ":", "-", "_"):
        cleaned = cleaned.replace(token, " ")
    cleaned = cleaned.replace("&", " & ")
    cleaned = " ".join(cleaned.split())
    cleaned = cleaned.replace(" u t", " u.t.")
    return cleaned



def _coerce_bool(value: Any) -> tuple[bool | None, str | None]:
    raw = _clean(value).upper()
    if not raw:
        return None, None
    if raw in {"YES", "Y", "TRUE", "1"}:
        return True, None
    if raw in {"NO", "N", "FALSE", "0"}:
        return False, None
    return None, f"Unrecognized boolean value '{raw}'"



def _parse_date(value: Any) -> tuple[datetime | None, str | None]:
    raw = _clean(value)
    if not raw:
        return None, None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(raw, fmt), None
        except Exception:
            continue
    try:
        return datetime.fromisoformat(raw), None
    except Exception:
        return None, f"Invalid DOB '{raw}'"



def _parse_opening_balance(value: Any) -> tuple[Decimal | None, str | None]:
    raw = _clean(value)
    if not raw:
        return Decimal("0"), None

    sanitized = (
        raw.replace("₹", "")
        .replace("Rs.", "")
        .replace("INR", "")
        .replace(",", "")
        .replace(" ", "")
    )
    if not sanitized:
        return Decimal("0"), None
    try:
        return Decimal(sanitized), None
    except (InvalidOperation, ValueError):
        return None, f"Invalid credit/opening balance '{raw}'"



def _parse_role(value: Any) -> tuple[PartyRoleType | None, str | None]:
    raw = _clean(value).upper()
    if raw == "CUSTOMER":
        return PartyRoleType.CUSTOMER, None
    if raw == "SUPPLIER":
        return PartyRoleType.SUPPLIER, None
    return None, "TYPE must be CUSTOMER or SUPPLIER"



def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in row.items():
        source_key = _normalize_header(key)
        mapped = HEADER_MAP.get(source_key)
        if mapped:
            normalized[mapped] = _clean(value)
    return normalized



def _find_match_candidates(db: Session, company_id: str, parsed: dict[str, Any]) -> tuple[list[Party], str | None, str | None]:
    gstin = parsed.get("gstin")
    if gstin:
        rows = db.query(Party).filter(Party.company_id == company_id, Party.gstin == gstin).all()
        if rows:
            return rows, "HIGH", "GSTIN exact match"

    phone = parsed.get("phone")
    name = parsed.get("name")
    if phone and name:
        rows = (
            db.query(Party)
            .filter(
                Party.company_id == company_id,
                Party.phone == phone,
                func.lower(Party.name) == name.lower(),
            )
            .all()
        )
        if rows:
            return rows, "MEDIUM", "Phone + name exact match"

    if name and parsed.get("billing_address_line"):
        role = parsed.get("role")
        if role:
            rows = (
                db.query(Party)
                .join(PartyRole, PartyRole.party_id == Party.id)
                .filter(
                    Party.company_id == company_id,
                    PartyRole.role == role,
                    func.lower(Party.name) == name.lower(),
                    func.lower(func.coalesce(Party.billing_address_line, "")) == parsed["billing_address_line"].lower(),
                )
                .all()
            )
            if rows:
                return rows, "LOW", "Name + role + billing address match"

    return [], None, None



def _preview_action_for_candidates(candidates: list[Party], confidence: str | None) -> tuple[str, str | None]:
    if not candidates:
        return "CREATE", None
    if len(candidates) > 1:
        return "POSSIBLE_DUPLICATE", "Multiple potential matches found"
    if confidence in {"HIGH", "MEDIUM"}:
        return "UPDATE", None
    return "POSSIBLE_DUPLICATE", "Low confidence match; review before update"



def _validate_and_parse_row(row_number: int, raw_row: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    mapped = _normalize_row(raw_row)
    parsed: dict[str, Any] = {
        "source_row_no": _clean(mapped.get("source_row_no")) or str(row_number),
        "name": normalize_name(mapped.get("name")),
        "phone": None,
        "category_name": _clean(mapped.get("category_name")) or None,
        "opening_balance": Decimal("0"),
        "balance_nature": None,
        "role": None,
        "gstin": None,
        "billing_type": _clean(mapped.get("billing_type")) or None,
        "dob": None,
        "business_name": normalize_name(mapped.get("business_name")),
        "email": normalize_email(mapped.get("email")),
        "billing_address_line": _clean(mapped.get("billing_address_line")) or None,
        "billing_state": _clean(mapped.get("billing_state")) or None,
        "billing_postal_code": _clean(mapped.get("billing_postal_code")) or None,
        "delivery_address_line": _clean(mapped.get("delivery_address_line")) or None,
        "delivery_state": _clean(mapped.get("delivery_state")) or None,
        "delivery_postal_code": _clean(mapped.get("delivery_postal_code")) or None,
        "payment_term": _clean(mapped.get("payment_term")) or None,
        "send_alerts": False,
        "favourite_party": False,
    }

    if not parsed["name"]:
        errors.append({"row": row_number, "field": "NAME", "message": "NAME is required"})

    role, role_error = _parse_role(mapped.get("role"))
    if role_error:
        errors.append({"row": row_number, "field": "TYPE", "message": role_error})
    parsed["role"] = role

    raw_phone = _clean(mapped.get("phone"))
    if raw_phone.upper() in INVALID_PHONE_TOKENS:
        parsed["phone"] = None
    else:
        normalized_phone = normalize_phone(raw_phone)
        if raw_phone and not normalized_phone:
            warnings.append({"row": row_number, "field": "PHONE", "message": f"Invalid phone '{raw_phone}' converted to null"})
        parsed["phone"] = normalized_phone

    opening_balance, opening_error = _parse_opening_balance(mapped.get("opening_balance"))
    if opening_error:
        errors.append({"row": row_number, "field": "CREDIT", "message": opening_error})
    else:
        parsed["opening_balance"] = opening_balance or Decimal("0")
        parsed["balance_nature"] = derive_balance_nature(parsed["opening_balance"])

    gstin = normalize_gstin(mapped.get("gstin"))
    parsed["gstin"] = gstin
    if gstin and not is_valid_gstin(gstin):
        warnings.append({"row": row_number, "field": "GST NO", "message": f"GST number '{gstin}' format looks invalid"})

    if parsed["email"] and not is_valid_email(parsed["email"]):
        warnings.append({"row": row_number, "field": "EMAIL", "message": f"Email '{parsed['email']}' format looks invalid"})

    dob, dob_error = _parse_date(mapped.get("dob"))
    if dob_error:
        warnings.append({"row": row_number, "field": "DOB", "message": dob_error})
    parsed["dob"] = dob

    send_alerts, send_alerts_err = _coerce_bool(mapped.get("send_alerts"))
    if send_alerts_err:
        warnings.append({"row": row_number, "field": "SEND ALERTS", "message": send_alerts_err})
    parsed["send_alerts"] = bool(send_alerts)

    favourite, favourite_err = _coerce_bool(mapped.get("favourite_party"))
    if favourite_err:
        warnings.append({"row": row_number, "field": "FAVOURITE PARTY", "message": favourite_err})
    parsed["favourite_party"] = bool(favourite)

    return parsed, warnings, errors



def preview_party_import(db: Session, user: User, *, filename: str, content: bytes) -> dict[str, Any]:
    rows, headers = parse_tabular_upload_content(filename, content)
    if not rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No data rows found in file")

    normalized_headers = {_normalize_header(h) for h in headers if h}
    missing = sorted(REQUIRED_COLUMNS - normalized_headers)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required columns: {', '.join(missing)}",
        )

    file_hash = hashlib.sha256(content).hexdigest()
    batch = PartyImportBatch(
        company_id=user.company_id,
        source=IMPORT_SOURCE,
        file_name=filename,
        file_hash=file_hash,
        status="PREVIEW_READY",
        total_rows=len(rows),
        created_by=user.id,
    )
    db.add(batch)
    db.flush()

    response_rows: list[dict[str, Any]] = []
    create_count = 0
    update_count = 0
    duplicate_count = 0
    error_count = 0
    warning_count = 0

    for idx, raw in enumerate(rows):
        row_number = idx + 2
        parsed, warnings, errors = _validate_and_parse_row(row_number, raw)

        action = "ERROR"
        match_confidence = None
        match_reason = None
        matched_party_id = None

        if not errors:
            candidates, match_confidence, match_reason = _find_match_candidates(db, user.company_id, parsed)
            action, auto_note = _preview_action_for_candidates(candidates, match_confidence)
            if auto_note:
                warnings.append({"row": row_number, "field": "MATCH", "message": auto_note})
            if candidates:
                matched_party_id = candidates[0].id if len(candidates) == 1 else None

        if action == "CREATE":
            create_count += 1
        elif action == "UPDATE":
            update_count += 1
        elif action == "POSSIBLE_DUPLICATE":
            duplicate_count += 1
        elif action == "ERROR":
            error_count += 1

        warning_count += len(warnings)

        parsed_payload = dict(parsed)
        if isinstance(parsed_payload.get("opening_balance"), Decimal):
            parsed_payload["opening_balance"] = str(parsed_payload["opening_balance"])
        if isinstance(parsed_payload.get("dob"), datetime):
            parsed_payload["dob"] = parsed_payload["dob"].isoformat()
        if parsed_payload.get("role") is not None:
            parsed_payload["role"] = parsed_payload["role"].value

        row_record = PartyImportRow(
            batch_id=batch.id,
            company_id=user.company_id,
            row_number=row_number,
            role=parsed_payload.get("role"),
            action=action,
            status="PREVIEW",
            match_confidence=match_confidence,
            matched_party_id=matched_party_id,
            parsed_payload=parsed_payload,
            raw_payload=raw,
            warnings_json=warnings,
            errors_json=errors,
        )
        db.add(row_record)

        response_rows.append(
            {
                "row_number": row_number,
                "parsed_values": parsed_payload,
                "detected_role": parsed_payload.get("role"),
                "warnings": warnings,
                "errors": errors,
                "action": action,
                "matched_party_id": matched_party_id,
                "match_confidence": match_confidence,
                "match_reason": match_reason,
            }
        )

    batch.create_count = create_count
    batch.update_count = update_count
    batch.duplicate_count = duplicate_count
    batch.error_count = error_count
    batch.warning_count = warning_count
    batch.result_json = {
        "summary": {
            "total_rows": len(rows),
            "create": create_count,
            "update": update_count,
            "possible_duplicate": duplicate_count,
            "error": error_count,
            "warning": warning_count,
        }
    }

    db.commit()

    return {
        "batch_id": batch.id,
        "file_name": filename,
        "file_hash": file_hash,
        "summary": batch.result_json["summary"],
        "rows": response_rows,
    }



def _build_party_updates(parsed: dict[str, Any], *, batch_id: str, row_number: int, raw_payload: dict[str, Any]) -> dict[str, Any]:
    opening_balance = Decimal(str(parsed.get("opening_balance") or "0"))
    dob = parsed.get("dob")
    if isinstance(dob, str) and dob:
        try:
            dob = datetime.fromisoformat(dob)
        except Exception:
            dob = None

    return {
        "name": normalize_name(parsed.get("name")) or "Unknown Party",
        "display_name": normalize_name(parsed.get("name")),
        "phone": normalize_phone(parsed.get("phone")),
        "email": normalize_email(parsed.get("email")),
        "gstin": normalize_gstin(parsed.get("gstin")),
        "business_name": normalize_name(parsed.get("business_name")),
        "dob": dob,
        "billing_type": parsed.get("billing_type"),
        "payment_term": parsed.get("payment_term"),
        "send_alerts": bool(parsed.get("send_alerts")),
        "favourite_party": bool(parsed.get("favourite_party")),
        "opening_balance": float(opening_balance),
        "balance_nature": derive_balance_nature(opening_balance),
        "category_name": parsed.get("category_name"),
        "billing_address_line": parsed.get("billing_address_line"),
        "billing_state": parsed.get("billing_state"),
        "billing_postal_code": parsed.get("billing_postal_code"),
        "delivery_address_line": parsed.get("delivery_address_line"),
        "delivery_state": parsed.get("delivery_state"),
        "delivery_postal_code": parsed.get("delivery_postal_code"),
        "source": IMPORT_SOURCE,
        "source_row_no": int(str(parsed.get("source_row_no") or row_number)),
        "import_batch_id": batch_id,
        "raw_import_payload": raw_payload,
    }



def _ensure_role_profile(db: Session, party: Party, role: str | None) -> None:
    if role == PartyRoleType.CUSTOMER.value:
        upsert_customer_profile_from_party(db, party)
    elif role == PartyRoleType.SUPPLIER.value:
        upsert_supplier_profile_from_party(db, party)



def commit_party_import(
    db: Session,
    user: User,
    *,
    batch_id: str,
    duplicate_policy: str,
) -> dict[str, Any]:
    normalized_policy = _clean(duplicate_policy).upper() or "UPDATE_MATCHED"
    if normalized_policy not in {"UPDATE_MATCHED", "SKIP_DUPLICATES", "CREATE_NEW"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid duplicate policy")

    batch = db.get(PartyImportBatch, batch_id)
    if not batch or batch.company_id != user.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import batch not found")

    rows = (
        db.query(PartyImportRow)
        .filter(PartyImportRow.batch_id == batch_id, PartyImportRow.company_id == user.company_id)
        .order_by(PartyImportRow.row_number.asc())
        .all()
    )

    success_count = 0
    fail_count = 0
    skipped_count = 0
    created_count = 0
    updated_count = 0

    for row in rows:
        parsed = dict(row.parsed_payload or {})
        raw_payload = dict(row.raw_payload or {})
        existing_errors = list(row.errors_json or [])

        if existing_errors:
            row.status = "FAILED"
            fail_count += 1
            continue

        action = row.action
        matched_party_id = row.matched_party_id

        if action == "POSSIBLE_DUPLICATE" and normalized_policy == "SKIP_DUPLICATES":
            row.status = "SKIPPED"
            skipped_count += 1
            continue

        if action == "UPDATE" and normalized_policy == "SKIP_DUPLICATES":
            row.status = "SKIPPED"
            skipped_count += 1
            continue

        if action == "POSSIBLE_DUPLICATE" and normalized_policy == "UPDATE_MATCHED" and not matched_party_id:
            row.status = "FAILED"
            row.errors_json = existing_errors + [
                {"row": row.row_number, "field": "MATCH", "message": "Possible duplicate requires manual review or CREATE_NEW"}
            ]
            fail_count += 1
            continue

        target_mode = "CREATE"
        if normalized_policy == "UPDATE_MATCHED" and action == "UPDATE" and matched_party_id:
            target_mode = "UPDATE"
        elif normalized_policy == "UPDATE_MATCHED" and action == "POSSIBLE_DUPLICATE" and matched_party_id:
            target_mode = "UPDATE"
        elif normalized_policy == "SKIP_DUPLICATES" and action == "CREATE":
            target_mode = "CREATE"
        elif normalized_policy == "CREATE_NEW":
            target_mode = "CREATE"

        try:
            with db.begin_nested():
                party: Party | None = None
                if target_mode == "UPDATE":
                    party = db.get(Party, matched_party_id)
                    if not party or party.company_id != user.company_id:
                        raise ValueError("Matched party not found for update")
                else:
                    party = Party(
                        company_id=user.company_id,
                        code=generate_party_code(db, user.company_id),
                        name=normalize_name(parsed.get("name")) or "Unknown Party",
                    )
                    db.add(party)
                    db.flush()

                updates = _build_party_updates(parsed, batch_id=batch.id, row_number=row.row_number, raw_payload=raw_payload)
                apply_party_updates(party, updates, overwrite=True)

                role = parsed.get("role")
                _ensure_role_profile(db, party, role)

                row.applied_party_id = party.id
                row.status = "IMPORTED"
                row.updated_at = datetime.utcnow()

                if target_mode == "CREATE":
                    created_count += 1
                else:
                    updated_count += 1
                success_count += 1
        except Exception as exc:
            row.status = "FAILED"
            row.errors_json = existing_errors + [{"row": row.row_number, "field": None, "message": str(exc)}]
            fail_count += 1

    batch.status = "COMPLETED" if fail_count == 0 else ("PARTIAL_SUCCESS" if success_count > 0 else "FAILED")
    batch.duplicate_policy = normalized_policy
    batch.success_count = success_count
    batch.fail_count = fail_count
    batch.skipped_count = skipped_count
    batch.committed_at = datetime.utcnow()
    batch.result_json = {
        "summary": {
            "total_rows": batch.total_rows,
            "success": success_count,
            "failed": fail_count,
            "skipped": skipped_count,
            "created": created_count,
            "updated": updated_count,
            "policy": normalized_policy,
        }
    }

    db.commit()

    return {
        "batch_id": batch.id,
        "status": batch.status,
        "summary": batch.result_json["summary"],
    }



def list_party_import_batches(db: Session, user: User, limit: int = 20) -> list[dict[str, Any]]:
    rows = (
        db.query(PartyImportBatch)
        .filter(PartyImportBatch.company_id == user.company_id)
        .order_by(PartyImportBatch.created_at.desc())
        .limit(limit)
        .all()
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "batch_id": row.id,
                "source": row.source,
                "file_name": row.file_name,
                "status": row.status,
                "duplicate_policy": row.duplicate_policy,
                "total_rows": row.total_rows,
                "create_count": row.create_count,
                "update_count": row.update_count,
                "duplicate_count": row.duplicate_count,
                "error_count": row.error_count,
                "warning_count": row.warning_count,
                "success_count": row.success_count,
                "fail_count": row.fail_count,
                "skipped_count": row.skipped_count,
                "created_at": row.created_at,
                "committed_at": row.committed_at,
            }
        )
    return out



def get_party_import_batch_detail(db: Session, user: User, batch_id: str) -> dict[str, Any]:
    batch = db.get(PartyImportBatch, batch_id)
    if not batch or batch.company_id != user.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import batch not found")

    row_items = (
        db.query(PartyImportRow)
        .filter(PartyImportRow.batch_id == batch_id, PartyImportRow.company_id == user.company_id)
        .order_by(PartyImportRow.row_number.asc())
        .all()
    )
    rows: list[dict[str, Any]] = []
    for item in row_items:
        rows.append(
            {
                "row_number": item.row_number,
                "role": item.role,
                "action": item.action,
                "status": item.status,
                "match_confidence": item.match_confidence,
                "matched_party_id": item.matched_party_id,
                "applied_party_id": item.applied_party_id,
                "parsed_values": item.parsed_payload or {},
                "warnings": item.warnings_json or [],
                "errors": item.errors_json or [],
            }
        )

    return {
        "batch_id": batch.id,
        "status": batch.status,
        "file_name": batch.file_name,
        "duplicate_policy": batch.duplicate_policy,
        "created_at": batch.created_at,
        "committed_at": batch.committed_at,
        "summary": batch.result_json.get("summary") if isinstance(batch.result_json, dict) else {},
        "rows": rows,
    }
