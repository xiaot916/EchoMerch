from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.warehouse.utry_overviews import parse_repurchase_payload, parse_sample_payload


def _payload(labels: list[str], values: list[list[object]]) -> dict[str, object]:
    return {
        "code": 0,
        "data": {
            "value": {
                "columns": [{"cells": [{"props": {"label": label}}]} for label in labels],
                "values": [[{"v": value} for value in row] for row in values],
                "page": {"count": len(values), "limit": 2000, "offset": 0},
            }
        },
    }


def test_current_utry_sample_labels_map_and_missing_metrics_stay_empty() -> None:
    labels = [
        "商品ID", "商品标题", "叶子类目", "行业大组", "一级大类", "二级大类",
        "派样单量", "派样人次", "派样GMV", "入仓派样单量",
    ]
    parsed = parse_sample_payload(
        _payload(labels, [["item-1", "试用装", "纸尿裤", "快消", "母婴", "婴童", 2, 3, "12.5", 1]]),
        business_day=date(2026, 8, 21),
    )

    assert len(parsed.rows) == 1
    row = parsed.rows[0]
    assert row.product_id == "item-1"
    assert row.leaf_category_name == "纸尿裤"
    assert row.metrics[:4] == (2, 3, 12.5, 1)
    assert all(value is None for value in row.metrics[4:])


def test_current_utry_repurchase_lowercase_uv_labels_are_supported() -> None:
    labels = [
        "商品ID", "商品名称", "ju_id", "叶子类目", "行业大组", "一级大类", "二级大类",
        "同店30日回购uv", "同店30日回购金额", "是否绑定正装1/0", "是否配置回购券1/0", "是否配置回购礼金1/0",
    ]
    parsed = parse_repurchase_payload(
        _payload(labels, [["item-2", "复购商品", "ju-1", "纸尿裤", "快消", "母婴", "婴童", 4, "99.9", 1, 0, 1]]),
        business_day=date(2026, 8, 21),
    )

    assert len(parsed.rows) == 1
    row = parsed.rows[0]
    assert row.product_id == "item-2"
    assert row.metrics[0] == 4
    assert row.metrics[1] == Decimal("99.9")
    assert row.bind_regular_product == "1"
