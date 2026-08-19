"""UTC datetime helpers used at persistence and API boundaries."""

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return the current time as an aware UTC datetime."""
    return datetime.now(UTC)


def as_utc(value: str | datetime) -> datetime:
    """Parse and normalize a datetime to UTC.

    Legacy naive values are interpreted as UTC because SQLite's
    ``CURRENT_TIMESTAMP`` has historically been the source of those values.
    """
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def utc_isoformat(value: str | datetime) -> str:
    """Return a canonical ISO 8601 UTC string suitable for SQLite and APIs."""
    return as_utc(value).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def utc_now_isoformat() -> str:
    """Return the current UTC time in canonical storage format."""
    return utc_isoformat(utc_now())
