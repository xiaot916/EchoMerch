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
    CPS_COLUMNS,
    CPS_PAYMENT_AMOUNT,
)
from app.warehouse.cps_overview import CpsPayloadError, parse_payload  # noqa: E402
from app.warehouse.store import WarehouseStore  # noqa: E402


BUSINESS_DAY = date(2026, 8, 17)


def cps_payload() -> dict[str, object]:
    return {
        "success": True,
        "resultCode": 200,
        "bizErrorCode": 0,
        "data": {
            "result": [{
                "pay_ord_cfee_8": "43.20",
                "pay_ord_sfee_8": "3.45",
                "pay_ord_cfee_rt_8": "0.0325",
                "pay_ser_ord_sfee_rt_8": "0.0026",
                "pay_ord_num_8": 88,
                "pay_ord_amt_8": "1329.84",
                "uclk_uv_8": 516,
                "sett_ord_total_fee_8": "35.86",
                "sett_ord_num_8": 69,
                "sett_ord_amt_8": "1104.66",
                "dep_ord_num_8": 2,
                "dep_ord_dep_amt_8": "31.00",
                "dep_ord_rest_amt_8": "170.00",
                "dep_ord_total_amt_8": "201.00",
                "pay_bmkt_fee_8": "1.50",
                "sett_bmkt_fee_8": "0.80",
            }]
        },
    }


class CpsOverviewParserTests(unittest.TestCase):
    def test_parser_maps_daily_metrics_without_guessing_units(self) -> None:
        parsed = parse_payload(cps_payload(), business_day=BUSINESS_DAY)

        self.assertEqual(parsed.metric_count, 16)
        self.assertEqual(parsed.response_code, 200)
        self.assertEqual(parsed.payment_amount, Decimal("1329.84"))
        self.assertEqual(parsed.payment_commission_rate, Decimal("0.0325"))
        self.assertEqual(parsed.click_visitors, Decimal("516"))
        self.assertEqual(parsed.preorder_total_amount, Decimal("201.00"))

    def test_parser_rejects_a_response_without_result_metrics(self) -> None:
        with self.assertRaises(CpsPayloadError):
            parse_payload({"code": 0, "data": {}}, business_day=BUSINESS_DAY)


class CpsOverviewIngestionTests(unittest.TestCase):
    def test_ingestion_writes_one_clean_idempotent_daily_row(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / "warehouse.sqlite3"
            response_path = root / "cps.json"
            response_path.write_text(
                json.dumps(cps_payload(), ensure_ascii=False),
                encoding="utf-8",
            )

            store = WarehouseStore(database_path)
            first_result = store.ingest_cps_overview(
                source_path=response_path,
                business_day=BUSINESS_DAY,
                store_name="碧芭宝贝旗舰店",
            )
            second_result = store.ingest_cps_overview(
                source_path=response_path,
                business_day=BUSINESS_DAY,
                store_name="碧芭宝贝旗舰店",
            )

            self.assertEqual(first_result.metric_count, 16)
            self.assertEqual(second_result.metric_count, 16)
            with closing(sqlite3.connect(database_path)) as conn:
                columns = {
                    row[1]
                    for row in conn.execute(
                        'pragma table_info("store_daily_cps_overviews")'
                    )
                }
                self.assertEqual(columns, set(CPS_COLUMNS))

                row_count = conn.execute(
                    "select count(*) from store_daily_cps_overviews"
                ).fetchone()[0]
                self.assertEqual(row_count, 1)

                payment_amount = conn.execute(
                    f'''
                    select "{CPS_PAYMENT_AMOUNT}"
                    from store_daily_cps_overviews
                    '''
                ).fetchone()[0]
                self.assertEqual(payment_amount, "1329.84")

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
