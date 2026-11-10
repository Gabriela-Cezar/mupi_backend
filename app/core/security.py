import hashlib
import hmac
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import SECRET_KEY

ALGORITHM = "HS256"
RESET_TOKEN_MINUTES = 10
ACCESS_TOKEN_DAYS = 7
ADMIN_SESSION_HOURS = 12


def _fingerprint(password_hash: str) -> str:
    return hashlib.sha256(password_hash.encode()).hexdigest()[:16]


def fingerprint_matches(payload: dict, current_password_hash: str) -> bool:
    return hmac.compare_digest(
        str(payload.get("fp", "")),
        _fingerprint(current_password_hash)
    )


reset_token_matches = fingerprint_matches


def create_reset_token(email: str, current_password_hash: str) -> str:
    payload = {
        "sub": email,
        "purpose": "password_reset",
        "fp": _fingerprint(current_password_hash),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_reset_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None

    if payload.get("purpose") != "password_reset":
        return None

    return payload


def create_access_token(user_id: int, current_password_hash: str) -> str:
    payload = {
        "sub": str(user_id),
        "purpose": "access",
        "fp": _fingerprint(current_password_hash),
        "exp": datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_DAYS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None

    if payload.get("purpose") != "access":
        return None

    return payload

# ---------- Sessão do painel administrativo ----------

def create_admin_session_token(admin_id: int, current_password_hash: str) -> str:
    payload = {
        "sub": str(admin_id),
        "purpose": "admin_session",
        "fp": _fingerprint(current_password_hash),
        "exp": datetime.now(timezone.utc) + timedelta(hours=ADMIN_SESSION_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_admin_session_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None

    if payload.get("purpose") != "admin_session":
        return None

    return payload


def csrf_token_for(session_token: str) -> str:
    """Token CSRF ligado à sessão: muda a cada login e não precisa ser guardado."""
    return hmac.new(
        SECRET_KEY.encode(),
        f"csrf:{session_token}".encode(),
        hashlib.sha256
    ).hexdigest()
