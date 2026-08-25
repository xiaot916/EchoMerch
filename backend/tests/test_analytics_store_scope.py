import sqlite3
from datetime import date
from pathlib import Path

import pytest

from app.core.local_database import LocalDatabase
from app.modules.imports.crawl_run_store import CrawlRunStore
from app.warehouse.store import WarehouseDataNotAvailable, WarehouseStore


def test_daily_overview_date_bounds_are_scoped_to_store(tmp_path: Path) -> None:
    database_path = tmp_path / "analytics.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    ledger = CrawlRunStore(database_path)
    ledger.ensure_store_reference(store_id=1, store_name="Store 1", platform_store_id="p-1")
    ledger.ensure_store_reference(store_id=2, store_name="Store 2", platform_store_id="p-2")

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            'insert into store_daily_overviews ("店铺ID", "业务日期") values (?, ?)',
            (1, "2026-08-01"),
        )
        connection.execute(
            'insert into store_daily_overviews ("店铺ID", "业务日期") values (?, ?)',
            (2, "2026-08-03"),
        )

    warehouse = WarehouseStore(database_path)
    assert warehouse.get_date_bounds(store_id=1) == (date(2026, 8, 1), date(2026, 8, 1))
    assert warehouse.get_date_bounds(store_id=2) == (date(2026, 8, 3), date(2026, 8, 3))
    with pytest.raises(WarehouseDataNotAvailable):
        warehouse.get_date_bounds(store_id=999)
