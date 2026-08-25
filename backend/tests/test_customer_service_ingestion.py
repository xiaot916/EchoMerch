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
    CUSTOMER_SERVICE_ACCOUNT_COLUMNS,
    CUSTOMER_SERVICE_AVG_REPLY_SECONDS,
    CUSTOMER_SERVICE_CONSULT_PAY_RATE,
    CUSTOMER_SERVICE_GMV,
    CUSTOMER_SERVICE_OVERVIEW_COLUMNS,
)
from app.warehouse.mtop_customer_service_overview import (  # noqa: E402
    parse_payload as parse_customer_service_overview,
)
from app.warehouse.store import WarehouseStore  # noqa: E402
from app.warehouse.sycm_customer_service_accounts import (  # noqa: E402
    parse_payload as parse_customer_service_accounts,
)


BUSINESS_DAY = date(2026, 8, 1)


def overview_payload() -> dict[str, object]:
    values = {
        "customerServiceGmv": "8488.65",
        "customerServiceSaleCnt": "102",
        "customerServiceSaleRatio": "0.1346",
        "customerServiceSalePrice": "83.22",
        "sucRefundAmount": "2311.75",
        "netPayAmt": "6176.90",
        "consultUserCnt": "436",
        "customerServiceRecUserCnt": "424",
        "wwConsultPayRate": "-",
        "avgReplyInterval": "23.12",
        "customerAllSateRate": "0.8667",
        "wwUserReplayRate": "1",
        "jtkCaseEndAvgDur": "0.23",
        "thtkCaseEndAvgDur": "47.06",
        "pltfHelpRate": "0.0007",
        "pltfRespRate": "0.0002",
    }
    return {
        "ret": ["SUCCESS::调用成功"],
        "data": {
            "model": {
                "result": {
                    "content": {
                        "sellerId": {"value": "2200573698992"},
                        "statDate": {"value": "2026-08-01"},
                        **{
                            code: {"value": value}
                            for code, value in values.items()
                        },
                    }
                }
            }
        },
    }


def accounts_payload(nicknames: tuple[str, ...] = ("客服甲", "客服乙")) -> dict[str, object]:
    rows = [
        {
            "nick": "汇总值",
            "validReplyUv1d": "999",
            "payAmt1d": "99999",
        }
    ]
    for index, nickname in enumerate(nicknames, start=1):
        rows.append(
            {
                "accountNick": nickname,
                "cstUv1d": str(100 + index),
                "validReplyUv1d": str(90 + index),
                "cstOrdUv1d": str(50 + index),
                "ordCrtUv1d": str(30 + index),
                "crtAmt1d": str(1000 + index),
                "payUsrCnt1d": str(20 + index),
                "payAmt1d": str(800 + index),
                "payItmCnt1d": str(40 + index),
                "payOrdCnt1d": str(25 + index),
                "proportionCss": f"0.{index}",
                "sucRefundAmt": str(50 + index),
                "netPayAmt": str(750 + index),
            }
        )
    return {
        "code": 0,
        "success": True,
        "data": {
            "sellerId": "2200573698992",
            "records": rows,
        },
    }


class CustomerServiceParserTests(unittest.TestCase):
    def test_overview_parser_supports_nested_mtop_metrics(self) -> None:
        parsed = parse_customer_service_overview(
            overview_payload(),
            business_day=BUSINESS_DAY,
        )

        self.assertEqual(parsed.platform_store_id, "2200573698992")
        self.assertEqual(parsed.metrics["customerServiceGmv"], Decimal("8488.65"))
        self.assertIsNone(parsed.metrics["wwConsultPayRate"])
        self.assertEqual(parsed.metrics["thtkCaseEndAvgDur"], Decimal("47.06"))
        self.assertEqual(parsed.metric_count, 15)

    def test_account_parser_skips_summary_rows(self) -> None:
        parsed = parse_customer_service_accounts(
            accounts_payload(),
            business_day=BUSINESS_DAY,
        )

        self.assertEqual([row.nickname for row in parsed.rows], ["客服甲", "客服乙"])
        self.assertEqual(parsed.rows[0].valid_reception_users, Decimal("91"))
        self.assertEqual(parsed.rows[1].net_sale_amount, Decimal("752"))

    def test_expired_responses_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parse_customer_service_overview(
                {"ret": ["FAIL_SYS_SESSION_EXPIRED::SESSION_EXPIRED"]},
                business_day=BUSINESS_DAY,
            )
        with self.assertRaises(ValueError):
            parse_customer_service_accounts(
                {"code": 5810, "msg": "You must login system first."},
                business_day=BUSINESS_DAY,
            )


class CustomerServiceIngestionTests(unittest.TestCase):
    def test_ingestion_uses_clean_chinese_business_tables(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / "warehouse.sqlite3"
            overview_path = root / "overview.jsonp"
            accounts_path = root / "accounts.json"
            overview_path.write_text(
                "mtopjsonp32("
                + json.dumps(overview_payload(), ensure_ascii=False)
                + ")",
                encoding="utf-8",
            )
            accounts_path.write_text(
                json.dumps(accounts_payload(), ensure_ascii=False),
                encoding="utf-8",
            )

            store = WarehouseStore(database_path)
            overview_result = store.ingest_mtop_customer_service_overview(
                source_path=overview_path,
                business_day=BUSINESS_DAY,
                store_name="碧芭宝贝旗舰店",
            )
            account_result = store.ingest_sycm_customer_service_accounts(
                source_path=accounts_path,
                business_day=BUSINESS_DAY,
                store_name="碧芭宝贝旗舰店",
            )

            self.assertEqual(overview_result.store.store_id, 1)
            self.assertEqual(account_result.metric_count, 2)

            with closing(sqlite3.connect(database_path)) as conn:
                overview_columns = {
                    row[1]
                    for row in conn.execute(
                        'pragma table_info("store_daily_customer_service_overviews")'
                    )
                }
                account_columns = {
                    row[1]
                    for row in conn.execute(
                        'pragma table_info("store_daily_customer_service_accounts")'
                    )
                }
                self.assertEqual(overview_columns, set(CUSTOMER_SERVICE_OVERVIEW_COLUMNS))
                self.assertEqual(account_columns, set(CUSTOMER_SERVICE_ACCOUNT_COLUMNS))

                overview_row = conn.execute(
                    f"""
                    select "{CUSTOMER_SERVICE_GMV}",
                           "{CUSTOMER_SERVICE_CONSULT_PAY_RATE}",
                           "{CUSTOMER_SERVICE_AVG_REPLY_SECONDS}"
                    from store_daily_customer_service_overviews
                    """
                ).fetchone()
                self.assertEqual(overview_row, ("8488.65", None, "23.12"))

                account_count = conn.execute(
                    "select count(*) from store_daily_customer_service_accounts"
                ).fetchone()[0]
                self.assertEqual(account_count, 2)

            replacement_path = root / "accounts-replacement.json"
            replacement_path.write_text(
                json.dumps(accounts_payload(("客服甲",)), ensure_ascii=False),
                encoding="utf-8",
            )
            store.ingest_sycm_customer_service_accounts(
                source_path=replacement_path,
                business_day=BUSINESS_DAY,
                store_name="碧芭宝贝旗舰店",
            )
            with closing(sqlite3.connect(database_path)) as conn:
                nicknames = [
                    row[0]
                    for row in conn.execute(
                        """
                        select "旺旺昵称"
                        from store_daily_customer_service_accounts
                        order by "旺旺昵称"
                        """
                    )
                ]
            self.assertEqual(nicknames, ["客服甲"])


if __name__ == "__main__":
    unittest.main()
