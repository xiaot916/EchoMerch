"""Business-day helpers shared by daily collection entry points.

Platform reports are keyed to China Standard Time rather than the machine's
local timezone.  Keeping the calculation here prevents a scheduler running
around midnight from accidentally requesting today's partial report.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def today_in_shanghai(*, now: datetime | None = None) -> date:
    """Return today's calendar date in China Standard Time."""

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=SHANGHAI_TZ)
    return current.astimezone(SHANGHAI_TZ).date()


def yesterday_in_shanghai(*, now: datetime | None = None) -> date:
    """Return the completed business day immediately before today in China."""

    return today_in_shanghai(now=now) - timedelta(days=1)


def parse_business_day(value: str, *, now: datetime | None = None) -> date:
    """Parse an ISO day or the relative values ``today``/``yesterday``."""

    normalized = value.strip().lower()
    if normalized == "today":
        return today_in_shanghai(now=now)
    if normalized == "yesterday":
        return yesterday_in_shanghai(now=now)
    return date.fromisoformat(value)
