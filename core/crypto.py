import hashlib
from app.core.config import settings

def hash_activation_key(key: str) -> str:
    raw = (settings.key_pepper + key.strip()).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()