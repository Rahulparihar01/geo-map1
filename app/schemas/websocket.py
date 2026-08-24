from typing import Optional
from pydantic import BaseModel, Field, field_validator


def _reject_float_int(value, field_name: str):
    if isinstance(value, float):
        raise ValueError(
            f"{field_name} must be a whole number (integer). "
            f"Decimal values are not supported."
        )
    return value


class WSClientMessage(BaseModel):
    type: str = Field(
        ...,
    )
    query: str = Field(
        ...,
        min_length=1,
        max_length=4000,
    )
    session_id: Optional[str] = Field(
        default=None,
    )
    place_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=255,
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=10,
    )

    @field_validator("top_k", mode="before")
    @classmethod
    def reject_float_top_k(cls, v):
        return _reject_float_int(v, "top_k")


class WSStreamStart(BaseModel):

    type: str = "stream_start"
    session_id: str
    is_new_session: bool


class WSChunk(BaseModel):

    type: str = "chunk"
    session_id: str
    token: str


class WSStreamEnd(BaseModel):

    type: str = "stream_end"
    session_id: str
    title: Optional[str] = None


class WSError(BaseModel):

    type: str = "error"
    session_id: Optional[str] = None
    message: str
