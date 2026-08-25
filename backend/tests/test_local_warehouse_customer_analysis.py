import sqlite3
from datetime import date
from pathlib import Path

from app.core.local_database import LocalDatabase
from app.integrations.local_warehouse.repository import LocalWarehouseAnalyticsRepository
from app.modules.imports.crawl_run_store import CrawlRunStore


def test_customer_analysis_uses_latest_non_empty_shop_customer_value(tmp_path: Path) -> None:
    database_path = tmp_path / "customer-analysis.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    CrawlRunStore(database_path).ensure_store_reference(
        store_id=1,
        store_name="Store 1",
        platform_store_id="p-1",
    )
    with sqlite3.connect(database_path) as connection:
        connection.executemany(
            '''
            insert into store_daily_customer_overviews (
                "店铺ID", "业务日期", "店铺客户数", "客户新访", "新访成交",
                "未购客户回访", "回访成交", "已购客户回访", "老客复购"
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            [
                (1, "2026-08-18", "47914", "100", "10", "50", "5", "40", "8"),
                (1, "2026-08-20", None, None, None, None, None, None, None),
            ],
        )

    snapshot = LocalWarehouseAnalyticsRepository(database_path).get_analysis_snapshot(
        date(2026, 8, 18),
        date(2026, 8, 20),
    )

    assert snapshot.customer.shop_customers == 47914
    assert snapshot.customer.shop_customers_stat_date == date(2026, 8, 18)
    assert [row.stat_date for row in snapshot.customer.daily_metrics] == [date(2026, 8, 18)]
    assert [(item.label, item.reached, item.buyers) for item in snapshot.customer.segments] == [
        ("新访", 100, 10),
        ("未购回访", 50, 5),
        ("已购回访", 40, 8),
    ]


def test_customer_analysis_keeps_missing_shop_customer_value_null(tmp_path: Path) -> None:
    database_path = tmp_path / "customer-analysis-missing.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    CrawlRunStore(database_path).ensure_store_reference(
        store_id=1,
        store_name="Store 1",
        platform_store_id="p-1",
    )
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            '''
            insert into store_daily_customer_overviews ("店铺ID", "业务日期", "店铺客户数")
            values (?, ?, ?)
            ''',
            (1, "2026-08-20", None),
        )

    snapshot = LocalWarehouseAnalyticsRepository(database_path).get_analysis_snapshot(
        date(2026, 8, 20),
        date(2026, 8, 20),
    )

    assert snapshot.customer.shop_customers is None
    assert snapshot.customer.shop_customers_stat_date is None
