from datetime import datetime, timedelta
import uuid
from typing import Any

from jose import jwt

from app.core.config import settings


def create_access_token(subject: str, company_id: str | None, role_ids: list[str]) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.access_token_minutes)
    payload = {
        "sub": subject,
        "company_id": company_id,
        "role_ids": role_ids,
        "exp": expire,
        "type": "access",
        "iat": datetime.utcnow(),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str) -> tuple[str, datetime]:
    expire = datetime.utcnow() + timedelta(days=settings.refresh_token_days)
    payload = {"sub": subject, "exp": expire, "type": "refresh", "iat": datetime.utcnow(), "jti": str(uuid.uuid4())}
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expire


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
