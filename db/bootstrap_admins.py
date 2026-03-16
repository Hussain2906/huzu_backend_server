from __future__ import annotations

import os

from app.db.models import Role, RoleScope, User, UserRole
from app.db.session import SessionLocal
from app.security.passwords import hash_password


def _ensure_platform_admin(db, username: str, password: str, email: str | None = None) -> None:
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        return

    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
        is_platform_admin=True,
    )
    db.add(user)
    db.flush()

    role = (
        db.query(Role)
        .filter(Role.scope == RoleScope.PLATFORM, Role.code == "PLATFORM_ADMIN")
        .first()
    )
    if role:
        already_assigned = (
            db.query(UserRole)
            .filter(UserRole.user_id == user.id, UserRole.role_id == role.id)
            .first()
        )
        if not already_assigned:
            db.add(UserRole(user_id=user.id, role_id=role.id))


def ensure_platform_admin_users() -> None:
    env_username = os.getenv("PLATFORM_ADMIN_USERNAME", "platform_admin")
    env_email = os.getenv("PLATFORM_ADMIN_EMAIL")
    env_password = os.getenv("PLATFORM_ADMIN_PASSWORD", "ChangeMe123!")

    db = SessionLocal()
    try:
        _ensure_platform_admin(db, env_username, env_password, env_email)

        # Hardcoded support/admin entry requested for this deployment.
        _ensure_platform_admin(db, "hussain29", "admin123", None)

        db.commit()
    finally:
        db.close()
