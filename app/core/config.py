from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str

    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int

    GOOGLE_PLACES_API_KEY: str
    GOOGLE_PLACES_BASE_URL: str
    GOOGLE_ROUTES_BASE_URL: str = "https://routes.googleapis.com/directions/v2"
    GOOGLE_GEOCODING_BASE_URL: str = "https://maps.googleapis.com/maps/api/geocode"

    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_PASSWORD: Optional[str] = None
    REDIS_CACHE_TTL: int
    REDIS_DETAILS_CACHE_TTL: int

    REDIS_ROUTES_CACHE_TTL: int = 300
    REDIS_ROUTE_MATRIX_CACHE_TTL: int = 120
    REDIS_AUTOCOMPLETE_CACHE_TTL: int = 300

    DETAILS_STALE_AFTER_DAYS: int = 7

    OPENAI_API_KEY: str
    OPENAI_EMBEDDING_MODEL: str
    OPENAI_CHAT_MODEL: str
    OPENAI_MAX_CONTEXT_TOKENS: int

    MAX_SESSIONS_PER_USER: int = 100

    PLACE_UNLOCK_ENABLED: bool = True

    PINECONE_API_KEY: str
    PINECONE_INDEX_NAME: str
    PINECONE_ENVIRONMENT: str

    SMTP_HOST: str
    SMTP_PORT: int
    SMTP_USER: str
    SMTP_PASSWORD: str
    SMTP_FROM_NAME: str
    SMTP_FROM_EMAIL: str
    SMTP_USE_TLS: bool = True
    MAILPIT_HOST: str = "localhost"
    MAILPIT_PORT: int = 1025

    RAZORPAY_KEY_ID: str
    RAZORPAY_KEY_SECRET: str
    RAZORPAY_WEBHOOK_SECRET: str

    OTP_EXPIRE_SECONDS: int
    OTP_MAX_ATTEMPTS: int
    OTP_RESEND_COOLDOWN_SECONDS: int = 60
    OTP_MAX_RESENDS_PER_WINDOW: int = 5
    OTP_RESEND_WINDOW_SECONDS: int = 3600

    TRUSTED_PROXY_IPS: str = ""
    CORS_ORIGINS: str = "*"

    LANGFUSE_PUBLIC_KEY: Optional[str] = None
    LANGFUSE_SECRET_KEY: Optional[str] = None
    LANGFUSE_BASE_URL: str = "https://cloud.langfuse.com"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return value

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith(
            (
                "postgresql://",
                "postgresql+psycopg2://",
                "postgresql+asyncpg://",
            )
        ):
            raise ValueError("Invalid PostgreSQL DATABASE_URL")
        return value

settings = Settings()