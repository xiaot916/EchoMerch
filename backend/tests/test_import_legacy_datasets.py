from datetime import datetime

from scripts.import_legacy_daily_overviews import _business_day
from scripts.import_legacy_datasets import (
    PRODUCT_DATASET,
    PROMOTION_CAMPAIGN_DATASET,
    TRAFFIC_DATASET,
    _aggregate_traffic_rows,
    map_source_row,
)


def test_maps_product_history_without_inventing_new_metrics() -> None:
    row = map_source_row(
        PRODUCT_DATASET,
        {
            "日期": "2026-08-01",
            "商品ID": 123,
            "商品名称": "测试商品",
            "支付金额": 10.5,
            "支付件数": 2,
        },
    )

    assert row["业务日期"] == "2026-08-01"
    assert row["商品ID"] == "123"
    assert row["支付金额"] == "10.5"
    assert row["支付件数"] == "2"
    assert row["推广消耗"] is None


def test_maps_traffic_source_level_from_populated_hierarchy() -> None:
    row = map_source_row(
        TRAFFIC_DATASET,
        {
            "日期": "2026-08-01",
            "一级来源": "付费推广",
            "二级来源": "关键词推广",
            "三级来源": "品牌词",
            "访客数": 100,
        },
    )

    assert row["业务日期"] == "2026-08-01"
    assert row["来源层级"] == "3"
    assert row["访客数"] == "100"


def test_aggregates_legacy_traffic_rows_and_recalculates_derived_metrics() -> None:
    rows = _aggregate_traffic_rows(
        [
            {
                "业务日期": "2026-08-01",
                "来源层级": "1",
                "一级来源": "手淘推荐",
                "二级来源": "",
                "三级来源": "",
                "访客数": "100",
                "新访客数": "20",
                "加购人数": "4",
                "商品收藏人数": "3",
                "支付买家数": "2",
                "支付金额": "10",
                "下单买家数": "3",
                "下单金额": "12",
            },
            {
                "业务日期": "2026-08-01",
                "来源层级": "1",
                "一级来源": "手淘推荐",
                "二级来源": "",
                "三级来源": "",
                "访客数": "100",
                "新访客数": "5",
                "加购人数": "1",
                "商品收藏人数": "1",
                "支付买家数": "3",
                "支付金额": "20",
                "下单买家数": "4",
                "下单金额": "22",
            },
        ]
    )

    assert len(rows) == 1
    assert rows[0]["访客数"] == "200"
    assert rows[0]["支付金额"] == "30"
    assert rows[0]["支付转化率"] == "0.025"
    assert rows[0]["UV价值"] == "0.15"
    assert rows[0]["支付金额占比"] == "1"


def test_maps_promotion_campaign_dimension_and_metrics() -> None:
    row = map_source_row(
        PROMOTION_CAMPAIGN_DATASET,
        {
            "日期": "2026-08-01",
            "场景名字": "关键词推广",
            "计划ID": 42,
            "计划名字": "核心词计划",
            "花费": 23.4,
            "总成交金额": 80,
        },
    )

    assert row["业务日期"] == "2026-08-01"
    assert row["推广计划ID"] == "42"
    assert row["推广计划名称"] == "核心词计划"
    assert row["花费"] == "23.4"
    assert row["总成交金额"] == "80"


def test_normalizes_mysql_datetime_to_business_day() -> None:
    assert _business_day(datetime(2026, 8, 1, 0, 0, 0)).isoformat() == "2026-08-01"
