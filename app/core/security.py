import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import settings

logger = logging.getLogger(__name__)

_ACCESS_AUD = "geo-map-access"
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def validate_token_sub(sub: Optional[str]) -> Optional[int]:
    if not sub:
        return None
    try:
        return int(sub)
    except ValueError:
        return None


def strip_bearer_prefix(raw_token: str) -> str:
    prefix = "Bearer "
    if raw_token.startswith(prefix):
        return raw_token[len(prefix):].strip()
    return raw_token.strip()


def _validate_sub(data: dict) -> dict:
    sub = data.get("sub")
    if sub is None:
        raise ValueError("Token payload must include 'sub' claim")
    try:
        int(sub)
    except (ValueError, TypeError):
        raise ValueError(f"'sub' claim must be a string-encoded integer, got: {sub}")
    return data


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    to_encode = _validate_sub(data.copy())
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update(
        {
            "type": "access",
            "exp": expire,
            "iat": now,
            "jti": secrets.token_hex(16),
            "aud": _ACCESS_AUD,
        }
    )
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            audience=_ACCESS_AUD,
        )

        if payload.get("type") != "access":
            return None
        return payload
    except JWTError:
        return None


def is_token_revoked_by_password_change(user, payload: dict) -> bool:
    if user.password_changed_at is None:
        return False
    token_iat = payload.get("iat")
    if token_iat is None:
        return False
    return token_iat < user.password_changed_at.timestamp()


def password_change_rejection_message(user) -> str:
    time_since_creation = (
        datetime.now(timezone.utc) - user.created_at
    ).total_seconds()
    time_diff = abs(
        user.password_changed_at.timestamp() - user.created_at.timestamp()
    )
    if time_since_creation < 300 and time_diff < 2:
        return "Registration successful! Please log in with your email and password."
    return "Your password was changed. Please log in with your new password."


def load_user_from_token(token: str, db: Session):
    from app.repositories.user_repository import UserRepository
    
    payload = decode_access_token(token)
    if payload is None:
        return None, None

    user_id = validate_token_sub(payload.get("sub"))
    if user_id is None:
        return None, payload

    user = UserRepository(db).get_active_by_id(user_id)
    if user is None:
        return None, payload

    return user, payload


