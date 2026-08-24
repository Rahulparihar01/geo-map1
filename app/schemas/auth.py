from datetime import datetime
from typing import Annotated, Optional

from pydantic import BaseModel, BeforeValidator, EmailStr, Field, field_validator, ValidationInfo

_WEAK_PASSWORDS = {
    "password",
    "password123",
    "12345678",
    "123456789",
    "qwerty123",
    "qwerty1",
    "letmein",
    "welcome",
    "admin123",
    "passw0rd",
    "name@197876",
    "hello",
    "abc123",
    "monkey",
}


def validate_password_strength(v: str) -> str:
    if not any(c.isupper() for c in v):
        raise ValueError("Password must contain at least one uppercase letter.")
    if not any(c.islower() for c in v):
        raise ValueError("Password must contain at least one lowercase letter.")
    if not any(c.isdigit() for c in v):
        raise ValueError("Password contain at least one digit.")
    if v.isalnum():
        raise ValueError("Password contain at least one special character.")
    if v.lower() in _WEAK_PASSWORDS:
        raise ValueError("This password is too common.")
    return v


def normalize_email(v: str) -> str:
    return v.strip().lower()


NormalizedEmail = Annotated[EmailStr, BeforeValidator(normalize_email)]


class SignupRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100, examples=["Jane Doe"])
    email: NormalizedEmail
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return validate_password_strength(v)


class SignupResponse(BaseModel):
    message: str
    email: str
    otp_expires_in_seconds: int
    otp_sent: bool = Field(
        default=True)


class VerifyOTPRequest(BaseModel):
    email: NormalizedEmail
    otp: str = Field(
        ..., min_length=6, max_length=6, pattern=r"^\d{6}$", examples=["482910"]
    )


class LoginRequest(BaseModel):
    email: NormalizedEmail
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("password")
    @classmethod
    def password_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Password cannot be empty.")
        return v


class UserResponse(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    is_active: bool
    email_verified: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None
    credits: int

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):

    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field()
    user: UserResponse


class ForgotPasswordRequest(BaseModel):
    email: NormalizedEmail


class ResendOTPRequest(BaseModel):
    email: NormalizedEmail


class ForgotPasswordResponse(BaseModel):
    message: str
    email: str
    otp_expires_in_seconds: int


class ResetPasswordRequest(BaseModel):
    email: NormalizedEmail
    otp: str = Field(
        ..., min_length=6, max_length=6, pattern=r"^\d{6}$", examples=["482910"]
    )
    new_password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v: str, info: ValidationInfo) -> str:
        if "new_password" in info.data and v != info.data["new_password"]:
            raise ValueError("Passwords do not match.")
        return v

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return validate_password_strength(v)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)
    confirm_new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("old_password")
    @classmethod
    def old_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Current password cannot be empty.")
        return v

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return validate_password_strength(v)

    @field_validator("confirm_new_password")
    @classmethod
    def passwords_match(cls, v: str, info: ValidationInfo) -> str:
        if "new_password" in info.data and v != info.data["new_password"]:
            raise ValueError("Passwords do not match.")
        return v


class ChangePasswordResponse(BaseModel):
    message: str


class ResetPasswordResponse(BaseModel):
    message: str
