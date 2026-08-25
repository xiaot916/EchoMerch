import json
import sqlite3
from datetime import date
from pathlib import Path

from app.core.local_database import LocalDatabase
from app.warehouse.alimama_promotion_detail import (
    load_and_parse_content,
    load_and_parse_item,
)
from app.warehouse.store import WarehouseStore


BUSINESS_DAY = date(2026, 8, 19)


def _item_payload() -> dict[str, object]:
    return {
        "data": {
            "count": 1,
            "list": [
                {
                    "thedate": "2026-08-19",
                    "scene1Name": "货品全站推广",
                    "campaignId": 82728721752,
                    "campaignName": "商品全站推广_955532215509",
                    "promotionId": 955532215509,
                    "promotionName": "盛夏金装试用装",
                    "subPromotionTypeName": "商品",
                    "adPv": 3315,
                    "click": 406,
                    "charge": 35.99,
                    "alipayInshopAmt": 313.75,
                    "alipayInshopUv": 61,
                }
            ],
        },
        "info": {"ok": True},
    }


def _content_payload() -> dict[str, object]:
    return {
        "data": {
            "count": 1,
            "list": [
                {
                    "thedate": "2026-08-19",
                    "scene1Name": "超级短视频",
                    "campaignId": 15036285105,
                    "campaignName": "盛夏金装2包",
                    "promotionId": 573133264506,
                    "promotionName": "更薄更透气短视频",
                    "subPromotionTypeName": "短视频",
                    "adPv": 1,
                    "click": 0,
                    "charge": 0,
                    "alipayInshopAmt": 0,
                }
            ],
        },
        "info": {"ok": True},
    }


def test_parses_item_and_content_subjects(tmp_path: Path) -> None:
    item_path = tmp_path / "item.json"
    content_path = tmp_path / "content.json"
    item_path.write_text(json.dumps(_item_payload(), ensure_ascii=False), encoding="utf-8")
    content_path.write_text(json.dumps(_content_payload(), ensure_ascii=False), encoding="utf-8")

    item = load_and_parse_item(item_path, BUSINESS_DAY).rows[0]
    content = load_and_parse_content(content_path, BUSINESS_DAY).rows[0]

    assert item.subject_id == "955532215509"
    assert item.subject_type == "商品"
    assert str(item.metrics[0]) == "3315"
    assert str(item.metrics[14]) == "313.75"
    assert content.subject_id == "573133264506"
    assert content.subject_type == "短视频"
    assert str(content.metrics[0]) == "1"


def test_ingests_item_and_content_into_separate_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "warehouse.sqlite3"
    item_path = tmp_path / "item.json"
    content_path = tmp_path / "content.json"
    item_path.write_text(json.dumps(_item_payload(), ensure_ascii=False), encoding="utf-8")
    content_path.write_text(json.dumps(_content_payload(), ensure_ascii=False), encoding="utf-8")
    warehouse = WarehouseStore(database_path)

    warehouse.ingest_alimama_promotion_item_report(
        source_path=item_path,
        business_day=BUSINESS_DAY,
        store_name="Store 1",
        platform_store_id="p-1",
    )
    warehouse.ingest_alimama_promotion_content_report(
        source_path=content_path,
        business_day=BUSINESS_DAY,
        store_name="Store 1",
        platform_store_id="p-1",
    )

    LocalDatabase(database_path).initialize_schema()
    with sqlite3.connect(database_path) as connection:
        item = connection.execute(
            'select "商品ID", "商品名称", "推广计划ID", "花费", "总成交金额" '
            'from store_daily_promotion_items'
        ).fetchone()
        content = connection.execute(
            'select "内容ID", "内容名称", "内容类型", "推广计划ID", "展现量" '
            'from store_daily_promotion_contents'
        ).fetchone()
    assert item == ("955532215509", "盛夏金装试用装", "82728721752", "35.99", "313.75")
    assert content == (
        "573133264506",
        "更薄更透气短视频",
        "短视频",
        "15036285105",
        "1",
    )
