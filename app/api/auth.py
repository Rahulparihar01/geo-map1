import logging
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rate_limiter import shared_limiter as limiter
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
    validate_token_sub,
)
from app.database.connection import get_db
from app.dependencies.auth import get_current_user, get_optional_user
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    ResetPasswordRequest,
    ResetPasswordResponse,
    ResendOTPRequest,
    SignupRequest,
    SignupResponse,
    TokenResponse,
    UserResponse,
    VerifyOTPRequest,
    ChangePasswordRequest,
    ChangePasswordResponse,
)
from app.services.email_service import send_otp_email, send_reset_email
from app.services.otp_service import (
    delete_pending_registration,
    resend_pending_registration,
    store_pending_registration,
    store_reset_otp,
    OTPCooldownError,
    OTPResendLimitError,
    verify_and_consume,
    verify_reset_otp,
)
from app.utils.error_messages import AUTH_TOKEN_INVALID

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


def _issue_access_token(user: User) -> TokenResponse:
    access = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return TokenResponse(
        access_token=access,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserResponse.model_validate(user),
    )


def _check_auth(caller: User | None, message: str, include_otp_sent: bool = True) -> None:
    if caller is None:
        return
    logger.warning(
        "Authenticated user id=%s attempted a public auth action — blocked", caller.id
    )
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message)


_SIGNUP_EXISTS_DETAIL = "An account with this email already exists. Please log in."


def _extract_user_id(reg_data: dict) -> int:
    user_id = validate_token_sub(reg_data.get("user_id"))
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Something went wrong while processing your request. Please try again.",
        )
    return user_id


def _otp_resend_error(exc: RuntimeError) -> HTTPException:
    if isinstance(exc, OTPCooldownError):
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Please wait before requesting another verification code.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        )
    if isinstance(exc, OTPResendLimitError):
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many verification code requests. Please try again later.",
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="We're having trouble sending your verification code. Please try again in a few moments.",
    )


def _forgot_password_msg(email: str) -> ForgotPasswordResponse:
    return ForgotPasswordResponse(
        message="If an account with this email exists, a password reset code has been sent.",
        email=email,
        otp_expires_in_seconds=settings.OTP_EXPIRE_SECONDS,
    )


def _resend_otp_msg(email: str, *, otp_sent: bool) -> SignupResponse:
    message = (
        "A verification code has been sent to your email."
        if otp_sent
        else "If a pending registration exists for this email, a verification code has been sent."
    )
    return SignupResponse(
        message=message,
        email=email,
        otp_expires_in_seconds=settings.OTP_EXPIRE_SECONDS,
        otp_sent=otp_sent,
    )


def _fail_unavailable(detail: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=detail,
    )


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def signup(
    request: Request,
    payload: SignupRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    repo = UserRepository(db)

    existing_user = repo.get_by_email_for_update(payload.email)
    if existing_user is not None:
        if not existing_user.email_verified:
            logger.info("Re-registration for pending email %s", payload.email)
            await delete_pending_registration(payload.email)
            repo.delete_pending_user(existing_user)
            db.flush()
        else:
            logger.info("Signup blocked for existing verified email: %s", payload.email)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_SIGNUP_EXISTS_DETAIL,
            )

    try:
        pending_user = repo.create_pending_user(
            full_name=payload.full_name,
            email=payload.email,
            hashed_password=hash_password(payload.password),
        )
    except IntegrityError:
        db.rollback()
        winner = repo.get_by_email_for_update(payload.email)
        if winner is not None and winner.email_verified:
            logger.info(
                "Signup IntegrityError — concurrent insert won for verified email: %s", payload.email
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_SIGNUP_EXISTS_DETAIL,
            )
        logger.info("Signup IntegrityError — concurrent insert for %s — please retry", payload.email)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "A registration for this email is already in progress. Please try again.",
                "otp_sent": False,
            },
        )

    try:
        otp = await store_pending_registration(email=payload.email, user_id=pending_user.id)
    except RuntimeError as exc:
        repo.delete_pending_user(pending_user)
        logger.error("Redis unavailable during signup: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="We're having trouble sending your verification code. Please try again in a few moments.",
        )

    background_tasks.add_task(send_otp_email, payload.email, payload.full_name, otp)
    db.commit()
    logger.info("Signup OTP queued for %s, pending user id=%s", payload.email, pending_user.id)
    return SignupResponse(
        message="Verification code sent. Check your email and enter the code to complete registration.",
        email=payload.email,
        otp_expires_in_seconds=settings.OTP_EXPIRE_SECONDS,
        otp_sent=True,
    )


@router.post(
    "/resend-signup",
    response_model=SignupResponse,
    status_code=status.HTTP_200_OK,
)
@limiter.limit("3/minute")
@limiter.limit("10/hour")
async def resend_signup(
    request: Request,
    payload: ResendOTPRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    caller: User | None = Depends(get_optional_user),
):
    _check_auth(caller, "You are already logged in. Please log out before verifying a new account.", include_otp_sent=True)

    generic_response = _resend_otp_msg(payload.email, otp_sent=False)
    user = UserRepository(db).get_by_email(payload.email)
    if user is None or user.email_verified or user.is_active:
        return generic_response

    try:
        otp = await resend_pending_registration(payload.email, user.id)
    except RuntimeError as exc:
        logger.error("Registration OTP resend failed: %s", exc)
        raise _otp_resend_error(exc)

    background_tasks.add_task(send_otp_email, payload.email, user.full_name, otp)
    return _resend_otp_msg(payload.email, otp_sent=True)


@router.post("/verify-otp", response_model=TokenResponse, status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def verify_otp(
    request: Request,
    payload: VerifyOTPRequest,
    db: Session = Depends(get_db),
    caller: User | None = Depends(get_optional_user),
):
    _check_auth(caller, "You are already logged in. Log out before verifying a new account.", include_otp_sent=True)

    try:
        reg_data = await verify_and_consume(email=payload.email, submitted_otp=payload.otp)
    except RuntimeError as exc:
        logger.error("Redis error: %s", exc)
        _fail_unavailable(
            "We're having trouble verifying your code. Please try again in a few moments."
        )

    if reg_data is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That code is incorrect or has expired. Please check it and try again, or sign up for a new one.",
        )

    repo = UserRepository(db)
    user = repo.get_by_id(_extract_user_id(reg_data))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your sign-up session has expired. Please sign up again for a new code.",
        )
    if user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This account is already verified. Please log in instead.",
        )

    user = repo.activate_pending_user(user)
    db.commit()
    logger.info("User activated via OTP: id=%s email=%s", user.id, payload.email)
    return _issue_access_token(user)


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def login(
    request: Request,
    payload: LoginRequest,
    db: Session = Depends(get_db),
    caller: User | None = Depends(get_optional_user),
):
    _check_auth(caller, "You are already logged in. Please log out first to switch accounts.", include_otp_sent=False)

    repo = UserRepository(db)
    user = repo.get_by_email(payload.email)

    if (
        user is None
        or not user.hashed_password
        or not verify_password(payload.password, user.hashed_password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The email or password you entered is incorrect. Please try again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated. Please contact support for help.",
        )

    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email first. Sign up again to receive a new verification code.",
        )

    logger.info("Login success: user_id=%s", user.id)
    return _issue_access_token(user)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post(
    "/forgot-password",
    response_model=ForgotPasswordResponse,
    status_code=status.HTTP_200_OK,
)
@limiter.limit("3/minute")
@limiter.limit("10/hour")
async def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    generic_response = _forgot_password_msg(payload.email)

    repo = UserRepository(db)
    user = repo.get_by_email(payload.email)

    if user is None or not user.email_verified or not user.is_active:
        logger.info("Forgot-password for %s — returning generic success", payload.email)
        return generic_response

    try:
        otp = await store_reset_otp(email=payload.email, user_id=user.id)
    except RuntimeError as exc:
        logger.error("Redis error: %s", exc)
        raise _otp_resend_error(exc)

    background_tasks.add_task(send_reset_email, payload.email, user.full_name, otp)
    logger.info("Password reset OTP queued for %s (user_id=%s)", payload.email, user.id)
    return generic_response


@router.post("/reset-password", response_model=ResetPasswordResponse, status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def reset_password(
    request: Request,
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db)):
    try:
        reg_data = await verify_reset_otp(email=payload.email, submitted_otp=payload.otp)
    except RuntimeError as exc:
        logger.error("Redis error: %s", exc)
        _fail_unavailable("We're having trouble verifying your code")

    if reg_data is None:
        logger.warning("Password reset: invalid or expired OTP for email=%s", payload.email)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=AUTH_TOKEN_INVALID,
        )

    repo = UserRepository(db)
    user = repo.get_active_by_id(_extract_user_id(reg_data))
    if user is None:
        logger.warning("Password reset: user not found for email=%s", payload.email)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=AUTH_TOKEN_INVALID,
        )

    repo.update_password(user, hash_password(payload.new_password))
    db.commit()
    logger.info("Password reset successful for user_id=%s", user.id)
    return ResetPasswordResponse(
        message="Password reset successful. Please log in with your new password.",
    )


@router.post("/change-password", response_model=ChangePasswordResponse, status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def change_password(
    request: Request,
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.hashed_password or not verify_password(
        payload.old_password, current_user.hashed_password
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )

    UserRepository(db).update_password(current_user, hash_password(payload.new_password))
    db.commit()
    logger.info("Password changed for user_id=%s", current_user.id)
    return ChangePasswordResponse(message="Password changed successfully.")