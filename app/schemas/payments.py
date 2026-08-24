from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.models.payment_transaction import PaymentTransaction


class PackageInfo(BaseModel):
    inr: int
    credits: int
    label: str


class PackagesResponse(BaseModel):
    packages: list[PackageInfo]
    custom_pricing: dict = Field(
        default={
            "min_amount_inr": 3,
            "credits_per_inr": "1 credit per ₹3 (floored)",
        }
    )


class CreateOrderRequest(BaseModel):
    amount_inr: int = Field(..., ge=3)
    package: str = Field(
        default="custom",
    )


class CreateOrderResponse(BaseModel):
    order_id: str
    key_id: str
    amount: int
    currency: str = Field(default="INR")
    credits_to_receive: int
    amount_inr: int


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class VerifyPaymentResponse(BaseModel):
    credits_added: int
    new_balance: int
    status: str


class PaymentHistoryItem(BaseModel):
    id: int
    amount_inr: int
    credits_purchased: int
    status: str
    currency: str
    razorpay_payment_id: str | None
    created_at: str
    completed_at: str | None


class PaymentHistoryResponse(BaseModel):
    transactions: list[PaymentHistoryItem]
    total_count: int = 0
    page: int = 1
    page_size: int = 20
    has_next: bool = False


class PaymentDetailResponse(BaseModel):
    id: int
    amount_inr: int
    amount_paise: int
    credits_purchased: int
    status: str
    currency: str
    provider: str
    razorpay_order_id: str | None
    razorpay_payment_id: str | None
    created_at: str
    completed_at: str | None
    metadata: dict


def format_payment_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def payment_history_item(txn: PaymentTransaction) -> PaymentHistoryItem:
    return PaymentHistoryItem(
        id=txn.id,
        amount_inr=txn.amount_inr,
        credits_purchased=txn.credits_purchased,
        status=txn.status.value,
        currency="INR",
        razorpay_payment_id=txn.razorpay_payment_id,
        created_at=format_payment_datetime(txn.created_at) or "",
        completed_at=format_payment_datetime(txn.completed_at),
    )


def payment_detail_response(txn: PaymentTransaction) -> PaymentDetailResponse:
    import json
    import logging

    logger = logging.getLogger(__name__)
    metadata = {}
    try:
        if txn.metadata_json:
            metadata = json.loads(txn.metadata_json)
    except json.JSONDecodeError:
        logger.warning("Invalid JSON in metadata for transaction %s", txn.id)

    return PaymentDetailResponse(
        id=txn.id,
        amount_inr=txn.amount_inr,
        amount_paise=txn.amount_paise,
        credits_purchased=txn.credits_purchased,
        status=txn.status.value,
        currency="INR",
        provider=getattr(txn, "provider", "razorpay"),
        razorpay_order_id=txn.razorpay_order_id,
        razorpay_payment_id=txn.razorpay_payment_id,
        created_at=format_payment_datetime(txn.created_at) or "",
        completed_at=format_payment_datetime(txn.completed_at),
        metadata=metadata,
    )
