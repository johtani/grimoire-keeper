"""Tests for UTC datetime normalization."""

from datetime import UTC, datetime, timedelta, timezone

from grimoire_api.utils.datetime import as_utc, utc_isoformat, utc_now


def test_utc_now_is_aware() -> None:
    value = utc_now()

    assert value.tzinfo is UTC
    assert value.utcoffset() == timedelta(0)


def test_naive_legacy_value_is_interpreted_as_utc() -> None:
    value = as_utc("2025-01-01 12:34:56")

    assert value == datetime(2025, 1, 1, 12, 34, 56, tzinfo=UTC)


def test_offset_value_crossing_date_boundary_is_normalized() -> None:
    source = datetime(2025, 1, 2, 1, 30, tzinfo=timezone(timedelta(hours=9)))

    assert utc_isoformat(source) == "2025-01-01T16:30:00.000Z"
