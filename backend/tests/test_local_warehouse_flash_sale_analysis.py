import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.core.local_database import LocalDatabase
from app.integrations.local_warehouse.repository import LocalWarehouseAnalyticsRepository
from app.modules.imports.crawl_run_store import CrawlRunStore


def test_flash_sale_analysis_excludes_empty_days_and_compares_daily_averages(tmp_path: Path) -> None:
    database_path = tmp_path / "flash-sale-analysis.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    CrawlRunStore(database_path).ensure_store_reference(
        store_id=1,
        store_name="Store 1",
        platform_store_id="p-1",
    )

    with sqlite3.connect(database_path) as connection:
        connection.executemany(
            '''
            insert into store_daily_overviews ("店铺ID", "业务日期", "支付金额")
            values (?, ?, ?)
            ''',
            [
                (1, "2026-08-01", "1000.00"),
                (1, "2026-08-02", "2000.00"),
            ],
        )
        connection.executemany(
            '''
            insert into store_daily_taobao_flash_sale_overviews (
                "店铺ID", "业务日期", "活动中商品量级", "活动商品IPV",
                "活动商品IPVUV", "活动商品成交笔数", "活动商品成交金额",
                "活动商品引导店铺新客", "活动商品最高爆发系数"
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            [
                (1, "2026-07-30", "1", "120", "60", "10", "100.00", "2", "1.25"),
                (1, "2026-07-31", None, None, None, None, None, None, None),
                (1, "2026-08-01", "2", "300", "100", "20", "300.00", "5", "2.50"),
                (1, "2026-08-02", None, None, None, None, None, None, None),
            ],
        )

    analysis = LocalWarehouseAnalyticsRepository(database_path).get_flash_sale_analysis(
        date(2026, 8, 1),
        date(2026, 8, 2),
    )

    assert analysis.latest_available_date == date(2026, 8, 2)
    assert analysis.summary.active_days == 1
    assert analysis.summary.paid_amount == Decimal("300.00")
    assert analysis.summary.paid_order_count == 20
    assert analysis.summary.shop_paid_share == Decimal("0.1")
    assert analysis.previous_summary.active_days == 1
    assert analysis.previous_summary.paid_amount == Decimal("100.00")
    assert analysis.comparison.paid_amount_change_percent == Decimal("200")
    assert analysis.empty_dates == [date(2026, 8, 2)]
    assert analysis.missing_dates == []
    assert [row.record_status for row in analysis.daily_metrics] == ["complete", "empty"]
