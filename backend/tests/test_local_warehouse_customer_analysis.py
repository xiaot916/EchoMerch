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
        connection.execute(
            '''
            insert into store_daily_overviews ("店铺ID", "业务日期", "支付买家数", "支付金额")
            values (?, ?, ?, ?)
            ''',
            (1, "2026-08-18", "20", "400.00"),
        )
        connection.executemany(
            '''
            insert into store_daily_customer_overviews (
                "店铺ID", "业务日期", "店铺客户数", "客户新访", "新访成交",
                "未购客户回访", "回访成交", "已购客户回访", "老客复购",
                "新访支付金额占比", "未购回访支付金额占比", "已购回访支付金额占比"
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            [
                (1, "2026-08-18", "47914", "100", "10", "50", "5", "40", "8", "0.30", "0.20", "0.50"),
                (1, "2026-08-20", None, None, None, None, None, None, None, None, None, None),
            ],
        )

    snapshot = LocalWarehouseAnalyticsRepository(database_path).get_analysis_snapshot(
        date(2026, 8, 18),
        date(2026, 8, 20),
    )

    assert snapshot.customer.shop_customers == 47914
    assert snapshot.customer.shop_customers_stat_date == date(2026, 8, 18)
    assert snapshot.customer.expected_days == 3
    assert snapshot.customer.covered_days == 1
    assert snapshot.customer.first_covered_date == date(2026, 8, 18)
    assert snapshot.customer.latest_covered_date == date(2026, 8, 18)
    assert snapshot.customer.missing_dates == [date(2026, 8, 19), date(2026, 8, 20)]
    assert [row.stat_date for row in snapshot.customer.daily_metrics] == [date(2026, 8, 18)]
    assert [(item.label, item.reached, item.buyers) for item in snapshot.customer.segments] == [
        ("新访", 100, 10),
        ("未购回访", 50, 5),
        ("已购回访", 40, 8),
    ]
    derived = {item.id: item for item in snapshot.customer.derived_metrics}
    assert derived["first_purchase_paid_buyers"].value == 12
    assert derived["first_purchase_paid_amount"].value == 200
    assert derived["first_purchase_amount_share"].value == 50
    assert snapshot.customer.daily_metrics[0].first_purchase_paid_amount == 200
    assert any("仅到 2026-08-18" in warning for warning in snapshot.customer.quality_warnings)


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


def test_customer_analysis_does_not_treat_missing_repeat_amount_ratio_as_zero(tmp_path: Path) -> None:
    database_path = tmp_path / "customer-analysis-partial.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    CrawlRunStore(database_path).ensure_store_reference(
        store_id=1,
        store_name="Store 1",
        platform_store_id="p-1",
    )
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            'insert into store_daily_overviews ("店铺ID", "业务日期", "支付买家数", "支付金额") values (?, ?, ?, ?)',
            (1, "2026-08-20", "20", "400.00"),
        )
        connection.execute(
            '''
            insert into store_daily_customer_overviews (
                "店铺ID", "业务日期", "客户新访", "新访成交", "未购客户回访",
                "回访成交", "已购客户回访", "老客复购", "新访支付金额占比"
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (1, "2026-08-20", "100", "10", "50", "5", "40", "8", "0.30"),
        )

    customer = LocalWarehouseAnalyticsRepository(database_path).get_analysis_snapshot(
        date(2026, 8, 20),
        date(2026, 8, 20),
    ).customer
    derived = {item.id: item for item in customer.derived_metrics}

    assert derived["first_purchase_paid_buyers"].status == "available"
    assert derived["first_purchase_paid_amount"].status == "unavailable"
    assert customer.daily_metrics[0].repeat_paid_amount is None
    assert customer.daily_metrics[0].first_purchase_paid_amount is None
    assert any("老客复购金额占比" in warning for warning in customer.quality_warnings)
