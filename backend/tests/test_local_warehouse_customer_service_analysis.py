import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.core.local_database import LocalDatabase
from app.integrations.local_warehouse.repository import LocalWarehouseAnalyticsRepository
from app.modules.imports.crawl_run_store import CrawlRunStore


def test_customer_service_snapshot_keeps_service_and_account_grains_separate(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "customer-service.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    CrawlRunStore(database_path).ensure_store_reference(
        store_id=1,
        store_name="Store 1",
        platform_store_id="p-1",
    )
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            '''
            insert into store_daily_customer_service_overviews (
                "店铺ID", "业务日期", "客服销售额", "客服销售人数", "客服销售占比",
                "成功退款金额", "净销售额", "咨询人数", "接待人数",
                "平均响应时长（秒）", "客户满意率"
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (1, "2026-08-01", "100", "10", "0.2", "15", "85", "40", "32", "20", "0.95"),
        )
        connection.executemany(
            '''
            insert into store_daily_customer_service_accounts (
                "店铺ID", "业务日期", "旺旺昵称", "咨询人数", "有效接待人数",
                "销售人数", "销售额", "净销售额"
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            [
                (1, "2026-08-01", "A", "20", "18", "6", "60", "52"),
                (1, "2026-08-01", "B", "12", "8", "4", "40", "33"),
            ],
        )

    snapshot = LocalWarehouseAnalyticsRepository(database_path).get_analysis_snapshot(
        date(2026, 8, 1),
        date(2026, 8, 1),
    )

    assert snapshot.customer_service.sales_amount == Decimal("100")
    assert snapshot.customer_service.reception_rate == Decimal("0.8")
    assert snapshot.customer_service.sales_conversion_rate == Decimal("0.25")
    assert snapshot.customer_service_daily[0].avg_reply_seconds == Decimal("20")
    assert [account.account_name for account in snapshot.customer_service_accounts] == ["A", "B"]
    assert snapshot.customer_service_accounts[0].reception_rate == Decimal("0.9")
    assert snapshot.customer_service_accounts[0].sales_conversion_rate == Decimal("0.3")
