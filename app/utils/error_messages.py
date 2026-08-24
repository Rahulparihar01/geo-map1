# Authentication
AUTH_TOKEN_INVALID              = "Invalid or expired token."

# Validation
VALIDATION_INVALID_COORDINATES  = "Invalid coordinates."

# Location
LOCATION_UPDATE_FAILED          = "Location update failed. Try again."
LOCATION_MANUAL_RATE_LIMIT      = "Too many manual location updates. Try again later."
LOCATION_SEARCH_FAILED          = "Unable to search for this location. Please try again."
LOCATION_SEARCH_INVALID_QUERY   = "Please enter a location to search."
LOCATION_GEOCODING_FAILED       = "Unable to resolve coordinates to an address. Please try again."
LOCATION_GEOCODING_TIMEOUT      = "Address lookup timed out. Please try again."
LOCATION_HISTORY_ERROR          = "Unable to load location history. Please try again."

# Payment & Credits
PAYMENT_VERIFICATION_FAILED     = "Payment verification failed. Try again."
PAYMENT_SERVICE_UNAVAILABLE     = "Payment service unavailable. Try again later."
PAYMENT_INVALID_AMOUNT          = "Invalid payment amount."
PAYMENT_INVALID_FORMAT          = "Invalid payment details."
PAYMENT_NOT_FOUND               = "Payment record not found."
TRANSACTION_NOT_FOUND           = "Transaction not found."
AMOUNT_MISMATCH                 = "Payment amount does not match."
CREDIT_ALLOCATION_FAILED        = "Payment received but credits could not be applied."
PAYMENT_FAILED                  = "Payment Failed. Please try again or use a different payment method."
OUT_OF_CREDIT                   = "Out of credit. Please purchase more credits to continue."

# Webhook
WEBHOOK_SIGNATURE_MISSING       = "Payment signature missing."
WEBHOOK_SIGNATURE_INVALID       = "Payment signature invalid."
WEBHOOK_INVALID_JSON            = "Malformed payment payload."

# Chat & Sessions
SESSION_LIMIT_REACHED           = "Session limit reached. Delete old sessions first."

# Comparison
COMPARISON_FAILED               = "Place comparison failed."

# Places & Visits
VISIT_NOT_FOUND                 = "Visit not found."
VISIT_NOT_ACCESSIBLE            = "Visit is not accessible."
SAVED_PLACE_NOT_FOUND           = "Saved place not found."
PLACE_LOCKED                    = "This place is locked."
PLACE_ALREADY_UNLOCKED          = "This place is already unlocked."
PLACE_QUESTION_LIMIT_REACHED    = "You've reached the question limit for this place."
PLACE_NOT_FOUND                 = "Place information not found. Please try again."
PLACE_CATEGORY_NOT_SUPPORTED    = "This place type is not supported."

# Server & General
SERVER_ERROR                    = "Something went wrong. Try again later."
FEATURE_DISABLED                = "This feature is currently disabled."


# ---------------------------------------------------------------------------
# Error sanitisation — shared by HTTP exception handler and WebSocket handler
# ---------------------------------------------------------------------------
import logging
import re
from typing import Any

_logger = logging.getLogger(__name__)


def sanitize_error_message(message: Any, context: str = "") -> str:

    if isinstance(message, dict):
        _logger.warning("Dict passed as error detail for %s: %s", context, message)
        inner = message.get("message", message.get("description", SERVER_ERROR))
        if isinstance(inner, str):
            return sanitize_error_message(inner, context)
        return SERVER_ERROR

    if not isinstance(message, str):
        return SERVER_ERROR

    raw = message

    # Payment / gateway errors — surface a generic message
    has_json_error = bool(re.search(r'\{.*"error".*\}', raw, re.DOTALL))
    has_bad_request = "BAD_REQUEST_ERROR" in raw
    has_payment_pattern = bool(re.search(
        r'payment.*error|payment_authentication', raw, re.IGNORECASE
    ))
    has_razorpay_pattern = bool(re.search(
        r'razorpay|order.*payment|Error:\s*\d+\s*\|', raw, re.IGNORECASE
    ))
    if has_json_error or has_bad_request or has_payment_pattern or has_razorpay_pattern:
        _logger.warning("Sanitised payment/gateway error for %s: %s", context, raw[:500])
        return PAYMENT_FAILED

    # Credit-related errors — surface a specific message
    if (
        "Not enough credits" in raw
        or ("credits" in raw.lower()
            and ("need" in raw.lower() or "only have" in raw.lower()))
    ):
        return OUT_OF_CREDIT

    # Stack traces / internal errors — never leak to clients
    if re.search(r'Traceback|File\s+".*",\s+line|Exception|Error:', raw):
        _logger.warning("Stripped stack trace from error for %s: %s", context, raw[:300])
        return SERVER_ERROR

    # Overlong messages — truncate to avoid leaking internals
    if len(raw) > 300:
        _logger.warning("Truncated overlong error for %s: %s", context, raw[:500])
        return SERVER_ERROR

    return raw
