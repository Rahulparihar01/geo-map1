import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.rate_limiter import shared_limiter as limiter
from app.database.connection import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.payments import (
    CreateOrderRequest,
    CreateOrderResponse,
    PackageInfo,
    PackagesResponse,
    PaymentDetailResponse,
    PaymentHistoryResponse,
    VerifyPaymentRequest,
    VerifyPaymentResponse,
    payment_detail_response,
    payment_history_item,
)
from app.services.payment_service import CREDIT_PACKAGES, PaymentService, resolve_credits
from app.services.razorpay_service import RazorpayService
from app.utils.error_messages import (
    PAYMENT_INVALID_FORMAT,
    PAYMENT_SERVICE_UNAVAILABLE,
    PAYMENT_VERIFICATION_FAILED,
    TRANSACTION_NOT_FOUND,
    PAYMENT_NOT_FOUND,
    PAYMENT_INVALID_AMOUNT,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.get("/packages", response_model=PackagesResponse)
@limiter.limit("30/minute")
async def get_packages(request: Request):
    return PackagesResponse(
        packages=[
            PackageInfo(inr=pkg["inr"], credits=pkg["credits"], label=pkg["label"])
            for pkg in CREDIT_PACKAGES
        ],
    )


@router.post("/orders", response_model=CreateOrderResponse)
@limiter.limit("10/minute")
async def create_order(
    request: Request,
    payload: CreateOrderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        credits = resolve_credits(payload.amount_inr, payload.package)
    except ValueError as exc:
        logger.error("Credit resolution failed for amount=%s package=%s: %s", 
                    payload.amount_inr, payload.package, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=PAYMENT_INVALID_AMOUNT,
        ) from exc

    try:
        razorpay_order = await RazorpayService.create_order(
            amount_paise=payload.amount_inr * 100,
            receipt=f"user_{current_user.id}_credits_{credits}",
            notes={
                "user_id": str(current_user.id),
                "credits": str(credits),
                "amount_inr": str(payload.amount_inr),
            },
        )
    except Exception as exc:
        logger.error("Failed to create Razorpay order for user=%s: %s", current_user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=PAYMENT_SERVICE_UNAVAILABLE,
        ) from exc

    svc = PaymentService(db)
    svc.create_razorpay_order(
        user_id=current_user.id,
        amount_inr=payload.amount_inr,
        credits=credits,
        razorpay_order_id=razorpay_order["id"],
    )
    db.commit()

    logger.info(
        "Razorpay order created: user_id=%s order=%s amount=₹%s credits=%s",
        current_user.id,
        razorpay_order["id"],
        payload.amount_inr,
        credits,
    )

    return CreateOrderResponse(
        order_id=razorpay_order["id"],
        key_id=RazorpayService.get_key_id(),
        amount=razorpay_order["amount"],
        currency=razorpay_order["currency"],
        credits_to_receive=credits,
        amount_inr=payload.amount_inr,
    )


@router.post("/verify", response_model=VerifyPaymentResponse)
@limiter.limit("10/minute")
async def verify_payment(
    request: Request,
    payload: VerifyPaymentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    logger.info(
        "Payment verification attempt: user=%s order=%s payment=%s sig_len=%s",
        current_user.id,
        payload.razorpay_order_id,
        payload.razorpay_payment_id,
        len(payload.razorpay_signature),
    )
    
    try:
        await RazorpayService.verify_payment_signature(
            order_id=payload.razorpay_order_id,
            payment_id=payload.razorpay_payment_id,
            signature=payload.razorpay_signature,
        )
    except Exception as exc:
        logger.error(
            "Signature verification failed for user=%s order=%s payment=%s: %s (type=%s)",
            current_user.id,
            payload.razorpay_order_id,
            payload.razorpay_payment_id,
            exc,
            type(exc).__name__,
        )
        
        # Return user-friendly message without exposing backend error details
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=PAYMENT_VERIFICATION_FAILED,
        ) from exc

    svc = PaymentService(db)
    result = svc.verify_and_credit(
        razorpay_order_id=payload.razorpay_order_id,
        razorpay_payment_id=payload.razorpay_payment_id,
        razorpay_signature=payload.razorpay_signature,
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=TRANSACTION_NOT_FOUND,
        )

    user, txn, was_pending = result

    if user.id != current_user.id:
        logger.warning("Ownership violation: user=%s attempted to verify order owned by user=%s", current_user.id, user.id,)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=TRANSACTION_NOT_FOUND,)

    db.commit()

    if was_pending:
        svc.send_confirmation_email_if_needed(payload.razorpay_order_id)
        db.commit()

    logger.info(
        "Payment verified: order=%s user=%s credits=%s balance=%s",
        payload.razorpay_order_id,
        current_user.id,
        txn.credits_purchased,
        user.credits,
    )

    return VerifyPaymentResponse(
        credits_added=txn.credits_purchased,
        new_balance=user.credits,
        status="succeeded",
    )


@router.get("/{payment_id}", response_model=PaymentDetailResponse)
@limiter.limit("30/minute")
async def get_payment_detail(
    request: Request,
    payment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = PaymentService(db)
    if payment_id.startswith("pay_"):
        txn = svc.payment_repo.get_by_razorpay_payment_id(payment_id)
    elif payment_id.isdigit():
        txn = svc.payment_repo.get_by_id(int(payment_id))
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=PAYMENT_INVALID_FORMAT,
        )
    if not txn or txn.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=PAYMENT_NOT_FOUND,)

    logger.info("Payment detail requested: payment_id=%s user_id=%s", payment_id, current_user.id,)
    return payment_detail_response(txn)


@router.get("", response_model=PaymentHistoryResponse)
@limiter.limit("20/minute")
async def payment_history(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str = Query(None, description="Filter by status: pending, succeeded, failed"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = PaymentService(db)
    offset = (page - 1) * page_size
    transactions, total = svc.payment_repo.get_user_history(
        current_user.id, 
        limit=page_size, 
        offset=offset,
        status=status
    )
    has_next = (offset + page_size) < total
    return PaymentHistoryResponse(
        transactions=[payment_history_item(t) for t in transactions],
        total_count=total,
        page=page,
        page_size=page_size,
        has_next=has_next
    )