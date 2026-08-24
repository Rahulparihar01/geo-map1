import sqlalchemy as sa
from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.sql import func

from app.database.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    full_name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    email_verified = Column(
        Boolean,
        default=False,
        server_default=sa.text("false"),
        nullable=False,
        comment="True after OTP verification.",
    )

    is_active = Column(
        Boolean,
        default=True,
        server_default=sa.text("true"),
        nullable=False,
        comment="Set to False to deactivate an account.",
    )

    credits = Column(
        Integer,
        default=50,
        server_default=sa.text("50"),
        nullable=False,
        comment="Credit balance. Deducted by AI chat and Place Q&A.",
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
    )

    hashed_password = Column(
        String(255),
        nullable=False,
        comment="bcrypt hash. Set at account creation.",
    )
    auth_provider = Column(
        String(20),
        default="local",
        server_default="local",
        nullable=False,
        comment="'local' for all users.",
    )
    password_changed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Set each time the password is changed or reset. Used to invalidate tokens issued before this timestamp.",
    )

    def __repr__(self) -> str:
        return (
            f"<User(id={self.id}, email='{self.email}', "
            f"verified={self.email_verified}, "
            f"credits={self.credits}, active={self.is_active})>"
        )
