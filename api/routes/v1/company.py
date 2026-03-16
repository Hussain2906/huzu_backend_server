from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_company_super_admin, require_company_user
from app.db.models import Company, CompanyProfile, Role, RoleScope, User, UserRole, UserStatus
from app.security.passwords import hash_password
from app.services.receipt_settings_service import (
    get_receipt_settings,
    reset_receipt_settings,
    sanitize_receipt_settings,
    set_receipt_settings,
)

router = APIRouter(prefix="/v1/company", tags=["company"])

_COMPANY_EXTRA_FIELDS = [
    "legal_name",
    "pan",
    "alternate_phone",
    "email",
    "website",
    "address_line1",
    "address_line2",
    "district",
    "state_code",
    "country",
    "bank_name",
    "bank_branch",
    "account_number",
    "ifsc_code",
    "upi_id",
    "authorised_signatory_name",
    "authorised_signatory_designation",
    "declaration_text",
    "terms_and_conditions",
    "registration_details",
    "logo_path",
    "default_invoice_prefix",
    "default_quotation_prefix",
    "place_of_supply_default",
]
_PRESERVED_EXTRA_KEYS = ["receipt_settings"]


class CompanyProfileOut(BaseModel):
    id: str
    name: str
    gstin: str | None = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    seat_limit: int
    plan_expiry_at: datetime | None = None
    enforce_single_manager: bool
    enforce_single_cashier: bool

    business_name: str | None = None
    gst_number: str | None = None
    profile_phone: str | None = None
    profile_address: str | None = None
    profile_state: str | None = None
    extra_data: dict | None = None


class CompanyProfileUpdate(BaseModel):
    name: str | None = None
    gstin: str | None = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None

    business_name: str | None = None
    gst_number: str | None = None
    profile_phone: str | None = None
    profile_address: str | None = None
    profile_state: str | None = None
    extra_data: dict | None = None


class UserCreate(BaseModel):
    username: str
    email: str | None = None
    password: str
    full_name: str | None = None
    phone: str | None = None
    role_label: str | None = None
    allowed_modules: list[str] | None = None
    role_code: str | None = None


class UserUpdate(BaseModel):
    status: UserStatus | None = None
    role_code: str | None = None
    full_name: str | None = None
    phone: str | None = None
    role_label: str | None = None
    allowed_modules: list[str] | None = None


class UserOut(BaseModel):
    id: str
    username: str
    email: str | None
    status: UserStatus
    role_code: str | None
    role_label: str | None = None
    full_name: str | None = None
    phone: str | None = None
    allowed_modules: list[str] | None = None


class DeleteOut(BaseModel):
    deleted: bool
    message: str


class ReceiptSettingsOut(BaseModel):
    printer: dict
    layout: dict
    visibility: dict


class ReceiptSettingsUpdate(BaseModel):
    printer: dict | None = None
    layout: dict | None = None
    visibility: dict | None = None


def _company_profile_out(company: Company, profile: CompanyProfile | None) -> CompanyProfileOut:
    return CompanyProfileOut(
        id=company.id,
        name=company.name,
        gstin=company.gstin,
        phone=company.phone,
        address=company.address,
        city=company.city,
        state=company.state,
        pincode=company.pincode,
        seat_limit=company.seat_limit,
        plan_expiry_at=company.plan_expiry_at,
        enforce_single_manager=company.enforce_single_manager,
        enforce_single_cashier=company.enforce_single_cashier,
        business_name=profile.business_name if profile else None,
        gst_number=profile.gst_number if profile else None,
        profile_phone=profile.phone if profile else None,
        profile_address=profile.address if profile else None,
        profile_state=profile.state if profile else None,
        extra_data=(profile.extra_json or {}) if profile else {},
    )


@router.get("/profile", response_model=CompanyProfileOut)
def get_profile(
    db: Session = Depends(get_db),
    user: User = Depends(require_company_user),
) -> CompanyProfileOut:
    company = db.get(Company, user.company_id)
    profile = db.query(CompanyProfile).filter(CompanyProfile.company_id == company.id).first()
    return _company_profile_out(company, profile)


@router.patch("/profile", response_model=CompanyProfileOut)
def update_profile(
    payload: CompanyProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_company_user),
) -> CompanyProfileOut:
    company = db.get(Company, user.company_id)
    for field in ["name", "gstin", "phone", "address", "city", "state", "pincode"]:
        value = getattr(payload, field)
        if value is not None:
            setattr(company, field, value)

    profile = db.query(CompanyProfile).filter(CompanyProfile.company_id == company.id).first()
    if not profile:
        profile = CompanyProfile(company_id=company.id, business_name=company.name)
        db.add(profile)

    if payload.business_name is not None:
        profile.business_name = payload.business_name
    if payload.gst_number is not None:
        profile.gst_number = payload.gst_number
    if payload.profile_phone is not None:
        profile.phone = payload.profile_phone
    if payload.profile_address is not None:
        profile.address = payload.profile_address
    if payload.profile_state is not None:
        profile.state = payload.profile_state
    if payload.extra_data is not None:
        extras = {key: value for key, value in (payload.extra_data or {}).items() if key in _COMPANY_EXTRA_FIELDS}
        existing = dict(profile.extra_json or {})
        for key in _PRESERVED_EXTRA_KEYS:
            if key in existing:
                extras[key] = existing[key]
        profile.extra_json = extras

    company.updated_at = datetime.utcnow()
    profile.updated_at = datetime.utcnow()
    db.commit()

    return get_profile(db=db, user=user)


@router.get("/receipt-settings", response_model=ReceiptSettingsOut)
def get_company_receipt_settings(
    db: Session = Depends(get_db),
    user: User = Depends(require_company_user),
) -> ReceiptSettingsOut:
    profile = db.query(CompanyProfile).filter(CompanyProfile.company_id == user.company_id).first()
    settings = get_receipt_settings(profile)
    return ReceiptSettingsOut(**settings)


@router.patch("/receipt-settings", response_model=ReceiptSettingsOut)
def update_company_receipt_settings(
    payload: ReceiptSettingsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_company_super_admin),
) -> ReceiptSettingsOut:
    profile = db.query(CompanyProfile).filter(CompanyProfile.company_id == user.company_id).first()
    company = db.get(Company, user.company_id)
    if not profile:
        profile = CompanyProfile(company_id=company.id, business_name=company.name, extra_json={})
        db.add(profile)
    incoming = {
        key: value
        for key, value in payload.model_dump(exclude_none=True).items()
        if isinstance(value, dict)
    }
    settings = set_receipt_settings(profile, incoming)
    profile.updated_at = datetime.utcnow()
    db.commit()
    return ReceiptSettingsOut(**settings)


@router.post("/receipt-settings/reset", response_model=ReceiptSettingsOut)
def reset_company_receipt_settings(
    db: Session = Depends(get_db),
    user: User = Depends(require_company_super_admin),
) -> ReceiptSettingsOut:
    profile = db.query(CompanyProfile).filter(CompanyProfile.company_id == user.company_id).first()
    company = db.get(Company, user.company_id)
    if not profile:
        profile = CompanyProfile(company_id=company.id, business_name=company.name, extra_json={})
        db.add(profile)
    settings = reset_receipt_settings(profile)
    profile.updated_at = datetime.utcnow()
    db.commit()
    return ReceiptSettingsOut(**sanitize_receipt_settings(settings))


@router.get("/users", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    user: User = Depends(require_company_user),
) -> list[UserOut]:
    users = db.query(User).filter(User.company_id == user.company_id).all()
    role_map = {
        ur.user_id: role.code
        for ur, role in db.query(UserRole, Role)
        .join(Role, Role.id == UserRole.role_id)
        .filter(Role.scope == RoleScope.COMPANY)
        .all()
    }

    return [
        UserOut(
            id=u.id,
            username=u.username,
            email=u.email,
            status=u.status,
            role_code=role_map.get(u.id),
            role_label=u.role_label,
            full_name=u.full_name,
            phone=u.phone,
            allowed_modules=u.allowed_modules,
        )
        for u in users
    ]


@router.post("/users", response_model=UserOut)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_company_super_admin),
) -> UserOut:
    allowed = payload.allowed_modules or []
    if len(allowed) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select at least one permission")
    company = db.get(Company, user.company_id)
    active_count = db.query(User).filter(User.company_id == company.id, User.status == UserStatus.ACTIVE).count()
    if active_count >= company.seat_limit:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Seat limit reached")

    role_code = (payload.role_code or "STAFF").upper()
    role = (
        db.query(Role)
        .filter(Role.scope == RoleScope.COMPANY, Role.code == role_code)
        .first()
    )
    if not role:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role")

    if company.enforce_single_manager and role.code == "MANAGER":
        existing = (
            db.query(UserRole)
            .join(User, User.id == UserRole.user_id)
            .join(Role, Role.id == UserRole.role_id)
            .filter(User.company_id == company.id, Role.code == "MANAGER")
            .count()
        )
        if existing >= 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only one manager allowed")

    if company.enforce_single_cashier and role.code == "CASHIER":
        existing = (
            db.query(UserRole)
            .join(User, User.id == UserRole.user_id)
            .join(Role, Role.id == UserRole.role_id)
            .filter(User.company_id == company.id, Role.code == "CASHIER")
            .count()
        )
        if existing >= 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only one cashier allowed")

    new_user = User(
        company_id=company.id,
        username=payload.username.strip().lower(),
        email=payload.email.strip().lower() if payload.email else None,
        password_hash=hash_password(payload.password),
        is_platform_admin=False,
        full_name=payload.full_name.strip() if payload.full_name else None,
        phone=payload.phone.strip() if payload.phone else None,
        role_label=payload.role_label.strip() if payload.role_label else None,
        allowed_modules=allowed,
    )
    db.add(new_user)
    db.flush()
    db.add(UserRole(user_id=new_user.id, role_id=role.id))
    db.commit()

    return UserOut(
        id=new_user.id,
        username=new_user.username,
        email=new_user.email,
        status=new_user.status,
        role_code=role.code,
        role_label=new_user.role_label,
        full_name=new_user.full_name,
        phone=new_user.phone,
        allowed_modules=new_user.allowed_modules,
    )


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: str,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(require_company_super_admin),
) -> UserOut:
    target = db.get(User, user_id)
    if not target or target.company_id != _user.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if payload.status is not None:
        target.status = payload.status

    role_code = None
    if payload.role_code:
        role = (
            db.query(Role)
            .filter(Role.scope == RoleScope.COMPANY, Role.code == payload.role_code.upper())
            .first()
        )
        if not role:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role")

        db.query(UserRole).filter(UserRole.user_id == target.id).delete()
        db.add(UserRole(user_id=target.id, role_id=role.id))
        role_code = role.code
    if payload.full_name is not None:
        target.full_name = payload.full_name.strip() if payload.full_name else None
    if payload.phone is not None:
        target.phone = payload.phone.strip() if payload.phone else None
    if payload.role_label is not None:
        target.role_label = payload.role_label.strip() if payload.role_label else None
    if payload.allowed_modules is not None:
        allowed = payload.allowed_modules or []
        if len(allowed) == 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select at least one permission")
        target.allowed_modules = allowed

    db.commit()

    if not role_code:
        role = (
            db.query(Role)
            .join(UserRole, UserRole.role_id == Role.id)
            .filter(UserRole.user_id == target.id)
            .first()
        )
        role_code = role.code if role else None

    return UserOut(
        id=target.id,
        username=target.username,
        email=target.email,
        status=target.status,
        role_code=role_code,
        role_label=target.role_label,
        full_name=target.full_name,
        phone=target.phone,
        allowed_modules=target.allowed_modules,
    )


@router.delete("/users/{user_id}", response_model=DeleteOut)
def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(require_company_super_admin),
) -> DeleteOut:
    target = db.get(User, user_id)
    if not target or target.company_id != _user.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if target.id == _user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot delete yourself")
    db.query(UserRole).filter(UserRole.user_id == target.id).delete()
    db.delete(target)
    db.commit()
    return DeleteOut(deleted=True, message="User deleted")
