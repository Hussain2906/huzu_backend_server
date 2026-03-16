from datetime import datetime
import hashlib

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.models import AuthSession, Role, User, UserRole, UserStatus
from app.security.passwords import verify_password
from app.security.jwt import create_access_token, create_refresh_token

router = APIRouter(prefix="/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username_or_email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    company_id: str | None = None
    is_platform_admin: bool = False
    role_code: str | None = None
    role_label: str | None = None
    allowed_modules: list[str] | None = None
    full_name: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    username_or_email: str


class ForgotPasswordResponse(BaseModel):
    message: str


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    q = payload.username_or_email.strip().lower()
    user = (
        db.query(User)
        .filter((User.username == q) | (User.email == q))
        .first()
    )
    if not user or user.status != UserStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    role_ids = [ur.role_id for ur in db.query(UserRole).filter(UserRole.user_id == user.id).all()]
    role = (
        db.query(Role)
        .join(UserRole, UserRole.role_id == Role.id)
        .filter(UserRole.user_id == user.id)
        .first()
    )
    access_token = create_access_token(user.id, user.company_id, role_ids)
    refresh_token, expires_at = create_refresh_token(user.id)

    token_hash = hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()
    db.add(AuthSession(user_id=user.id, refresh_token_hash=token_hash, expires_at=expires_at))
    db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        company_id=user.company_id,
        is_platform_admin=user.is_platform_admin,
        role_code=role.code if role else None,
        role_label=user.role_label,
        allowed_modules=user.allowed_modules,
        full_name=user.full_name,
    )


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)) -> ForgotPasswordResponse:
    q = payload.username_or_email.strip().lower()
    if q:
        (
            db.query(User)
            .filter((User.username == q) | (User.email == q))
            .first()
        )

    return ForgotPasswordResponse(
        message="Password reset requests are handled by an administrator. Contact admin to reset your password."
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    token_hash = hashlib.sha256(payload.refresh_token.encode("utf-8")).hexdigest()
    session = (
        db.query(AuthSession)
        .filter(AuthSession.refresh_token_hash == token_hash)
        .first()
    )
    if not session or session.revoked_at is not None or session.expires_at < datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user = db.get(User, session.user_id)
    if not user or user.status != UserStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user")

    role_ids = [ur.role_id for ur in db.query(UserRole).filter(UserRole.user_id == user.id).all()]
    role = (
        db.query(Role)
        .join(UserRole, UserRole.role_id == Role.id)
        .filter(UserRole.user_id == user.id)
        .first()
    )
    access_token = create_access_token(user.id, user.company_id, role_ids)
    refresh_token, expires_at = create_refresh_token(user.id)

    session.revoked_at = datetime.utcnow()
    new_hash = hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()
    db.add(AuthSession(user_id=user.id, refresh_token_hash=new_hash, expires_at=expires_at))
    db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        company_id=user.company_id,
        is_platform_admin=user.is_platform_admin,
        role_code=role.code if role else None,
        role_label=user.role_label,
        allowed_modules=user.allowed_modules,
        full_name=user.full_name,
    )
