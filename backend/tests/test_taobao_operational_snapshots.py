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
    TAOBAO_ACTIVITY_ITEM_SNAPSHOT_TABLE,
    TAOBAO_CURRENT_PRICE_ITEM_TABLE,
    TAOBAO_RISK_PRICE_ITEM_TABLE,
)
from app.warehouse.store import WarehouseStore  # noqa: E402
from app.warehouse.taobao_activity_item_snapshots import parse_payload as parse_activity  # noqa: E402
from app.warehouse.taobao_current_price_items import parse_payload as parse_current  # noqa: E402
from app.warehouse.taobao_risk_price_items import parse_payload as parse_risk  # noqa: E402


DAY = date(2026, 8, 21)


def risk_payload(item_id: str = "1") -> dict[str, object]:
    return {"ret": ["SUCCESS::调用成功"], "data": {"model": {"riskDetectRecords": [{
        "gmtModified": "2026-08-21 10:00:00", "itemInfo": {"itemId": item_id, "itemTitle": "纸尿裤"},
        "riskDesc": {"exampleLowPrice": "39.9", "lowPriceSkuNum": 2, "promotionDetails": {"活动": "直降"}, "riskDetectSubDesc": "低价SKU"},
    }]}}}


def current_payload(item_id: str = "1") -> dict[str, object]:
    return {"ret": ["SUCCESS::调用成功"], "data": {"model": {"items": [{
        "itemId": item_id, "itemTitle": "纸尿裤", "attention": True, "riskTag": "低价",
        "lowPrice": "39.90", "lowPriceLowerBound": "39", "lowPriceUpperBound": "45", "skuNum": 3,
    }]}}}


def activity_payload(item_id: str = "1") -> dict[str, object]:
    row = {"itemId": item_id, "itemName": "纸尿裤", "juId": "j1", "status": "1", "statusName": "在线", "activityName": "百补",
           "activityPrice": "39.9", "originalPrice": "59.9", "inventory": 10, "soldCount": 2, "onlineStartTime": 1787260800000}
    return {"snapshots": [{"snapshotType": "bybt_online", "pages": [{"success": True, "data": {"data": [row]}}]},
                           {"snapshotType": "bybt_pending", "pages": [{"success": True, "data": {"data": []}}]},
                           {"snapshotType": "flash_sale_online", "pages": [{"success": True, "data": {"data": []}}]}]}


class TaobaoOperationalSnapshotTests(unittest.TestCase):
    def test_parsers_accept_nested_payloads_and_empty_activity_pages(self) -> None:
        self.assertEqual(parse_risk(risk_payload(), business_day=DAY).rows[0].item_id, "1")
        self.assertEqual(parse_current(current_payload(), business_day=DAY).rows[0].item_id, "1")
        parsed = parse_activity(activity_payload(), business_day=DAY)
        self.assertEqual(len(parsed.rows), 1)
        self.assertEqual(parsed.rows[0].snapshot_type, "bybt_online")

    def test_daily_ingestion_replaces_each_snapshot_table(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {}
            for name, payload in (("risk", risk_payload()), ("current", current_payload()), ("activity", activity_payload())):
                path = root / f"{name}.json"
                path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                files[name] = path
            store = WarehouseStore(root / "warehouse.sqlite3")
            store.ingest_taobao_risk_price_items(files["risk"], DAY, "测试店")
            store.ingest_taobao_current_price_items(files["current"], DAY, "测试店")
            store.ingest_taobao_activity_item_snapshots(files["activity"], DAY, "测试店")
            updated = json.loads(json.dumps(activity_payload("2")))
            (root / "activity.json").write_text(json.dumps(updated, ensure_ascii=False), encoding="utf-8")
            store.ingest_taobao_activity_item_snapshots(root / "activity.json", DAY, "测试店")
            with closing(sqlite3.connect(root / "warehouse.sqlite3")) as conn:
                self.assertEqual(conn.execute(f'select count(*) from "{TAOBAO_RISK_PRICE_ITEM_TABLE}"').fetchone()[0], 1)
                self.assertEqual(conn.execute(f'select count(*) from "{TAOBAO_CURRENT_PRICE_ITEM_TABLE}"').fetchone()[0], 1)
                self.assertEqual(conn.execute(f'select count(*) from "{TAOBAO_ACTIVITY_ITEM_SNAPSHOT_TABLE}"').fetchone()[0], 1)
                self.assertEqual(conn.execute(f'select "商品ID" from "{TAOBAO_ACTIVITY_ITEM_SNAPSHOT_TABLE}"').fetchone()[0], "2")
            emptied = activity_payload()
            for snapshot in emptied["snapshots"]:
                snapshot["pages"][0]["data"]["data"] = []
            (root / "activity.json").write_text(json.dumps(emptied, ensure_ascii=False), encoding="utf-8")
            store.ingest_taobao_activity_item_snapshots(root / "activity.json", DAY, "测试店")
            with closing(sqlite3.connect(root / "warehouse.sqlite3")) as conn:
                self.assertEqual(conn.execute(f'select count(*) from "{TAOBAO_ACTIVITY_ITEM_SNAPSHOT_TABLE}"').fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
