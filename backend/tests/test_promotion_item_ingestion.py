from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.local_database import (  # noqa: E402
    BYBT_ITEM_COLUMNS,
    BYBT_ITEM_TABLE,
    TAOBAO_FLASH_SALE_ITEM_COLUMNS,
    TAOBAO_FLASH_SALE_ITEM_TABLE,
)
from app.warehouse.store import WarehouseStore  # noqa: E402
from app.warehouse.sycm_bybt import SycmBybtPayloadError, parse_payload as parse_bybt_overview  # noqa: E402
from app.warehouse.sycm_bybt_items import parse_payload as parse_bybt_items  # noqa: E402
from app.warehouse.taobao_flash_sale_items import parse_payload as parse_flash_items  # noqa: E402


DAY = date(2026, 8, 1)


def bybt_payload() -> dict[str, object]:
    return {
        "code": 0,
        "data": {
            "recordCount": 1,
            "data": [{
                "itemId": {"value": "123"}, "item": {"title": "百补纸尿裤"},
                "juId": "bybt-1", "bybtCateFullName": "母婴/尿裤",
                "businessScenario": "日常", "salesMethod": "自营", "raceType": "母婴", "playType": "直降",
                "bybtPayAmt": {"value": "130.705"}, "bybtPayOrdQty": {"value": "5"},
                "bybtPayOrdCntNew": {"value": "4"}, "bybtItemUv": {"value": "62"}, "bybtCvr": {"value": "0.08"},
            }],
        },
    }


def flash_payload() -> dict[str, object]:
    return {
        "success": True,
        "data": {"data": {"content": [], "list": [{
            "itemId": "456", "activityId": "flash-1", "itemTitle": "秒杀湿巾", "activityName": "限时秒杀",
            "activityStatus": "进行中", "startTime": "2026-08-01 00:00:00", "endTime": "2026-08-01 23:59:59",
            "ipv": 138, "ipvUv": 62, "payOrdCnt": 28, "payOrdAmt": 130.70000000000007,
            "newDac": 4, "payOrdCntRate": 0.4516,
        }], "pageIndex": 1, "pageSize": 50, "total": 1}},
    }


class PromotionItemParserTests(unittest.TestCase):
    def test_empty_bybt_overview_is_rejected_as_incomplete(self) -> None:
        with self.assertRaisesRegex(SycmBybtPayloadError, "incomplete"):
            parse_bybt_overview(
                {"code": 0, "data": {"bybtOnlineItemCnt": {"value": "12"}}},
                business_day=DAY,
            )

    def test_parses_bybt_product_rows(self) -> None:
        parsed = parse_bybt_items(bybt_payload(), business_day=DAY)
        self.assertEqual(len(parsed.rows), 1)
        self.assertEqual(parsed.rows[0].item_id, "123")
        self.assertEqual(str(parsed.rows[0].paid_amount), "130.71")
        self.assertEqual(parsed.metric_count, 5)

    def test_parses_flash_sale_product_rows(self) -> None:
        parsed = parse_flash_items(flash_payload(), business_day=DAY)
        self.assertEqual(len(parsed.rows), 1)
        self.assertEqual(parsed.rows[0].activity_id, "flash-1")
        self.assertEqual(parsed.rows[0].item_name, "秒杀湿巾")
        self.assertEqual(str(parsed.rows[0].paid_amount), "130.70")
        self.assertEqual(str(parsed.rows[0].conversion_rate), "0.4516")
        self.assertEqual(parsed.metric_count, 6)

    def test_empty_dimension_objects_remain_empty_text(self) -> None:
        payload = bybt_payload()
        row = payload["data"]["data"][0]  # type: ignore[index]
        row["salesMethod"] = {}  # type: ignore[index]
        parsed = parse_bybt_items(payload, business_day=DAY)
        self.assertEqual(parsed.rows[0].sales_method, "")


class PromotionItemIngestionTests(unittest.TestCase):
    def test_product_snapshots_are_created_and_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bybt_path = root / "bybt.json"; bybt_path.write_text(json.dumps(bybt_payload(), ensure_ascii=False), encoding="utf-8")
            flash_path = root / "flash.json"; flash_path.write_text(json.dumps(flash_payload(), ensure_ascii=False), encoding="utf-8")
            store = WarehouseStore(root / "warehouse.sqlite3")
            bybt_result = store.ingest_sycm_bybt_items(bybt_path, DAY, "碧芭宝贝旗舰店")
            flash_result = store.ingest_taobao_flash_sale_items(flash_path, DAY, "碧芭宝贝旗舰店")
            self.assertEqual((bybt_result.metric_count, flash_result.metric_count), (5, 6))
            with closing(sqlite3.connect(root / "warehouse.sqlite3")) as conn:
                bybt_columns = {row[1] for row in conn.execute(f'pragma table_info("{BYBT_ITEM_TABLE}")')}
                flash_columns = {row[1] for row in conn.execute(f'pragma table_info("{TAOBAO_FLASH_SALE_ITEM_TABLE}")')}
                self.assertEqual(bybt_columns, set(BYBT_ITEM_COLUMNS))
                self.assertEqual(flash_columns, set(TAOBAO_FLASH_SALE_ITEM_COLUMNS))
                self.assertEqual(conn.execute(f'select count(*) from "{BYBT_ITEM_TABLE}"').fetchone()[0], 1)
                self.assertEqual(conn.execute(f'select count(*) from "{TAOBAO_FLASH_SALE_ITEM_TABLE}"').fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
