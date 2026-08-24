import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.payment_transaction import PaymentTransaction, PaymentStatus

logger = logging.getLogger(__name__)


class PaymentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def mark_succeeded(self, txn: PaymentTransaction) -> PaymentTransaction:
        txn.status = PaymentStatus.SUCCEEDED
        txn.completed_at = datetime.now(timezone.utc)
        self.db.flush()
        logger.info("Transaction %s marked as SUCCEEDED", txn.id)
        return txn

    def mark_failed(self, txn: PaymentTransaction) -> PaymentTransaction:
        txn.status = PaymentStatus.FAILED
        self.db.flush()
        logger.info("Transaction %s marked as FAILED", txn.id)
        return txn

    def get_user_history(
        self, user_id: int, limit: int = 20, offset: int = 0, status: Optional[str] = None
    ) -> tuple[List[PaymentTransaction], int]:
        query = self.db.query(PaymentTransaction).filter(
            PaymentTransaction.user_id == user_id
        )
        
        if status:
            query = query.filter(PaymentTransaction.status.like(f"%{status}%"))
        
        total = query.count()
        
        transactions = (
            query.order_by(PaymentTransaction.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )
        return transactions, total

    def create_razorpay_transaction(
        self,
        *,
        user_id: int,
        amount_inr: int,
        credits_purchased: int,
        razorpay_order_id: str,
    ) -> PaymentTransaction:
        txn = PaymentTransaction(
            user_id=user_id,
            amount_inr=amount_inr,
            amount_paise=amount_inr * 100,
            credits_purchased=credits_purchased,
            razorpay_order_id=razorpay_order_id,
            status=PaymentStatus.PENDING,
        )
        self.db.add(txn)
        self.db.flush()
        logger.info(
            "Created Razorpay transaction: id=%s user_id=%s order=%s amount=₹%s credits=%s",
            txn.id,
            user_id,
            razorpay_order_id,
            amount_inr,
            credits_purchased,
        )
        return txn

    def get_by_razorpay_order_id(
        self, razorpay_order_id: str
    ) -> Optional[PaymentTransaction]:
        return (
            self.db.query(PaymentTransaction)
            .filter(PaymentTransaction.razorpay_order_id == razorpay_order_id)
            .first()
        )

    def get_by_razorpay_order_id_for_update(
        self, razorpay_order_id: str
    ) -> Optional[PaymentTransaction]:
        return (
            self.db.query(PaymentTransaction)
            .filter(PaymentTransaction.razorpay_order_id == razorpay_order_id)
            .with_for_update()
            .first()
        )

    def get_by_razorpay_payment_id(
        self, razorpay_payment_id: str
    ) -> Optional[PaymentTransaction]:
        return (
            self.db.query(PaymentTransaction)
            .filter(PaymentTransaction.razorpay_payment_id == razorpay_payment_id)
            .first()
        )

    def get_by_id(self, payment_id: int) -> Optional[PaymentTransaction]:
        return (
            self.db.query(PaymentTransaction)
            .filter(PaymentTransaction.id == payment_id)
            .first()
        )

    def set_razorpay_payment_details(
        self, txn: PaymentTransaction, payment_id: str, signature: str
    ) -> PaymentTransaction:
        txn.razorpay_payment_id = payment_id
        txn.razorpay_signature = signature
        self.db.flush()
        logger.info("Updated transaction %s with payment_id=%s", txn.id, payment_id)
        return txn

    def mark_refunded(self, txn: PaymentTransaction) -> PaymentTransaction:
        txn.status = PaymentStatus.REFUNDED
        self.db.flush()
        logger.info("Transaction %s marked as REFUNDED", txn.id)
        return txn

    def update_metadata(
        self, txn: PaymentTransaction, metadata: dict
    ) -> PaymentTransaction:
        txn.metadata_json = json.dumps(metadata)
        self.db.flush()
        return txn
