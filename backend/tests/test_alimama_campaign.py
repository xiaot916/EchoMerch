import json
import sqlite3
from datetime import date
from pathlib import Path

from app.core.local_database import LocalDatabase
from app.warehouse.alimama_campaign import parse_payload
from app.warehouse.store import WarehouseStore


BUSINESS_DAY = date(2026, 8, 18)


def _payload(*, charge: float = 12.5) -> dict[str, object]:
    return {
        "data": {
            "count": 1,
            "list": [
                {
                    "scene1Name": "关键词推广",
                    "campaignId": 42,
                    "campaignName": "核心计划",
                    "adPv": 100,
                    "click": 5,
                    "charge": charge,
                    "ctr": 0.05,
                    "alipayInshopAmt": 50,
                    "alipayInshopNum": 3,
                    "alipayInshopUv": 2,
                    "roi": 4,
                }
            ],
        },
        "info": {"ok": True},
    }


def test_parses_campaign_dimensions_and_metrics() -> None:
    parsed = parse_payload(_payload(), business_day=BUSINESS_DAY)

    assert parsed.response_code == 0
    assert len(parsed.rows) == 1
    assert parsed.rows[0].scene_name == "关键词推广"
    assert parsed.rows[0].campaign_id == "42"
    assert parsed.rows[0].campaign_name == "核心计划"
    assert str(parsed.rows[0].metrics[0]) == "100"
    assert str(parsed.rows[0].metrics[2]) == "12.5"
    assert str(parsed.rows[0].metrics[14]) == "50"
    assert str(parsed.rows[0].metrics[58]) == "2"


def test_ingestion_replaces_all_campaign_rows_for_the_business_day(tmp_path: Path) -> None:
    database_path = tmp_path / "warehouse.sqlite3"
    response_path = tmp_path / "campaign.json"
    response_path.write_text(json.dumps(_payload(), ensure_ascii=False), encoding="utf-8")
    warehouse = WarehouseStore(database_path)

    first = warehouse.ingest_alimama_campaign_report(
        source_path=response_path,
        business_day=BUSINESS_DAY,
        store_name="Store 1",
        platform_store_id="p-1",
    )
    response_path.write_text(json.dumps(_payload(charge=8), ensure_ascii=False), encoding="utf-8")
    second = warehouse.ingest_alimama_campaign_report(
        source_path=response_path,
        business_day=BUSINESS_DAY,
        store_name="Store 1",
        platform_store_id="p-1",
    )

    assert first.metric_count == second.metric_count
    LocalDatabase(database_path).initialize_schema()
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            'select "推广场景", "推广计划ID", "推广计划名称", "花费", "总成交金额", "成交人数" '
            'from store_daily_promotion_campaigns'
        ).fetchall()
    assert rows == [("关键词推广", "42", "核心计划", "8", "50", "2")]
