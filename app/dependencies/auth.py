from typing import Optional

from fastapi import Depends, Header, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import (
    is_token_revoked_by_password_change,
    load_user_from_token,
    password_change_rejection_message,
)
from app.database.connection import get_db
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)

_credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials. Please log in again.",
    headers={"WWW-Authenticate": "Bearer"},
)


def _load_authenticated_user(
    token: str | None,
    db: Session,
):
    if token is None:
        return None, None

    user, payload = load_user_from_token(token, db)
    return user, payload


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None

    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer":
        return None

    token = token.strip()
    return token or None


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(
        bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user, payload = _load_authenticated_user(credentials.credentials, db)
    if user is None or payload is None:
        raise _credentials_exception

    if is_token_revoked_by_password_change(user, payload):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=password_change_rejection_message(user),
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_optional_user(
    authorization: str | None = Header(
        default=None,
        alias="Authorization",
        include_in_schema=False,
    ),
    db: Session = Depends(get_db),
) -> Optional[User]:
    user, payload = _load_authenticated_user(
        _extract_bearer_token(authorization),
        db,
    )
    if user is None or payload is None:
        return None

    if is_token_revoked_by_password_change(user, payload):
        return None

    return user
