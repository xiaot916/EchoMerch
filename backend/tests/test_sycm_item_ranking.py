import json
from datetime import date
from pathlib import Path

from app.core.local_database import (
    PAID_ITEMS,
    LocalDatabase,
    PRODUCT_RANKING_ITEM_ID,
    PRODUCT_RANKING_TABLE,
    q,
)
from app.warehouse.store import WarehouseStore
from app.warehouse.sycm_item_ranking import parse_payload


def _row(item_id: str, payment_items: str) -> dict[str, object]:
    return {
        "itemId": {"value": item_id},
        "item": {"title": f"\u5546\u54c1 {item_id}"},
        "itemStatus": "\u5728\u552e",
        "payAmt": {"value": "99.50"},
        "payItmCnt": {"value": payment_items},
        "itemCartCnt": {"value": "6"},
        "itmStayTime": {"value": "35"},
        "fCharge": {"value": "4.30"},
        "pDROI": {"value": "12.5"},
    }


def _payload() -> dict[str, object]:
    return {
        "code": 0,
        "data": {
            "data": [
                _row("1001", "3"),
                _row("1002", "0"),
            ]
        },
    }


def test_item_ranking_parser_stops_at_first_zero_payment_item() -> None:
    parsed = parse_payload(_payload(), business_day=date(2026, 8, 16))

    assert parsed.reached_zero_payment_items is True
    assert len(parsed.rows) == 1
    assert parsed.rows[0]["\u5546\u54c1ID"] == "1001"
    assert parsed.rows[0]["\u5546\u54c1\u540d\u79f0"] == "\u5546\u54c1 1001"
    assert parsed.rows[0]["\u5546\u54c1\u52a0\u8d2d\u4ef6\u6570"] == "6"
    assert parsed.rows[0]["\u5e73\u5747\u505c\u7559\u65f6\u957f"] == "35"
    assert parsed.rows[0]["\u63a8\u5e7f\u76f4\u63a5ROI"] == "12.5"


def test_item_ranking_ingest_replaces_one_store_day_snapshot(tmp_path: Path) -> None:
    response_file = tmp_path / "item-ranking.json"
    response_file.write_text(
        json.dumps({"pages": [_payload()]}, ensure_ascii=False),
        encoding="utf-8",
    )
    database_path = tmp_path / "warehouse.sqlite3"
    store = WarehouseStore(database_path)

    result = store.ingest_sycm_item_ranking(
        source_path=response_file,
        business_day=date(2026, 8, 16),
        store_name="\u6d4b\u8bd5\u5e97\u94fa",
        platform_store_id="test-shop",
    )

    assert result.row_count == 1
    with LocalDatabase(database_path).connect() as conn:
        rows = conn.execute(
            f"select {q(PRODUCT_RANKING_ITEM_ID)}, {q(PAID_ITEMS)} from {PRODUCT_RANKING_TABLE}"
        ).fetchall()
    assert [tuple(row) for row in rows] == [("1001", "3")]
