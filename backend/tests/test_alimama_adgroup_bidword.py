import json
import re
import sqlite3
from datetime import date
from pathlib import Path

from app.core.local_database import (
    BUSINESS_DAY as BUSINESS_DAY_COLUMN,
    PROMOTION_ADGROUP_ID,
    PROMOTION_AUTOMATCH_TYPE,
    PROMOTION_BIDWORD_ID,
    PROMOTION_BIDWORD_PACKAGE_ID,
    PROMOTION_BIDWORD_TABLE,
    PROMOTION_CAMPAIGN_ID,
    STORE_ID,
    q,
)
from app.core.local_database import LocalDatabase
from app.warehouse.alimama_adgroup import parse_payload as parse_adgroup_payload
from app.warehouse.alimama_bidword import parse_payload as parse_bidword_payload
from app.warehouse.store import WarehouseStore


BUSINESS_DAY = date(2026, 8, 19)


def _product(product_id: int = 123) -> list[dict[str, object]]:
    return [
        {
            "promotionId": product_id,
            "promotionName": "测试商品",
            "subPromotionTypeStr": "ITEM",
        }
    ]


def _adgroup_payload() -> dict[str, object]:
    return {
        "data": {
            "count": 1,
            "list": [
                {
                    "thedate": "2026-08-19",
                    "scene1Name": "关键词推广",
                    "campaignId": 10,
                    "campaignName": "测试计划",
                    "adgroupId": 20,
                    "adgroupName": "测试单元",
                    "promotions": _product(),
                    "adPv": 100,
                    "click": 5,
                    "charge": 2.5,
                    "alipayInshopAmt": 20,
                }
            ],
        },
        "info": {"ok": True},
    }


def _bidword_payload() -> dict[str, object]:
    def row(word_id: int, word_type: str, word: str) -> dict[str, object]:
        return {
            "thedate": "2026-08-19",
            "scene1Name": "关键词推广",
            "campaignId": 10,
            "campaignName": "测试计划",
            "adgroupId": 20,
            "adgroupName": "测试单元",
            "bidwordId": word_id,
            "bidwordPkgId": word_id if word_type == "wordPkg" else -999,
            "bidwordPkgName": word if word_type == "wordPkg" else "",
            "originalWord": word,
            "bidWordType": word_type,
            "isAutomatch": 21,
            "promotions": _product(),
            "adPv": 100,
            "click": 5,
            "charge": 2.5,
            "alipayInshopAmt": 20,
        }

    return {
        "pages": [
            {"data": {"count": 0, "list": [row(1, "word", "纸尿裤")]}, "info": {"ok": True}},
            {"data": {"count": 0, "list": [row(1, "wordPkg", "流量智选") ]}, "info": {"ok": True}},
        ]
    }


def _same_id_bidword_package_payload() -> dict[str, object]:
    def row(package_name: str, automatch_type: int) -> dict[str, object]:
        return {
            "thedate": "2026-08-19",
            "scene1Name": "关键词推广",
            "campaignId": 10,
            "campaignName": "测试计划",
            "adgroupId": 20,
            "adgroupName": "测试单元",
            "bidwordId": 3,
            "bidwordPkgId": 3,
            "bidwordPkgName": package_name,
            "originalWord": package_name,
            "bidWordType": "wordPkg",
            "isAutomatch": automatch_type,
            "promotions": _product(),
            "adPv": 100,
        }

    return {
        "data": {
            "count": 2,
            "list": [row("目标优选", 21), row("好词优选", 1)],
        },
        "info": {"ok": True},
    }


def test_parsers_keep_adgroup_and_bidword_dimensions_separate() -> None:
    adgroup = parse_adgroup_payload(_adgroup_payload(), BUSINESS_DAY)
    bidword = parse_bidword_payload(_bidword_payload(), BUSINESS_DAY)

    assert len(adgroup.rows) == 1
    assert adgroup.rows[0].adgroup_id == "20"
    assert adgroup.rows[0].product_id == "123"
    assert len(bidword.rows) == 2
    assert {row.bidword_type for row in bidword.rows} == {"word", "wordPkg"}
    assert len({(row.campaign_id, row.adgroup_id, row.bidword_id, row.bidword_type, row.product_id) for row in bidword.rows}) == 2


def test_bidword_parser_keeps_same_id_packages_with_different_match_types() -> None:
    bidword = parse_bidword_payload(_same_id_bidword_package_payload(), BUSINESS_DAY)

    assert len(bidword.rows) == 2
    assert {
        (row.bidword_package_name, row.automatch_type)
        for row in bidword.rows
    } == {("目标优选", "21"), ("好词优选", "1")}


def test_ingestion_replaces_each_hierarchy_table_without_campaign_rows(tmp_path: Path) -> None:
    database_path = tmp_path / "warehouse.sqlite3"
    adgroup_path = tmp_path / "adgroup.json"
    bidword_path = tmp_path / "bidword.json"
    adgroup_path.write_text(json.dumps(_adgroup_payload(), ensure_ascii=False), encoding="utf-8")
    bidword_path.write_text(json.dumps(_bidword_payload(), ensure_ascii=False), encoding="utf-8")
    warehouse = WarehouseStore(database_path)

    warehouse.ingest_alimama_adgroup_report(adgroup_path, BUSINESS_DAY, "Store 1", "p-1")
    warehouse.ingest_alimama_bidword_report(bidword_path, BUSINESS_DAY, "Store 1", "p-1")
    warehouse.ingest_alimama_bidword_report(bidword_path, BUSINESS_DAY, "Store 1", "p-1")
    LocalDatabase(database_path).initialize_schema(force=True)

    with sqlite3.connect(database_path) as connection:
        adgroup_count = connection.execute("select count(*) from store_daily_promotion_adgroups").fetchone()[0]
        bidword_count = connection.execute("select count(*) from store_daily_promotion_bidwords").fetchone()[0]
        campaign_count = connection.execute("select count(*) from store_daily_promotion_campaigns").fetchone()[0]
    assert adgroup_count == 1
    assert bidword_count == 2
    assert campaign_count == 0


def test_bidword_table_primary_key_includes_package_and_match_type(tmp_path: Path) -> None:
    database_path = tmp_path / "warehouse.sqlite3"
    bidword_path = tmp_path / "bidword.json"
    bidword_path.write_text(
        json.dumps(_same_id_bidword_package_payload(), ensure_ascii=False),
        encoding="utf-8",
    )
    warehouse = WarehouseStore(database_path)

    warehouse.ingest_alimama_bidword_report(bidword_path, BUSINESS_DAY, "Store 1", "p-1")

    with sqlite3.connect(database_path) as connection:
        count = connection.execute(
            "select count(*) from store_daily_promotion_bidwords"
        ).fetchone()[0]
        primary_key_columns = [
            row[1]
            for row in connection.execute(
                'pragma table_info("store_daily_promotion_bidwords")'
            ).fetchall()
            if row[5]
        ]
    assert count == 2
    assert "关键词包ID" in primary_key_columns
    assert "智能匹配类型" in primary_key_columns


def test_initialize_schema_migrates_legacy_bidword_primary_key(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy-warehouse.sqlite3"
    bidword_path = tmp_path / "bidword.json"
    bidword_path.write_text(
        json.dumps(_same_id_bidword_package_payload(), ensure_ascii=False),
        encoding="utf-8",
    )
    warehouse = WarehouseStore(database_path)
    warehouse.ingest_alimama_bidword_report(bidword_path, BUSINESS_DAY, "Store 1", "p-1")

    with sqlite3.connect(database_path) as connection:
        table_sql = connection.execute(
            f"select sql from sqlite_master where type='table' and name='{PROMOTION_BIDWORD_TABLE}'"
        ).fetchone()[0]
        rows = connection.execute(
            f'select * from "{PROMOTION_BIDWORD_TABLE}"'
        ).fetchall()
        connection.execute(f'drop table "{PROMOTION_BIDWORD_TABLE}"')
        legacy_primary_key = "primary key(" + ", ".join(
            q(column)
            for column in (
                STORE_ID,
                BUSINESS_DAY_COLUMN,
                PROMOTION_CAMPAIGN_ID,
                PROMOTION_ADGROUP_ID,
                PROMOTION_BIDWORD_ID,
                PROMOTION_BIDWORD_PACKAGE_ID,
                "商品ID",
            )
        ) + ")"
        legacy_sql = re.sub(
            r"primary key\s*\([^)]*\)",
            legacy_primary_key,
            table_sql,
            count=1,
            flags=re.IGNORECASE,
        )
        connection.execute(legacy_sql)
        placeholders = ", ".join("?" for _ in rows[0])
        connection.executemany(
            f'insert into "{PROMOTION_BIDWORD_TABLE}" values ({placeholders})',
            rows[:1],
        )
        connection.commit()

    LocalDatabase(database_path).initialize_schema(force=True)

    with sqlite3.connect(database_path) as connection:
        count = connection.execute(
            f'select count(*) from "{PROMOTION_BIDWORD_TABLE}"'
        ).fetchone()[0]
        primary_key_columns = [
            row[1]
            for row in connection.execute(
                f'pragma table_info("{PROMOTION_BIDWORD_TABLE}")'
            ).fetchall()
            if row[5]
        ]
    assert count == 1
    assert PROMOTION_BIDWORD_PACKAGE_ID in primary_key_columns
    assert PROMOTION_AUTOMATCH_TYPE in primary_key_columns

    warehouse.ingest_alimama_bidword_report(bidword_path, BUSINESS_DAY, "Store 1", "p-1")
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            f'select count(*) from "{PROMOTION_BIDWORD_TABLE}"'
        ).fetchone()[0] == 2
