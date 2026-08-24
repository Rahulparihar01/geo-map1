import enum
import sqlalchemy as sa
from sqlalchemy import Column, DateTime, Integer, String, Text, Enum as SAEnum
from sqlalchemy.sql import func

from app.database.base import Base
from app.models.user import User


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        sa.ForeignKey(User.id, ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Razorpay payment fields
    razorpay_order_id = Column(String(255), unique=True, nullable=True, index=True)
    razorpay_payment_id = Column(String(255), nullable=True, index=True)
    razorpay_signature = Column(String(255), nullable=True)

    amount_inr = Column(Integer, nullable=False, comment="Amount in INR (e.g. 150)")
    amount_paise = Column(
        Integer,
        nullable=False,
        comment="Amount in paise (e.g. 15000 for ₹150)",
    )
    credits_purchased = Column(Integer, nullable=False)

    status = Column(
        SAEnum(PaymentStatus),
        default=PaymentStatus.PENDING,
        nullable=False,
        index=True,
    )

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    metadata_json = Column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<PaymentTransaction(id={self.id}, user_id={self.user_id}, "
            f"amount_inr={self.amount_inr}, credits={self.credits_purchased}, "
            f"status='{self.status}', razorpay_order={self.razorpay_order_id})>"
        )
