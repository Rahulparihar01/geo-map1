import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rate_limiter import shared_limiter as limiter
from app.database.connection import get_db
from app.models.payment_transaction import PaymentStatus
from app.services.payment_service import PaymentService
from app.services.razorpay_service import RazorpayService
from app.utils.error_messages import (
    WEBHOOK_SIGNATURE_MISSING,
    WEBHOOK_SIGNATURE_INVALID,
    WEBHOOK_INVALID_JSON,
    AMOUNT_MISMATCH,
    CREDIT_ALLOCATION_FAILED,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["Razorpay Webhook"])


@router.get("/webhook/health", include_in_schema=False)
async def webhook_health():
    return {
        "status": "ok",
        "webhook_configured": bool(settings.RAZORPAY_WEBHOOK_SECRET),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/webhook", response_model=None)
@limiter.limit("300/minute")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.body()
    signature = request.headers.get("x-razorpay-signature")
    event_id = request.headers.get("x-razorpay-event-id")

    if not signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=WEBHOOK_SIGNATURE_MISSING,
        )

    try:
        await RazorpayService.verify_webhook_signature(
            raw_body, signature, settings.RAZORPAY_WEBHOOK_SECRET
        )
    except Exception as exc:
        logger.warning(
            "Razorpay webhook signature verification failed (event=%s): %s %s",
            event_id,
            type(exc).__name__,
            exc,
        )
        # Do not expose SDK exception names to external callers
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=WEBHOOK_SIGNATURE_INVALID,
        ) from exc

    try:
        event = json.loads(raw_body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("Razorpay webhook body is not valid JSON: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=WEBHOOK_INVALID_JSON,
        ) from exc

    event_type = event.get("event")
    payload = event.get("payload", {})
    logger.info("Razorpay webhook received: event=%s event_id=%s", event_type, event_id)

    if event_type in ("payment.captured", "order.paid"):
        return await _handle_payment_captured(db, payload)

    if event_type == "payment.failed":
        return await _handle_payment_failed(db, payload)

    if event_type == "refund.processed":
        return await _handle_refund(db, payload)

    logger.info("Razorpay webhook event %s not handled — skipping", event_type)
    return {"received": True}


async def _handle_payment_captured(db: Session, payload: dict) -> dict:
    entity = (payload.get("payment") or {}).get("entity") or {}
    order_id = entity.get("order_id")
    payment_id = entity.get("id")
    amount_paise = entity.get("amount")

    if not order_id or not payment_id:
        logger.warning("payment.captured event missing order_id/payment_id — skipping")
        return {"received": True}

    svc = PaymentService(db)
    txn = svc.payment_repo.get_by_razorpay_order_id_for_update(order_id)
    if txn is None:
        logger.warning(
            "payment.captured received for unknown order=%s — acknowledging",
            order_id,
        )
        return {"received": True, "skipped": "unknown_order"}

    if txn.amount_paise != int(amount_paise or 0):
        logger.error(
            "payment.captured amount mismatch for order=%s: expected %s paise, "
            "got %s paise — refusing to credit",
            order_id,
            txn.amount_paise,
            amount_paise,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=AMOUNT_MISMATCH,
        )

    # IDEMPOTENCY CHECK: If already succeeded, skip re-processing
    if txn.status == PaymentStatus.SUCCEEDED:
        logger.info(
            "payment.captured webhook already processed for order=%s — acknowledging duplicate",
            order_id,
        )
        return {"received": True}

    was_pending = txn.status == PaymentStatus.PENDING

    if txn.razorpay_payment_id != payment_id:
        svc.payment_repo.set_razorpay_payment_details(
            txn, payment_id=payment_id, signature=txn.razorpay_signature or ""
        )

    user = svc.credit_transaction(txn)
    if user is None:
        logger.error(
            "credit_transaction() returned None for order=%s on payment.captured",
            order_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=CREDIT_ALLOCATION_FAILED,
        )

    db.commit()

    if was_pending:
        try:
            svc.send_confirmation_email_if_needed(order_id)
            db.commit()
        except Exception as exc:
            logger.error(
                "Failed to send confirmation email for order=%s: %s",
                order_id,
                exc,
            )

    logger.info(
        "Payment captured — order=%s payment=%s user_id=%s credits=%s balance=%s",
        order_id,
        payment_id,
        user.id,
        txn.credits_purchased,
        user.credits,
    )
    return {"received": True}


async def _handle_payment_failed(db: Session, payload: dict) -> dict:
    entity = (payload.get("payment") or {}).get("entity") or {}
    order_id = entity.get("order_id")

    if not order_id:
        logger.warning("payment.failed event missing order_id — skipping")
        return {"received": True}

    svc = PaymentService(db)
    txn = svc.payment_repo.get_by_razorpay_order_id_for_update(order_id)
    if txn is None:
        logger.warning("payment.failed received for unknown order=%s", order_id)
        return {"received": True}

    if txn.status == PaymentStatus.SUCCEEDED:
        logger.warning(
            "Ignoring payment.failed for order=%s — transaction already SUCCEEDED",
            order_id,
        )
        return {"received": True}

    if txn.status == PaymentStatus.FAILED:
        # IDEMPOTENCY CHECK: Already marked as failed
        logger.info(
            "payment.failed webhook already processed for order=%s — acknowledging duplicate",
            order_id,
        )
        return {"received": True}

    # Status is PENDING or other — mark as failed
    svc.payment_repo.mark_failed(txn)
    db.commit()
    logger.info("Payment failed — order=%s user_id=%s", order_id, txn.user_id)
    return {"received": True}


async def _handle_refund(db: Session, payload: dict) -> dict:
    payment_entity = (payload.get("payment") or {}).get("entity") or {}
    refund_entity = (payload.get("refund") or {}).get("entity") or {}

    order_id = payment_entity.get("order_id")
    payment_id = payment_entity.get("id") or refund_entity.get("payment_id")

    svc = PaymentService(db)
    txn = None
    if order_id:
        txn = svc.payment_repo.get_by_razorpay_order_id_for_update(order_id)
    if txn is None and payment_id:
        txn = svc.payment_repo.get_by_razorpay_payment_id(payment_id)
        if txn:
            txn = svc.payment_repo.get_by_razorpay_order_id_for_update(
                txn.razorpay_order_id
            )

    if txn is None:
        logger.warning(
            "Refund event received for unknown payment/order (order=%s payment=%s)",
            order_id,
            payment_id,
        )
        return {"received": True}

    # IDEMPOTENCY CHECK: If already refunded, skip re-processing
    if hasattr(PaymentStatus, 'REFUNDED') and txn.status == PaymentStatus.REFUNDED:
        logger.info(
            "refund.processed webhook already processed for order=%s — acknowledging duplicate",
            txn.razorpay_order_id,
        )
        return {"received": True}

    if txn.status != PaymentStatus.SUCCEEDED:
        logger.warning(
            "Refund event for order=%s ignored — transaction status is %s",
            txn.razorpay_order_id,
            txn.status.value,
        )
        return {"received": True}

    user = svc.user_repo.get_by_id(txn.user_id)
    if user:
        old_balance = user.credits or 0
        new_balance = max(0, old_balance - txn.credits_purchased)
        shortfall = max(0, txn.credits_purchased - old_balance)
        user.credits = new_balance
        if shortfall > 0:
            logger.warning(
                "Refund credit shortfall: user %s owed %s credits but only had %s",
                user.id,
                txn.credits_purchased,
                old_balance,
            )
    else:
        logger.warning(
            "User %s not found for refund — marking transaction as refunded",
            txn.user_id,
        )

    svc.payment_repo.mark_refunded(txn)
    db.commit()
    logger.info(
        "Payment refunded — order=%s user_id=%s", txn.razorpay_order_id, txn.user_id
    )
    return {"received": True}
