from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_db, require_platform_admin
from app.db.models import Company, CompanyStatus, Role, RoleScope, User, UserRole
from app.security.passwords import hash_password, verify_password

router = APIRouter(prefix="/v1/platform", tags=["platform"])


class CompanyCreate(BaseModel):
    name: str
    gstin: str | None = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    seat_limit: int = Field(default=5, ge=1)
    plan_days: int = Field(default=30, ge=1)

    super_admin_username: str
    super_admin_email: str | None = None
    super_admin_password: str


class CompanyUpdate(BaseModel):
    name: str | None = None
    gstin: str | None = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    seat_limit: int | None = None
    plan_expiry_at: datetime | None = None
    status: CompanyStatus | None = None


class CompanyOut(BaseModel):
    id: str
    name: str
    status: CompanyStatus
    seat_limit: int
    plan_expiry_at: datetime | None
    gstin: str | None = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None


class PlatformAdminOut(BaseModel):
    id: str
    username: str
    email: str | None = None


class PlatformAdminUpdate(BaseModel):
    username: str | None = None
    email: str | None = None
    current_password: str | None = None
    new_password: str | None = None


@router.post("/companies", response_model=CompanyOut)
def create_company(
    payload: CompanyCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
) -> CompanyOut:
    expiry = datetime.utcnow() + timedelta(days=payload.plan_days)
    username = payload.super_admin_username.strip().lower()
    email = payload.super_admin_email.strip().lower() if payload.super_admin_email else None

    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already in use")

    company = Company(
        name=payload.name.strip(),
        gstin=payload.gstin,
        phone=payload.phone,
        address=payload.address,
        city=payload.city,
        state=payload.state,
        pincode=payload.pincode,
        seat_limit=payload.seat_limit,
        plan_expiry_at=expiry,
    )
    db.add(company)
    db.flush()

    super_admin = User(
        company_id=company.id,
        username=username,
        email=email,
        password_hash=hash_password(payload.super_admin_password),
        is_platform_admin=False,
    )
    db.add(super_admin)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        detail = str(exc.orig).lower()
        if "users.email" in detail:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already in use")
        if "users.username" in detail:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already in use")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Duplicate record")

    role = (
        db.query(Role)
        .filter(Role.scope == RoleScope.COMPANY, Role.code == "SUPER_ADMIN")
        .first()
    )
    if not role:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Role SUPER_ADMIN missing")

    db.add(UserRole(user_id=super_admin.id, role_id=role.id))
    db.commit()

    return CompanyOut(
        id=company.id,
        name=company.name,
        status=company.status,
        seat_limit=company.seat_limit,
        plan_expiry_at=company.plan_expiry_at,
        gstin=company.gstin,
        phone=company.phone,
        address=company.address,
        city=company.city,
        state=company.state,
        pincode=company.pincode,
    )


@router.get("/companies", response_model=list[CompanyOut])
def list_companies(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
) -> list[CompanyOut]:
    companies = db.query(Company).order_by(Company.created_at.desc()).all()
    return [
        CompanyOut(
            id=c.id,
            name=c.name,
            status=c.status,
            seat_limit=c.seat_limit,
            plan_expiry_at=c.plan_expiry_at,
            gstin=c.gstin,
            phone=c.phone,
            address=c.address,
            city=c.city,
            state=c.state,
            pincode=c.pincode,
        )
        for c in companies
    ]


@router.patch("/companies/{company_id}", response_model=CompanyOut)
def update_company(
    company_id: str,
    payload: CompanyUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
) -> CompanyOut:
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(company, field, value)

    company.updated_at = datetime.utcnow()
    db.commit()

    return CompanyOut(
        id=company.id,
        name=company.name,
        status=company.status,
        seat_limit=company.seat_limit,
        plan_expiry_at=company.plan_expiry_at,
        gstin=company.gstin,
        phone=company.phone,
        address=company.address,
        city=company.city,
        state=company.state,
        pincode=company.pincode,
    )


@router.get("/admin/profile", response_model=PlatformAdminOut)
def get_platform_admin_profile(
    _admin: User = Depends(require_platform_admin),
) -> PlatformAdminOut:
    return PlatformAdminOut(id=_admin.id, username=_admin.username, email=_admin.email)


@router.patch("/admin/profile", response_model=PlatformAdminOut)
def update_platform_admin_profile(
    payload: PlatformAdminUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
) -> PlatformAdminOut:
    if any([payload.username, payload.email, payload.new_password]):
        if not payload.current_password:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password required")
        if not verify_password(payload.current_password, _admin.password_hash):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid current password")

    if payload.username:
        next_username = payload.username.strip().lower()
        if next_username != _admin.username:
            exists = db.query(User).filter(User.username == next_username).first()
            if exists:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already in use")
        _admin.username = next_username

    if payload.email is not None:
        next_email = payload.email.strip().lower() if payload.email else None
        _admin.email = next_email

    if payload.new_password:
        _admin.password_hash = hash_password(payload.new_password)

    db.commit()
    return PlatformAdminOut(id=_admin.id, username=_admin.username, email=_admin.email)
