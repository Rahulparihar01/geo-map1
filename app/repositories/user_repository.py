import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.user import User

logger = logging.getLogger(__name__)


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _normalize_email(email: str) -> str:
        return email.strip().lower()

    def get_by_id(self, user_id: int) -> Optional[User]:
        return self.db.query(User).filter(User.id == user_id).first()

    def get_by_email(self, email: str) -> Optional[User]:
        return self.db.query(User).filter(User.email == self._normalize_email(email)).first()

    def get_by_email_for_update(self, email: str) -> Optional[User]:
        return (
            self.db.query(User)
            .filter(User.email == self._normalize_email(email))
            .with_for_update()
            .first()
        )

    def get_active_by_id(self, user_id: int) -> Optional[User]:
        return (
            self.db.query(User)
            .filter(User.id == user_id, User.is_active == True)
            .first()
        )

    def create_pending_user(
        self,
        *,
        full_name: str,
        email: str,
        hashed_password: str,
    ) -> User:
        user = User(
            full_name=full_name,
            email=email,
            hashed_password=hashed_password,
            auth_provider="local",
            email_verified=False,
            is_active=False,
            credits=0,
        )
        self.db.add(user)
        self.db.flush()
        logger.info("Created pending user for OTP flow: email=%s id=%s", email, user.id)
        return user

    def activate_pending_user(self, user: User) -> User:
        if user.email_verified:
            logger.warning(
                "User already activated (idempotent): id=%s email=%s",
                user.id,
                user.email,
            )
            return user

        user.email_verified = True
        user.is_active = True
        user.credits = 50
        self.db.flush()
        logger.info("Activated user after OTP: id=%s email=%s", user.id, user.email)
        return user

    def delete_pending_user(self, user: User) -> None:
        self.db.delete(user)
        self.db.flush()
        logger.info("Deleted pending user: id=%s email=%s", user.id, user.email)

    def update_password(self, user: User, new_hashed_password: str) -> User:
        user.hashed_password = new_hashed_password
        user.password_changed_at = datetime.now(timezone.utc)
        self.db.flush()
        logger.info("Password updated for user id=%s", user.id)
        return user
