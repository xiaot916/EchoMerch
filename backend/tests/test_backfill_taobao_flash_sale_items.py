from __future__ import annotations

from datetime import date
from pathlib import Path

from app.core.local_database import LocalDatabase
from app.modules.imports.crawl_run_store import CrawlRunStore
from scripts.backfill_taobao_flash_sale_items import _existing_days, _overview_days


def test_backfill_uses_only_days_present_in_flash_sale_overview(tmp_path: Path) -> None:
    database = LocalDatabase(tmp_path / "flash-sale-items.sqlite3")
    database.initialize_schema()
    runs = CrawlRunStore(database.database_path)
    runs.ensure_store_reference(store_id=1, store_name="Store 1", platform_store_id="p-1")
    import sqlite3
    with sqlite3.connect(database.database_path) as conn:
        conn.executemany(
            'insert into store_daily_taobao_flash_sale_overviews ("店铺ID", "业务日期") values (?, ?)',
            [(1, "2025-05-21"), (1, "2025-05-23"), (2, "2025-05-22")],
        )
        conn.commit()
    assert _overview_days(database, 1, date(2025, 5, 21), date(2025, 5, 23)) == [
        date(2025, 5, 21), date(2025, 5, 23)
    ]


def test_successful_empty_flash_sale_day_is_treated_as_existing(tmp_path: Path) -> None:
    database = LocalDatabase(tmp_path / "flash-sale-items.sqlite3")
    database.initialize_schema()
    runs = CrawlRunStore(database.database_path)
    runs.ensure_store_reference(store_id=1, store_name="Store 1", platform_store_id="p-1")
    run_id = runs.create_run(
        store_id=1,
        task_type="taobao_flash_sale_items",
        start_day=date(2025, 5, 21),
        end_day=date(2025, 5, 21),
        mode="backfill",
        planned_days=1,
        log_file=tmp_path / "run.jsonl",
    )
    runs.record_day(run_id=run_id, store_id=1, business_day=date(2025, 5, 21), status="no_data", metric_count=0)
    assert _existing_days(database, 1) == {date(2025, 5, 21)}
