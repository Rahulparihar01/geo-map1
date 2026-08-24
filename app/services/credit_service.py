import asyncio
import logging
from functools import wraps
from typing import Callable
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from app.exceptions.custom_exceptions import InsufficientCreditsError, NotFoundError
from app.models.user import User

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BASE_DELAY = 0.1


def _retry_on_deadlock(func: Callable) -> Callable:

    @wraps(func)
    async def wrapper(*args, **kwargs):
        last_deadlock_exc = None
        for attempt in range(_MAX_RETRIES):
            try:
                return await func(*args, **kwargs)
            except OperationalError as exc:
                error_code = getattr(exc.orig, "pgcode", "")
                if error_code in ("40P01", "40001"):
                    last_deadlock_exc = exc
                    delay = _BASE_DELAY * (2**attempt)
                    logger.warning(
                        "Credit deduct deadlock (attempt %d/%d), retrying in %.1fs: %s",
                        attempt + 1,
                        _MAX_RETRIES,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)
                else:
                    raise
            except (NotFoundError, InsufficientCreditsError):
                raise
        raise last_deadlock_exc

    return wrapper


class CreditService:
    @staticmethod
    @_retry_on_deadlock
    async def deduct(db: Session, user_id: int, amount: int) -> int:
        user = db.query(User).filter(User.id == user_id).with_for_update().first()
        if user is None:
            raise NotFoundError(f"User {user_id} not found")

        available = user.credits or 0
        if available < amount:
            raise InsufficientCreditsError(required=amount, available=available)

        user.credits = available - amount
        db.flush()

        logger.info(
            "Deducted %s credits from user %s; remaining=%s",
            amount,
            user_id,
            user.credits,
        )
        return user.credits

    @staticmethod
    async def check_balance(db: Session, user_id: int, required: int) -> None:
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            raise NotFoundError(f"User {user_id} not found")

        available = user.credits or 0
        if available < required:
            raise InsufficientCreditsError(required=required, available=available)
