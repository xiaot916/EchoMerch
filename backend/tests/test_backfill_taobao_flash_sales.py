from datetime import date
from pathlib import Path
import sqlite3

from app.core.local_database import LocalDatabase
from scripts.backfill_taobao_flash_sales import _existing_days


def test_existing_days_requires_complete_metrics_or_explicit_no_data(tmp_path: Path) -> None:
    database = LocalDatabase(tmp_path / "flash-sale.sqlite3")
    database.initialize_schema()
    with sqlite3.connect(database.database_path) as connection:
        connection.executemany(
            '''
            insert into store_daily_taobao_flash_sale_overviews (
                "店铺ID", "业务日期", "活动中商品量级", "活动商品IPV",
                "活动商品IPVUV", "活动商品成交笔数", "活动商品成交金额",
                "活动商品引导店铺新客", "活动商品最高爆发系数"
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            [
                (1, "2026-08-18", "2", "2777", "1601", "154", "1806.34", "25", "3.68"),
                (1, "2026-08-19", None, None, None, None, None, None, None),
            ],
        )
        connection.execute(
            '''
            insert into crawl_runs (
                "采集任务ID", "店铺ID", "任务类型", "开始日期", "结束日期",
                "运行模式", "运行状态", "计划天数", "成功天数", "跳过天数", "失败天数",
                "开始时间", "日志文件"
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            ("run-no-data", 1, "taobao_flash_sale", "2026-08-19", "2026-08-19", "backfill", "completed", 1, 1, 0, 0, "2026-08-20T00:00:00", "run.jsonl"),
        )
        connection.execute(
            '''
            insert into crawl_run_days (
                "日期条目ID", "采集任务ID", "店铺ID", "业务日期", "日期状态", "指标数量"
            ) values (?, ?, ?, ?, ?, ?)
            ''',
            (1, "run-no-data", 1, "2026-08-19", "no_data", 0),
        )
        connection.commit()

    assert _existing_days(database.database_path, 1) == {
        date(2026, 8, 18),
        date(2026, 8, 19),
    }
