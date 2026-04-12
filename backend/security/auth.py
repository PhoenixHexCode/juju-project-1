"""JWT auth + bcrypt password hashing for the companion's API."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from ..config import get_settings

ALGO = "HS256"
_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd.verify(plain, hashed)


def create_token(subject: str, *, expires_minutes: int = 60 * 24 * 7) -> str:
    payload = {
        "sub": subject,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=expires_minutes),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, get_settings().app_secret, algorithm=ALGO)


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        return jwt.decode(token, get_settings().app_secret, algorithms=[ALGO])
    except JWTError:
        return None
