from datetime import datetime, timezone


def now_utc_iso() -> str:
    """Return current UTC time as ISO formatted string."""
    return datetime.now(timezone.utc).isoformat()
