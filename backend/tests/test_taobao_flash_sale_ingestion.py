from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import date
from decimal import Decimal
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.local_database import (  # noqa: E402
    TAOBAO_FLASH_SALE_COLUMNS,
    TAOBAO_FLASH_SALE_PAID_ORDER_AMOUNT,
)
from app.warehouse.store import WarehouseStore  # noqa: E402
from app.warehouse.taobao_flash_sale import (  # noqa: E402
    parse_payload as parse_flash_sale,
)


BUSINESS_DAY = date(2026, 8, 1)


def flash_sale_payload() -> dict[str, object]:
    return {
        "data": {
            "data": [
                {
                    "detailList": [{"ds": "20260801", "value": 1}],
                    "level": "-",
                    "qoq": 0,
                    "type": "itemCnt",
                    "value": 1,
                },
                {
                    "detailList": [{"ds": "20260801", "value": 138}],
                    "level": "低于同行商家平均水平",
                    "qoq": 21.05,
                    "type": "ipv",
                    "value": 138,
                },
                {
                    "detailList": [{"ds": "20260801", "value": 62}],
                    "level": "低于同行商家平均水平",
                    "qoq": 16.98,
                    "type": "ipvUv",
                    "value": 62,
                },
                {
                    "detailList": [{"ds": "20260801", "value": 28}],
                    "level": "低于同行商家平均水平",
                    "qoq": 27.27,
                    "type": "payOrderCnt",
                    "value": 28,
                },
                {
                    "detailList": [{"ds": "20260801", "value": 130.70000000000007}],
                    "level": "低于同行商家平均水平",
                    "qoq": 26.04,
                    "type": "payOrderAmt",
                    "value": 130.70000000000007,
                },
                {
                    "detailList": [{"ds": "20260801", "value": 4}],
                    "level": "-",
                    "qoq": 100,
                    "type": "newDac",
                    "value": 4,
                },
                {
                    "detailList": [
                        {"ds": "20260731", "value": 0.1},
                        {"ds": "20260801", "value": 0.25950890707751567},
                    ],
                    "level": "-",
                    "qoq": 52.07,
                    "type": "payOrderCntCoef",
                    "value": 0.25950890707751567,
                },
            ]
        },
        "success": True,
    }


class TaobaoFlashSaleParserTests(unittest.TestCase):
    def test_parser_maps_metric_types_to_daily_values(self) -> None:
        parsed = parse_flash_sale(
            flash_sale_payload(),
            business_day=BUSINESS_DAY,
        )

        self.assertEqual(parsed.metric_count, 7)
        self.assertEqual(parsed.metrics["itemCnt"], Decimal("1"))
        self.assertEqual(parsed.metrics["ipv"], Decimal("138"))
        self.assertEqual(parsed.metrics["ipvUv"], Decimal("62"))
        self.assertEqual(parsed.metrics["payOrderCnt"], Decimal("28"))
        self.assertEqual(parsed.metrics["payOrderAmt"], Decimal("130.70"))
        self.assertEqual(parsed.metrics["newDac"], Decimal("4"))
        self.assertEqual(
            parsed.metrics["payOrderCntCoef"],
            Decimal("0.25950890707751567"),
        )

    def test_login_redirect_response_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parse_flash_sale(
                {"success": False, "message": "请重新登录"},
                business_day=BUSINESS_DAY,
            )

    def test_successful_empty_response_is_stored_as_no_activity(self) -> None:
        parsed = parse_flash_sale(
            {"data": {"data": []}, "success": True},
            business_day=BUSINESS_DAY,
        )

        self.assertEqual(parsed.metric_count, 0)
        self.assertTrue(all(value is None for value in parsed.metrics.values()))


class TaobaoFlashSaleIngestionTests(unittest.TestCase):
    def test_ingestion_writes_clean_daily_table(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / "warehouse.sqlite3"
            response_path = root / "flash-sale.json"
            response_path.write_text(
                json.dumps(flash_sale_payload(), ensure_ascii=False),
                encoding="utf-8",
            )

            store = WarehouseStore(database_path)
            result = store.ingest_taobao_flash_sale(
                source_path=response_path,
                business_day=BUSINESS_DAY,
                store_name="碧芭宝贝旗舰店",
            )

            self.assertEqual(result.metric_count, 7)
            self.assertEqual(result.store.store_id, 1)

            with closing(sqlite3.connect(database_path)) as conn:
                columns = {
                    row[1]
                    for row in conn.execute(
                        'pragma table_info("store_daily_taobao_flash_sale_overviews")'
                    )
                }
                self.assertEqual(columns, set(TAOBAO_FLASH_SALE_COLUMNS))

                amount = conn.execute(
                    f"""
                    select "{TAOBAO_FLASH_SALE_PAID_ORDER_AMOUNT}"
                    from store_daily_taobao_flash_sale_overviews
                    """
                ).fetchone()[0]
                self.assertEqual(amount, "130.70")

                raw_table = conn.execute(
                    """
                    select 1
                    from sqlite_master
                    where type = 'table' and name = 'raw_response_artifacts'
                    """
                ).fetchone()
                self.assertIsNone(raw_table)


if __name__ == "__main__":
    unittest.main()
