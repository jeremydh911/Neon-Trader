from datetime import datetime, timezone


def now_utc_iso() -> str:
    """Return current UTC time as ISO formatted string."""
    return datetime.now(timezone.utc).isoformat()
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Optional


def now_utc() -> datetime:
    """Return a timezone-aware UTC datetime"""
    return datetime.now(timezone.utc)


def now_utc_iso() -> str:
    """Return the current UTC time as an ISO 8601 string"""
    return now_utc().isoformat()


def format_utc(dt: datetime) -> str:
    """Format a timezone-aware datetime to ISO 8601 string; if naive, assume UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def format_local(dt: Optional[datetime] = None, tz_name: Optional[str] = None, fmt: str = "%Y-%m-%d %H:%M:%S %Z") -> str:
    """Return a timezone-aware datetime formatted for local display.

    Args:
        dt: The datetime to format (assumed UTC if naive). Defaults to now_utc().
        tz_name: Optional IANA tz database name (e.g., 'America/New_York'). If None, uses local system timezone.
        fmt: Output format string (strftime compatible).
    Returns:
        Formatted string representing `dt` in the desired timezone.
    """
    if dt is None:
        dt = now_utc()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    if tz_name:
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = datetime.now().astimezone().tzinfo
    else:
        tz = datetime.now().astimezone().tzinfo

    return dt.astimezone(tz).strftime(fmt)


def format_local_iso(dt: Optional[datetime] = None, tz_name: Optional[str] = None) -> str:
    """Return a ISO8601 timestamp in the local timezone.

    Args:
        dt: The datetime to convert (defaults to now_utc()).
        tz_name: Optional tz name.
    Returns:
        ISO formatted string in the desired timezone.
    """
    if dt is None:
        dt = now_utc()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if tz_name:
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = datetime.now().astimezone().tzinfo
    else:
        tz = datetime.now().astimezone().tzinfo
    return dt.astimezone(tz).isoformat()


def format_for_ui(dt: Optional[datetime] = None, use_local_time: bool = True, tz_name: Optional[str] = None, fmt: Optional[str] = None) -> str:
    """Format a datetime string for UI display.

    Args:
        dt: The datetime to format (defaults to now_utc()).
        use_local_time: Whether to format in local timezone (True) or UTC (False).
        tz_name: Optional timezone name for local formatting.
        fmt: Optional strftime format string. If provided, returns a human readable string, otherwise returns ISO string.
    """
    if use_local_time:
        if fmt:
            return format_local(dt, tz_name=tz_name, fmt=fmt)
        return format_local_iso(dt, tz_name=tz_name)
    else:
        if fmt:
            d = dt or now_utc()
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            return d.astimezone(timezone.utc).strftime(fmt)
        return now_utc_iso() if dt is None else format_utc(dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))
