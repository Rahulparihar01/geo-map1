from typing import Optional


def format_distance(meters: Optional[int]) -> Optional[str]:
    if meters is None:
        return None
    if meters < 1000:
        return f"{meters} m"
    return f"{meters / 1000:.1f} km"


def format_duration(seconds: Optional[int]) -> Optional[str]:
    if seconds is None:
        return None
    if seconds < 60:
        return "<1 min"

    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min"

    hours, remaining_minutes = divmod(minutes, 60)
    if remaining_minutes == 0:
        return "1 hour" if hours == 1 else f"{hours} hours"

    hour_label = "hour" if hours == 1 else "hours"
    return f"{hours} {hour_label} {remaining_minutes} min"
