import json
import sqlite3
from datetime import date
from pathlib import Path

from app.core.local_database import LocalDatabase
from app.warehouse.alimama_crowd import parse_payload
from app.warehouse.store import WarehouseStore


BUSINESS_DAY = date(2026, 8, 19)


def _payload() -> dict[str, object]:
    return {
        "data": {
            "count": 0,
            "list": [
                {
                    "thedate": "2026-08-19",
                    "scene1Name": "关键词推广",
                    "campaignId": 80233540786,
                    "campaignName": "盛夏金装两包",
                    "adgroupId": 80157169533,
                    "adgroupName": "盛夏金装单元",
                    "bpCrowdId": "628000",
                    "crowdName": "店铺长期价值人群",
                    "promotionId": 867250872810,
                    "promotionName": "盛夏金装商品",
                    "subPromotionTypeName": "商品",
                    "adPv": 5998,
                    "click": 241,
                    "ctr": 0.04018,
                    "charge": 296.76,
                    "ecpc": 1.23137,
                    "cartDirNum": 5,
                }
            ],
        },
        "info": {"ok": True},
    }


def test_parses_crowd_dimensions_when_count_is_zero() -> None:
    parsed = parse_payload(_payload(), business_day=BUSINESS_DAY)

    assert len(parsed.rows) == 1
    row = parsed.rows[0]
    assert row.crowd_id == "628000"
    assert row.crowd_name == "店铺长期价值人群"
    assert row.campaign_id == "80233540786"
    assert row.adgroup_id == "80157169533"
    assert row.subject_id == "867250872810"
    assert str(row.metrics[0]) == "5998"
    assert str(row.metrics[3]) == "296.76"


def test_ingestion_keeps_crowd_facts_separate_from_campaign_facts(tmp_path: Path) -> None:
    database_path = tmp_path / "warehouse.sqlite3"
    response_path = tmp_path / "crowd.json"
    response_path.write_text(json.dumps(_payload(), ensure_ascii=False), encoding="utf-8")
    warehouse = WarehouseStore(database_path)

    warehouse.ingest_alimama_crowd_report(
        source_path=response_path,
        business_day=BUSINESS_DAY,
        store_name="Store 1",
        platform_store_id="p-1",
    )

    LocalDatabase(database_path).initialize_schema()
    with sqlite3.connect(database_path) as connection:
        crowd_rows = connection.execute(
            'select "人群名称", "推广计划名称", "推广单元名称", "主体ID", '
            '"展现量", "点击量", "花费" from store_daily_promotion_crowds'
        ).fetchall()
        campaign_count = connection.execute(
            "select count(*) from store_daily_promotion_campaigns"
        ).fetchone()[0]
    assert crowd_rows == [
        ("店铺长期价值人群", "盛夏金装两包", "盛夏金装单元", "867250872810", "5998", "241", "296.76")
    ]
    assert campaign_count == 0
