import json
import hashlib
import hmac
import logging
import secrets
import string
from enum import Enum

from app.core.config import settings
from app.core.redis import get_redis_client

logger = logging.getLogger(__name__)

_PENDING_PREFIX = "otp:pending:"
_RESET_PREFIX = "otp:reset:"
_COOLDOWN_PREFIX = "otp:cooldown:"
_RESEND_COUNT_PREFIX = "otp:resends:"


class OTPPurpose(str, Enum):
    REGISTRATION_VERIFICATION = "registration_verification"
    PASSWORD_RESET = "password_reset"


class OTPCooldownError(RuntimeError):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("OTP resend is still cooling down.")
        self.retry_after_seconds = max(1, retry_after_seconds)


class OTPResendLimitError(RuntimeError):
    pass

_VERIFY_LUA_SCRIPT = """
local key     = KEYS[1]
local otp_hash = ARGV[1]
local otp_legacy = ARGV[2]
local max_att = tonumber(ARGV[3])

local raw = redis.call('GET', key)
if not raw then
    return {3, ''}
end

local data = cjson.decode(raw)
if data['otp_hash'] == otp_hash or data['otp'] == otp_legacy then
    -- Correct OTP — consume and return the user_id
    redis.call('DEL', key)
    return {0, data['user_id']}
end

-- Wrong OTP
local attempts = (data['attempts'] or 0) + 1
if attempts >= max_att then
    redis.call('DEL', key)
    return {1, ''}
end

data['attempts'] = attempts
local ttl = redis.call('TTL', key)
if ttl > 0 then
    redis.call('SETEX', key, ttl, cjson.encode(data))
end
return {2, tostring(attempts)}
"""

_ISSUE_RESEND_LUA_SCRIPT = """
local otp_key = KEYS[1]
local cooldown_key = KEYS[2]
local count_key = KEYS[3]
local otp_payload = ARGV[1]
local otp_ttl = tonumber(ARGV[2])
local cooldown_ttl = tonumber(ARGV[3])
local window_ttl = tonumber(ARGV[4])
local max_resends = tonumber(ARGV[5])

local cooldown = redis.call('TTL', cooldown_key)
if cooldown > 0 then
    return {1, cooldown}
end

local count = tonumber(redis.call('GET', count_key) or '0')
if count >= max_resends then
    local remaining = redis.call('TTL', count_key)
    return {2, remaining}
end

redis.call('SETEX', otp_key, otp_ttl, otp_payload)
redis.call('INCR', count_key)
if count == 0 then
    redis.call('EXPIRE', count_key, window_ttl)
end
redis.call('SETEX', cooldown_key, cooldown_ttl, '1')
return {0, ''}
"""


def _generate_otp(length: int = 6) -> str:
    return "".join(secrets.choice(string.digits) for _ in range(length))


def _hash_otp(otp: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(),
        otp.encode(),
        hashlib.sha256,
    ).hexdigest()


def _purpose_prefix(purpose: OTPPurpose) -> str:
    if purpose is OTPPurpose.REGISTRATION_VERIFICATION:
        return _PENDING_PREFIX
    return _RESET_PREFIX


async def _store_otp(
    purpose: OTPPurpose,
    email: str,
    user_id: int,
    *,
    enforce_resend_limits: bool = False,
) -> str:
    redis = get_redis_client()
    if redis is None:
        raise RuntimeError("Redis is unavailable.")

    otp = _generate_otp()
    payload = json.dumps(
        {
            "otp_hash": _hash_otp(otp),
            "attempts": 0,
            "user_id": str(user_id),
            "email": email,
            "purpose": purpose.value,
        }
    )
    key = f"{_purpose_prefix(purpose)}{email}"

    if enforce_resend_limits:
        result = await redis.eval(
            _ISSUE_RESEND_LUA_SCRIPT,
            3,
            key,
            f"{_COOLDOWN_PREFIX}{purpose.value}:{email}",
            f"{_RESEND_COUNT_PREFIX}{purpose.value}:{email}",
            payload,
            str(settings.OTP_EXPIRE_SECONDS),
            str(settings.OTP_RESEND_COOLDOWN_SECONDS),
            str(settings.OTP_RESEND_WINDOW_SECONDS),
            str(settings.OTP_MAX_RESENDS_PER_WINDOW),
        )
        result_code = int(result[0])
        if result_code == 1:
            raise OTPCooldownError(int(result[1]))
        if result_code == 2:
            raise OTPResendLimitError()
    else:
        await redis.setex(key, settings.OTP_EXPIRE_SECONDS, payload)

    logger.info("OTP stored for %s (user_id=%s, TTL=%ss)", email, user_id, settings.OTP_EXPIRE_SECONDS)
    return otp


async def store_pending_registration(email: str, user_id: int) -> str:
    return await _store_otp(
        OTPPurpose.REGISTRATION_VERIFICATION,
        email,
        user_id,
    )


async def resend_pending_registration(email: str, user_id: int) -> str:
    return await _store_otp(
        OTPPurpose.REGISTRATION_VERIFICATION,
        email,
        user_id,
        enforce_resend_limits=True,
    )


async def verify_and_consume(email: str, submitted_otp: str) -> dict | None:
    return await _verify_otp(
        OTPPurpose.REGISTRATION_VERIFICATION,
        email,
        submitted_otp,
    )


async def verify_reset_otp(email: str, submitted_otp: str) -> dict | None:
    return await _verify_otp(OTPPurpose.PASSWORD_RESET, email, submitted_otp)


async def _verify_otp(
    purpose: OTPPurpose,
    email: str,
    submitted_otp: str,
) -> dict | None:
    redis = get_redis_client()
    if redis is None:
        raise RuntimeError("Redis is unavailable.")

    key = f"{_purpose_prefix(purpose)}{email}"

    status, data = await redis.eval(
        _VERIFY_LUA_SCRIPT,
        1,
        key,
        _hash_otp(submitted_otp),
        submitted_otp,
        str(settings.OTP_MAX_ATTEMPTS),
    )

    if status == 0:
        logger.info("OTP verified and consumed for %s", email)
        if data and data.strip():
            return {"user_id": data, "email": email, "purpose": purpose.value}
        return None

    if status == 1:
        logger.warning("Max OTP attempts for %s — entry deleted", email)
        return None

    if status == 2:
        logger.warning(
            "Wrong OTP for %s (attempt %s/%d)",
            email,
            data,
            settings.OTP_MAX_ATTEMPTS,
        )
        return None

    logger.info("No pending OTP for %s (expired or never set)", email)
    return None


async def delete_pending_registration(email: str) -> None:
    redis = get_redis_client()
    if redis is None:
        return
    await redis.delete(f"{_PENDING_PREFIX}{email}")
    logger.info("Pending OTP cancelled for %s", email)


async def _otp_exists(purpose: OTPPurpose, email: str) -> bool:
    redis = get_redis_client()
    if redis is None:
        return False
    key = f"{_purpose_prefix(purpose)}{email}"
    return await redis.exists(key) > 0


async def store_reset_otp(email: str, user_id: int) -> str:
    if await _otp_exists(OTPPurpose.PASSWORD_RESET, email):
        return await _store_otp(
            OTPPurpose.PASSWORD_RESET,
            email,
            user_id,
            enforce_resend_limits=True,
        )
    return await _store_otp(OTPPurpose.PASSWORD_RESET, email, user_id)


async def resend_reset_otp(email: str, user_id: int) -> str:
    return await _store_otp(
        OTPPurpose.PASSWORD_RESET,
        email,
        user_id,
        enforce_resend_limits=True,
    )
