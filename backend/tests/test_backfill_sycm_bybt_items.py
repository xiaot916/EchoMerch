from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from app.core.local_database import LocalDatabase
from app.modules.imports.crawl_run_store import CrawlRunStore
from scripts.backfill_sycm_bybt_items import _existing_days, _overview_days


def test_backfill_uses_every_calendar_day_even_when_bybt_overview_is_missing(tmp_path: Path) -> None:
    database = LocalDatabase(tmp_path / "bybt-items.sqlite3")
    database.initialize_schema()
    with sqlite3.connect(database.database_path) as conn:
        conn.executemany(
            'insert into store_daily_bybt_overviews ("店铺ID", "业务日期") values (?, ?)',
            [(1, "2025-01-01"), (1, "2025-01-03"), (2, "2025-01-02")],
        )
        conn.commit()

    assert _overview_days(database, 1, date(2025, 1, 1), date(2025, 1, 3)) == [
        date(2025, 1, 1),
        date(2025, 1, 2),
        date(2025, 1, 3),
    ]


def test_successful_empty_day_is_treated_as_existing(tmp_path: Path) -> None:
    database = LocalDatabase(tmp_path / "bybt-items.sqlite3")
    database.initialize_schema()
    runs = CrawlRunStore(database.database_path)
    runs.ensure_store_reference(store_id=1, store_name="Store 1", platform_store_id="p-1")
    run_id = runs.create_run(
        store_id=1,
        task_type="sycm_bybt_items",
        start_day=date(2025, 1, 1),
        end_day=date(2025, 1, 1),
        mode="backfill",
        planned_days=1,
        log_file=tmp_path / "run.jsonl",
    )
    runs.record_day(
        run_id=run_id,
        store_id=1,
        business_day=date(2025, 1, 1),
        status="no_data",
        metric_count=0,
    )

    assert _existing_days(database, 1) == {date(2025, 1, 1)}
