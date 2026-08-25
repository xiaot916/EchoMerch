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
    BRAND_ZONE_COLUMNS,
    BRAND_ZONE_PAID_AMOUNT,
)
from app.warehouse.brandsearch_report import (  # noqa: E402
    BrandSearchPayloadError,
    parse_payload,
)
from app.warehouse.store import WarehouseStore  # noqa: E402


BUSINESS_DAY = date(2026, 8, 17)


def brandsearch_payload() -> dict[str, object]:
    row = {
        "thedate": BUSINESS_DAY.isoformat(),
        "impression": 2936,
        "requestCnt": 3639,
        "click": 581,
        "ctr": 0.197888,
        "click_uv": 530,
        "carttotal": 353,
        "transactiontotal": 1151311.0,
        "transactionshippingtotal": 225,
        "cpt_cvr": 0.076634,
        "shopclick": 580,
        "interactclick": 1,
        "shopctr": 0.197547,
        "favshoptotal": 20,
        "favitemtotal": 23,
        "item_view_cnt": 5641,
        "research_impression": 1111,
        "shop_view_cnt": 3661,
        # These values are deliberately not mapped until their source units are confirmed.
        "cost": 0,
        "cpc": 0,
        "cpm": 0,
        "view_time": 203627,
    }
    return {"data": {"rptQueryResp": {"rptDataDaily": [row], "rptDataSum": [row]}}}


class BrandSearchParserTests(unittest.TestCase):
    def test_parser_maps_confirmed_daily_metrics_and_normalizes_cents(self) -> None:
        parsed = parse_payload(brandsearch_payload(), business_day=BUSINESS_DAY)

        self.assertEqual(parsed.metric_count, 17)
        self.assertEqual(parsed.impressions, Decimal("2936"))
        self.assertEqual(parsed.search_requests, Decimal("3639"))
        self.assertEqual(parsed.clicks, Decimal("581"))
        self.assertEqual(parsed.paid_amount, Decimal("11513.11"))
        self.assertEqual(parsed.paid_order_count, Decimal("225"))
        self.assertEqual(parsed.destination_clicks, Decimal("580"))
        self.assertEqual(parsed.shop_page_views, Decimal("3661"))

    def test_parser_rejects_response_without_the_requested_daily_row(self) -> None:
        with self.assertRaises(BrandSearchPayloadError):
            parse_payload(brandsearch_payload(), business_day=date(2026, 8, 16))


class BrandSearchIngestionTests(unittest.TestCase):
    def test_ingestion_writes_one_clean_idempotent_daily_row(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / "warehouse.sqlite3"
            response_path = root / "brandsearch.json"
            response_path.write_text(
                json.dumps(brandsearch_payload(), ensure_ascii=False),
                encoding="utf-8",
            )

            store = WarehouseStore(database_path)
            first_result = store.ingest_brandsearch_report(
                source_path=response_path,
                business_day=BUSINESS_DAY,
                store_name="碧芭宝贝旗舰店",
            )
            second_result = store.ingest_brandsearch_report(
                source_path=response_path,
                business_day=BUSINESS_DAY,
                store_name="碧芭宝贝旗舰店",
            )

            self.assertEqual(first_result.metric_count, 17)
            self.assertEqual(second_result.metric_count, 17)
            self.assertEqual(first_result.store.store_id, 1)

            with closing(sqlite3.connect(database_path)) as conn:
                columns = {
                    row[1]
                    for row in conn.execute(
                        'pragma table_info("store_daily_brand_zone_overviews")'
                    )
                }
                self.assertEqual(columns, set(BRAND_ZONE_COLUMNS))

                row_count = conn.execute(
                    "select count(*) from store_daily_brand_zone_overviews"
                ).fetchone()[0]
                self.assertEqual(row_count, 1)

                paid_amount = conn.execute(
                    f'''
                    select "{BRAND_ZONE_PAID_AMOUNT}"
                    from store_daily_brand_zone_overviews
                    '''
                ).fetchone()[0]
                self.assertEqual(paid_amount, "11513.11")

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
