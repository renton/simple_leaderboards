"""Unit tests for app.services.time_ranges."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.services.time_ranges import (
    InvalidRangeError,
    InvalidTimezoneError,
    range_to_bounds,
)


def utc(year, month, day, hour=0, minute=0, second=0):
    return datetime(year, month, day, hour, minute, second, tzinfo=UTC)


def test_all_time_returns_open_interval():
    assert range_to_bounds("all-time", "UTC") == (None, None)


def test_hourly_in_utc():
    start, end = range_to_bounds("hourly", "UTC", now_utc=utc(2026, 3, 15, 14, 37, 12))
    assert start == utc(2026, 3, 15, 14, 0, 0)
    assert end == utc(2026, 3, 15, 15, 0, 0)


def test_daily_in_game_timezone_spans_midnight():
    # 2026-05-20 03:00 UTC == 2026-05-19 23:00 in America/New_York (EDT, -04:00),
    # so "daily" range for that game is May 19 00:00 -> May 20 00:00 local.
    start, end = range_to_bounds(
        "daily", "America/New_York", now_utc=utc(2026, 5, 20, 3, 0)
    )
    ny = ZoneInfo("America/New_York")
    assert start == datetime(2026, 5, 19, 0, 0, tzinfo=ny).astimezone(UTC)
    assert end == datetime(2026, 5, 20, 0, 0, tzinfo=ny).astimezone(UTC)
    assert (end - start) == timedelta(days=1)


def test_weekly_is_iso_monday_start():
    # 2026-05-20 is a Wednesday in UTC.
    start, end = range_to_bounds("weekly", "UTC", now_utc=utc(2026, 5, 20, 12, 0))
    assert start == utc(2026, 5, 18)  # Monday
    assert end == utc(2026, 5, 25)  # next Monday
    assert (end - start) == timedelta(days=7)
    assert start.weekday() == 0


def test_weekly_when_now_is_monday_includes_today():
    # 2026-05-18 is a Monday. The bounds should be that Monday -> next Monday.
    start, end = range_to_bounds("weekly", "UTC", now_utc=utc(2026, 5, 18, 9, 0))
    assert start == utc(2026, 5, 18)
    assert end == utc(2026, 5, 25)


def test_monthly_in_utc_and_handles_year_rollover():
    start, end = range_to_bounds("monthly", "UTC", now_utc=utc(2026, 12, 15, 10))
    assert start == utc(2026, 12, 1)
    assert end == utc(2027, 1, 1)


def test_yearly_in_game_timezone():
    # Asia/Tokyo is UTC+9, no DST.
    start, end = range_to_bounds("yearly", "Asia/Tokyo", now_utc=utc(2026, 7, 1, 0, 0))
    tokyo = ZoneInfo("Asia/Tokyo")
    assert start == datetime(2026, 1, 1, 0, 0, tzinfo=tokyo).astimezone(UTC)
    assert end == datetime(2027, 1, 1, 0, 0, tzinfo=tokyo).astimezone(UTC)


def test_daily_across_spring_dst_boundary():
    # America/New_York spring-forward 2026 is 2026-03-08 02:00 -> 03:00 local.
    # The "daily" range for that local day is 23 hours long.
    start, end = range_to_bounds(
        "daily", "America/New_York", now_utc=utc(2026, 3, 8, 12, 0)
    )
    assert (end - start) == timedelta(hours=23)


def test_daily_across_fall_dst_boundary():
    # America/New_York fall-back 2026 is 2026-11-01 02:00 -> 01:00 local.
    # That local day is 25 hours long.
    start, end = range_to_bounds(
        "daily", "America/New_York", now_utc=utc(2026, 11, 1, 12, 0)
    )
    assert (end - start) == timedelta(hours=25)


def test_unknown_range_raises():
    with pytest.raises(InvalidRangeError):
        range_to_bounds("decadely", "UTC")


def test_unknown_timezone_raises():
    with pytest.raises(InvalidTimezoneError):
        range_to_bounds("daily", "Mars/Olympus_Mons")


def test_naive_now_is_assumed_utc():
    naive = datetime(2026, 5, 20, 12, 0)
    aware = utc(2026, 5, 20, 12, 0)
    assert range_to_bounds("hourly", "UTC", now_utc=naive) == range_to_bounds(
        "hourly", "UTC", now_utc=aware
    )
