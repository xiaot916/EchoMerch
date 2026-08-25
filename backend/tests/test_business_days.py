from datetime import datetime, timezone

from app.core.business_days import (
    parse_business_day,
    today_in_shanghai,
    yesterday_in_shanghai,
)


def test_shanghai_day_rollover_is_used_for_daily_jobs() -> None:
    before_midnight_utc = datetime(2026, 8, 20, 15, 59, tzinfo=timezone.utc)
    after_midnight_utc = datetime(2026, 8, 20, 16, 1, tzinfo=timezone.utc)

    assert today_in_shanghai(now=before_midnight_utc).isoformat() == "2026-08-20"
    assert today_in_shanghai(now=after_midnight_utc).isoformat() == "2026-08-21"
    assert yesterday_in_shanghai(now=after_midnight_utc).isoformat() == "2026-08-20"


def test_relative_and_iso_business_days_are_supported() -> None:
    now = datetime(2026, 8, 20, 16, 1, tzinfo=timezone.utc)

    assert parse_business_day("yesterday", now=now).isoformat() == "2026-08-20"
    assert parse_business_day("today", now=now).isoformat() == "2026-08-21"
    assert parse_business_day("2026-08-01", now=now).isoformat() == "2026-08-01"
