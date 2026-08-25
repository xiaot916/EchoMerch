from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from app.core.local_database import LocalDatabase
from scripts.backfill_sycm_new_customer_discount import _existing_days


def test_existing_days_only_contains_complete_activity_rows(tmp_path: Path) -> None:
    database = LocalDatabase(tmp_path / "new-customer-backfill.sqlite3")
    database.initialize_schema()
    with sqlite3.connect(database.database_path) as connection:
        connection.executemany(
            '''
            insert into store_daily_new_customer_discount_overviews (
                "店铺ID", "业务日期", "商品新访客数", "新客支付人数",
                "新客支付金额", "新客支付转化率", "店铺新客支付人数",
                "店铺新客支付金额"
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            [
                (1, "2026-08-19", "6965", "747", "22083.28", "0.107", "1697", "47072.76"),
                (1, "2026-08-20", None, None, None, None, "1251", "26684.36"),
            ],
        )
        connection.commit()

    assert _existing_days(database, 1) == {date(2026, 8, 19)}
