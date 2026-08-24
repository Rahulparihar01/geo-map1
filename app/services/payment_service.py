import json
import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.models.payment_transaction import PaymentTransaction, PaymentStatus
from app.models.user import User
from app.repositories.payment_repository import PaymentRepository
from app.repositories.user_repository import UserRepository
from app.services.email_service import send_payment_confirmation_email

logger = logging.getLogger(__name__)

CREDIT_PACKAGES = [
    {"inr": 150, "credits": 50, "label": "Starter", "key": "starter"},
    {"inr": 300, "credits": 110, "label": "Popular", "key": "popular"},
    {"inr": 500, "credits": 190, "label": "Pro", "key": "pro"},
    {"inr": 1000, "credits": 400, "label": "Ultimate", "key": "ultimate"},
]


def calculate_credits_for_amount(amount_inr: int) -> int:
    if amount_inr < 3:
        raise ValueError("Invalid payment amount")
    return amount_inr // 3

def resolve_credits(amount_inr: int, package_type: str = "custom") -> int:
    if package_type == "custom":
        return calculate_credits_for_amount(amount_inr)

    for pkg in CREDIT_PACKAGES:
        if pkg["key"] == package_type.lower():
            if pkg["inr"] != amount_inr:
                raise ValueError("Invalid payment amount")
            return pkg["credits"]

    logger.warning(
        "Unknown package_type '%s' — falling back to custom credit calculation",
        package_type,
    )
    return calculate_credits_for_amount(amount_inr)


class PaymentService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.payment_repo = PaymentRepository(db)
        self.user_repo = UserRepository(db)

    def create_razorpay_order(
        self,
        *,
        user_id: int,
        amount_inr: int,
        credits: int,
        razorpay_order_id: str,
    ) -> PaymentTransaction:
        return self.payment_repo.create_razorpay_transaction(
            user_id=user_id,
            amount_inr=amount_inr,
            credits_purchased=credits,
            razorpay_order_id=razorpay_order_id,
        )

    def credit_transaction(self, txn: PaymentTransaction) -> Optional[User]:
        txn = (
            self.db.query(PaymentTransaction)
            .filter(PaymentTransaction.id == txn.id)
            .with_for_update()
            .first()
        )
        if txn is None:
            logger.error("Transaction not found for crediting")
            return None

        if txn.status == PaymentStatus.SUCCEEDED:
            logger.info("Transaction %s already succeeded — skipping duplicate credit", txn.id)
            user = (
                self.db.query(User)
                .filter(User.id == txn.user_id)
                .first()
            )
            return user

        txn.status = PaymentStatus.SUCCEEDED
        txn.completed_at = datetime.now(timezone.utc)
        self.db.flush()

        user = (
            self.db.query(User)
            .filter(User.id == txn.user_id)
            .with_for_update()
            .first()
        )
        if user is None:
            self.db.rollback()
            logger.error("User %s not found for transaction %s — rolled back, remains PENDING", txn.user_id, txn.id)
            return None

        user.credits = (user.credits or 0) + txn.credits_purchased
        self.db.flush()

        logger.info(
            "Credited %s credits to user %s (new balance: %s) for transaction %s",
            txn.credits_purchased,
            user.id,
            user.credits,
            txn.id,
        )
        return user

    def verify_and_credit(
        self,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str,
    ) -> Optional[Tuple[User, PaymentTransaction, bool]]:
        txn = self.payment_repo.get_by_razorpay_order_id_for_update(razorpay_order_id)
        if txn is None:
            logger.error("No transaction found for order: %s", razorpay_order_id)
            return None

        was_pending = txn.status == PaymentStatus.PENDING
        self.payment_repo.set_razorpay_payment_details(
            txn,
            payment_id=razorpay_payment_id,
            signature=razorpay_signature)

        user = self.credit_transaction(txn)
        if user is None:
            return None
        return user, txn, was_pending

    def send_confirmation_email_if_needed(self, order_id: str) -> None:
        txn = self.payment_repo.get_by_razorpay_order_id(order_id)
        if txn is None or txn.status != PaymentStatus.SUCCEEDED:
            return

        try:
            metadata = json.loads(txn.metadata_json or "{}")
        except json.JSONDecodeError:
            metadata = {}

        if metadata.get("email_sent"):
            return

        user = self.user_repo.get_by_id(txn.user_id)
        if user is None:
            return

        send_payment_confirmation_email(
            to_email=user.email,
            full_name=user.full_name,
            credits_purchased=txn.credits_purchased,
            new_balance=user.credits or 0,
            amount_inr=txn.amount_inr,
        )

        metadata["email_sent"] = True
        metadata["email_sent_at"] = datetime.now(timezone.utc).isoformat()
        self.payment_repo.update_metadata(txn, metadata)
