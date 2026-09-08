from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

from app.warehouse.store import WarehouseStore


def test_customer_overview_ingestion_keeps_the_customer_metric_namespace(tmp_path: Path) -> None:
    source_path = tmp_path / "customer-overview.json"
    source_path.write_text(
        json.dumps(
            {
                "code": 0,
                "data": {
                    "sellerId": {"value": "2200573698992"},
                    "shopCustomer": {"value": 45000},
                    "newVisitorCnt": {"value": 16000},
                    "newVisitorBuyCnt": {"value": 1300},
                    "newVisitorPayAmtRatio": {"value": 0.25},
                    "noPurchaseCnt": {"value": 9000},
                    "noPurchaseBuyCnt": {"value": 300},
                    "noPurchasePayAmtRatio": {"value": 0.1},
                    "hasPurchaseCnt": {"value": 18000},
                    "hasPurchaseUbyCnt": {"value": 2500},
                    "hasPurchasePayAmtRatio": {"value": 0.65},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    database_path = tmp_path / "customer-overview.sqlite3"

    WarehouseStore(database_path).ingest_sycm_customer_overview(
        source_path,
        date(2026, 8, 19),
        "Store 1",
    )

    with sqlite3.connect(database_path) as conn:
        row = conn.execute(
            '''select "店铺客户数", "客户新访", "新访成交", "新访支付金额占比",
                      "未购客户回访", "回访成交", "未购回访支付金额占比",
                      "已购客户回访", "老客复购", "已购回访支付金额占比"
               from store_daily_customer_overviews
               where "业务日期" = ?''',
            ("2026-08-19",),
        ).fetchone()

    assert row == (
        "45000", "16000", "1300", "0.25", "9000", "300", "0.1", "18000", "2500", "0.65"
    )
