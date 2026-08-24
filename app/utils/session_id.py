import uuid
from typing import Any, Optional

_UUID_V4_HELP = "Expected a valid UUID v4 string."


def validate_uuid4(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
    try:
        uuid_obj = uuid.UUID(str(value))
        if uuid_obj.version != 4:
            raise ValueError(f"UUID must be version 4. {_UUID_V4_HELP}")
        return str(uuid_obj)
    except (ValueError, AttributeError):
        raise ValueError(f"Invalid session ID format. {_UUID_V4_HELP}")

