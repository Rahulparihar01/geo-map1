import logging
from typing import Any, Dict, Optional
import razorpay
from app.core.config import settings
logger = logging.getLogger(__name__)
_razorpay_client: Optional[razorpay.Client] = None

def _get_client() -> razorpay.Client:
    global _razorpay_client

    if _razorpay_client is None:
        if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
            logger.warning(
                "RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are not set — "
                "payment endpoints will fail at runtime."
            )
            raise RuntimeError(
                "RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must be set in the "
                "environment before using Razorpay."
            )
        _razorpay_client = razorpay.Client(
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
        )
        logger.info("Razorpay client initialized and cached")

    return _razorpay_client


class RazorpayService:
    @staticmethod
    def get_key_id() -> str:
        return settings.RAZORPAY_KEY_ID

    @staticmethod
    def get_active_key_pair() -> tuple[str, str]:
        return (settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)

    @staticmethod
    async def create_order(
        *,
        amount_paise: int,
        receipt: str,
        notes: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        try:
            order = _get_client().order.create(
                data={
                    "amount": amount_paise,
                    "currency": "INR",
                    "receipt": receipt,
                    "notes": notes or {},
                    "payment_capture": 1,
                }
            )
            logger.info(
                "Razorpay order created: %s (amount=%s paise, receipt=%s)",
                order["id"],
                amount_paise,
                receipt,
            )
            return {
                "id": order["id"],
                "amount": order["amount"],
                "currency": order["currency"],
                "receipt": order.get("receipt"),
            }
        except Exception as exc:
            logger.error("Razorpay error creating order: %s (type=%s)", exc, type(exc).__name__)
            raise

    @staticmethod
    async def verify_payment_signature(
        *,
        order_id: str,
        payment_id: str,
        signature: str,
    ) -> None:
        logger.debug(
            "Verifying signature: order=%s payment=%s sig_len=%s",
            order_id,
            payment_id,
            len(signature),
        )
        try:
            _get_client().utility.verify_payment_signature(
                {
                    "razorpay_order_id": order_id,
                    "razorpay_payment_id": payment_id,
                    "razorpay_signature": signature,
                }
            )
        except Exception as exc:
            logger.error(
                "Razorpay signature verification error: %s (type=%s) — "
                "possible causes: invalid key pair, wrong environment (dev vs prod), "
                "corrupted signature, or mismatched order/payment IDs",
                exc,
                type(exc).__name__,
            )
            raise
        logger.info(
            "Razorpay payment signature verified: order=%s payment=%s",
            order_id,
            payment_id,
        )

    @staticmethod
    async def verify_webhook_signature(
        raw_body: bytes,
        signature: str,
        webhook_secret: str,
    ) -> None:
        body = (
            raw_body.decode("utf-8")
            if isinstance(raw_body, (bytes, bytearray))
            else raw_body
        )
        _get_client().utility.verify_webhook_signature(
            body, signature, webhook_secret
        )
        logger.info("Razorpay webhook signature verified")

    @staticmethod
    async def create_webhook(
        *,
        url: str,
        events: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        if events is None:
            events = [
                "payment.authorized",
                "payment.failed",
                "payment.captured",
                "order.paid",
                "refund.created",
                "refund.processed",
            ]
        
        try:
            webhook = _get_client().webhook.create(
                data={
                    "url": url,
                    "events": events,
                }
            )
            logger.info(
                "Razorpay webhook created: %s (url=%s events=%s)",
                webhook["id"],
                url,
                ",".join(events),
            )
            return {
                "id": webhook["id"],
                "url": webhook["url"],
                "events": webhook["events"],
                "signing_secret": webhook.get("secret"),
            }
        except Exception as exc:
            logger.error("Razorpay error creating webhook: %s", exc)
            raise
