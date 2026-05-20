"""Map a leaderboard range name + game timezone to UTC bounds.

Bounds are half-open: [start, end). `all-time` returns (None, None).

Computation happens in pure Python via stdlib `zoneinfo`. DST is handled
correctly because zoneinfo is rules-based. The query layer filters on a
plain indexed UTC `submitted_at` column, so we get index seek performance
without any `AT TIME ZONE` SQL.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

VALID_RANGES = frozenset(
    {"all-time", "hourly", "daily", "weekly", "monthly", "yearly"}
)


class InvalidRangeError(ValueError):
    pass


class InvalidTimezoneError(ValueError):
    pass


def _add_months(dt: datetime, months: int) -> datetime:
    new_month = dt.month + months
    year = dt.year + (new_month - 1) // 12
    month = ((new_month - 1) % 12) + 1
    return dt.replace(year=year, month=month)


def range_to_bounds(
    range_name: str,
    tz_name: str,
    now_utc: datetime | None = None,
) -> tuple[datetime | None, datetime | None]:
    """Return (start_utc, end_utc) for the current period of `range_name`.

    - `range_name` ∈ VALID_RANGES (raises InvalidRangeError otherwise).
    - `tz_name` is an IANA timezone string (raises InvalidTimezoneError otherwise).
    - `now_utc` defaults to wall-clock `datetime.now(timezone.utc)`.

    For `all-time` returns (None, None) — the query layer omits the WHERE clause.
    """
    if range_name not in VALID_RANGES:
        raise InvalidRangeError(f"unknown range {range_name!r}")
    if range_name == "all-time":
        return None, None

    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError) as e:
        raise InvalidTimezoneError(f"invalid IANA timezone {tz_name!r}") from e

    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    elif now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    local = now_utc.astimezone(tz)

    if range_name == "hourly":
        start_local = local.replace(minute=0, second=0, microsecond=0)
        end_local = start_local + timedelta(hours=1)
    elif range_name == "daily":
        start_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = start_local + timedelta(days=1)
    elif range_name == "weekly":
        # ISO week: Monday start
        start_local = (local - timedelta(days=local.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end_local = start_local + timedelta(days=7)
    elif range_name == "monthly":
        start_local = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_local = _add_months(start_local, 1)
    elif range_name == "yearly":
        start_local = local.replace(
            month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
        end_local = start_local.replace(year=start_local.year + 1)
    else:  # pragma: no cover - VALID_RANGES guard above
        raise InvalidRangeError(f"unknown range {range_name!r}")

    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)
