import time
from threading import Lock
from typing import Any, Optional

_lock = Lock()
_store: dict[str, tuple[float, Any]] = {}


def get(key: str) -> Optional[Any]:
    now = time.time()
    with _lock:
        item = _store.get(key)
        if not item:
            return None
        exp, val = item
        if exp < now:
            _store.pop(key, None)
            return None
        return val


def set(key: str, val: Any, ttl_sec: int) -> None:
    exp = time.time() + ttl_sec
    with _lock:
        _store[key] = (exp, val)


def delete(key: str) -> None:
    with _lock:
        _store.pop(key, None)
