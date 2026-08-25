import sqlite3
from pathlib import Path

from app.core.local_database import LocalDatabase
from app.modules.imports.crawl_run_store import CrawlRunStore


def test_normalizes_timestamped_live_overview_business_day(tmp_path: Path) -> None:
    database_path = tmp_path / "live.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    CrawlRunStore(database_path).ensure_store_reference(
        store_id=1,
        store_name="Store 1",
        platform_store_id="p-1",
    )
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            'insert into store_daily_live_overviews ("店铺ID", "业务日期") values (?, ?)',
            (1, "2026-08-01T00:00:00"),
        )
        LocalDatabase._normalize_live_overview_business_days(connection)
        assert connection.execute(
            'select "业务日期" from store_daily_live_overviews'
        ).fetchone()[0] == "2026-08-01"
