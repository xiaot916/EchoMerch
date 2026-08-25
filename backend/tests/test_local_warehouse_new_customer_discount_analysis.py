import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.core.local_database import LocalDatabase
from app.integrations.local_warehouse.repository import LocalWarehouseAnalyticsRepository
from app.modules.imports.crawl_run_store import CrawlRunStore


def test_new_customer_discount_tracks_daily_status_and_sums_complete_days_only(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "new-customer-discount.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    CrawlRunStore(database_path).ensure_store_reference(
        store_id=1,
        store_name="Store 1",
        platform_store_id="p-1",
    )
    with sqlite3.connect(database_path) as connection:
        connection.executemany(
            '''
            insert into store_daily_new_customer_discount_overviews (
                "店铺ID", "业务日期", "商品新访客数", "新客支付人数",
                "新客支付金额", "新客支付转化率", "店铺新客支付人数",
                "店铺新客支付金额"
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            [
                (1, "2026-08-14", "100", "10", "200", "0.1", "20", "500"),
                (1, "2026-08-15", None, "999", "9999", None, "50", "1000"),
            ],
        )

    analysis = LocalWarehouseAnalyticsRepository(database_path).get_analysis_snapshot(
        date(2026, 8, 14),
        date(2026, 8, 16),
    ).new_customer_discount

    assert [item.record_status for item in analysis.daily_metrics] == [
        "complete",
        "partial",
        "missing",
    ]
    assert analysis.daily_metrics[1].paid_buyers is None
    assert analysis.daily_metrics[1].paid_amount is None
    assert analysis.daily_metrics[2].product_new_visitors is None
    assert analysis.product_new_visitors == 100
    assert analysis.paid_buyers == 10
    assert analysis.paid_amount == Decimal("200")
    assert analysis.conversion_rate == Decimal("0.1")
    assert analysis.shop_paid_buyers == 20
    assert analysis.shop_paid_amount == Decimal("500")
    assert analysis.buyer_share == Decimal("0.5")
    assert analysis.amount_share == Decimal("0.4")
