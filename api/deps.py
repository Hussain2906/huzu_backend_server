from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.ensure_sqlite_schema import ensure_sqlite_schema
from app.db.models import Role, RoleScope, User, UserRole, UserStatus
from app.security.jwt import decode_token


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login")


_sqlite_schema_ready = False


def get_db():
    global _sqlite_schema_ready
    if not _sqlite_schema_ready:
        try:
            ensure_sqlite_schema()
        except Exception:
            pass
        _sqlite_schema_ready = True
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = db.get(User, user_id)
    if not user or user.status != UserStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")

    return user


def require_platform_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_platform_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform admin only")
    return user


def require_company_user(user: User = Depends(get_current_user)) -> User:
    if not user.company_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Company user only")
    return user


def is_company_super_admin(db: Session, user: User) -> bool:
    return (
        db.query(Role)
        .join(UserRole, UserRole.role_id == Role.id)
        .filter(UserRole.user_id == user.id, Role.scope == RoleScope.COMPANY, Role.code == "SUPER_ADMIN")
        .first()
        is not None
    )


def require_company_super_admin(
    user: User = Depends(require_company_user),
    db: Session = Depends(get_db),
) -> User:
    if not is_company_super_admin(db, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admin only")
    return user


def _has_module(user: User, module: str) -> bool:
    if user.is_platform_admin:
        return True
    if user.allowed_modules is None:
        return True
    allowed = user.allowed_modules or []
    if "all" in allowed:
        return True
    return any(mod == module or mod.startswith(f"{module}.") for mod in allowed)


def _has_any_module(user: User, modules: list[str]) -> bool:
    return any(_has_module(user, module) for module in modules)


def require_sales_access(user: User = Depends(require_company_user)) -> User:
    if not _has_module(user, "sales"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sales access required")
    return user


def require_quotation_view_access(user: User = Depends(require_company_user)) -> User:
    if not _has_any_module(user, ["quotations.view", "quotations", "sales.view", "sales"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Quotation view access required")
    return user


def require_quotation_create_access(user: User = Depends(require_company_user)) -> User:
    if not _has_any_module(user, ["quotations.create", "quotations", "sales.create", "sales"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Quotation create access required")
    return user


def require_quotation_edit_access(user: User = Depends(require_company_user)) -> User:
    if not _has_any_module(user, ["quotations.edit", "quotations", "sales.edit", "sales"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Quotation edit access required")
    return user


def require_quotation_delete_access(user: User = Depends(require_company_user)) -> User:
    if not _has_any_module(user, ["quotations.delete", "quotations", "sales.delete", "sales"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Quotation delete access required")
    return user


def require_quotation_convert_access(user: User = Depends(require_company_user)) -> User:
    if not _has_any_module(user, ["quotations.convert", "quotations.edit", "quotations", "sales.create", "sales.edit", "sales"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Quotation convert access required")
    return user


def require_purchase_access(user: User = Depends(require_company_user)) -> User:
    if not _has_module(user, "purchase"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Purchase access required")
    return user
