from __future__ import annotations

from datetime import date
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.local_database import LocalDatabase
from app.modules.inventory.service import InventoryService, calculate_package_inventory
from app.modules.ai.schemas import AnalysisContext, AnalysisRequest, MCPEnvelope
from app.modules.ai.skills import select_skill
from app.modules.ai.service import AIAnalysisService


def test_package_inventory_is_minimum_per_warehouse_then_sum() -> None:
    result = calculate_package_inventory(
        [
            {"skuId": "A", "goodsNo": "A-NO", "goodsAmount": 2},
            {"skuId": "B", "goodsNo": "B-NO", "goodsAmount": 3},
        ],
        [
            {"warehouseId": "W1", "skuId": "A", "canUseQuantity": 11},
            {"warehouseId": "W1", "skuId": "B", "canUseQuantity": 13},
            {"warehouseId": "W2", "skuId": "A", "canUseQuantity": 5},
            {"warehouseId": "W2", "skuId": "B", "canUseQuantity": 20},
        ],
    )

    # W1=min(11//2, 13//3)=4; W2=min(5//2, 20//3)=2.
    assert result["assemblable_quantity"] == 6
    assert [item["assemblable_quantity"] for item in result["warehouses"]] == [4, 2]


def test_package_inventory_does_not_mix_stock_between_warehouses() -> None:
    result = calculate_package_inventory(
        [{"skuId": "A", "goodsAmount": 1}, {"skuId": "B", "goodsAmount": 1}],
        [
            {"warehouseId": "W1", "skuId": "A", "canUseQuantity": 100},
            {"warehouseId": "W2", "skuId": "B", "canUseQuantity": 100},
        ],
    )

    assert result["assemblable_quantity"] == 0


def test_package_inventory_aggregates_matching_rows_inside_one_warehouse() -> None:
    result = calculate_package_inventory(
        [{"skuId": "A", "goodsAmount": 2}, {"skuId": "B", "goodsAmount": 1}],
        [
            {"warehouseId": "W1", "skuId": "A", "canUseQuantity": 3},
            {"warehouseId": "W1", "skuId": "A", "canUseQuantity": 5},
            {"warehouseId": "W1", "skuId": "B", "canUseQuantity": 10},
        ],
    )

    # The two A rows belong to the same SKU and warehouse: (3 + 5) // 2 = 4.
    assert result["assemblable_quantity"] == 4
    warehouse = result["warehouses"][0]
    assert warehouse["components"][0]["available_quantity"] == 8


def test_package_inventory_prefers_sku_id_over_goods_number_fallback() -> None:
    result = calculate_package_inventory(
        [{"skuId": "A", "goodsNo": "SAME-GOODS", "goodsAmount": 1}],
        [
            {"warehouseId": "W1", "skuId": "A", "goodsNo": "SAME-GOODS", "canUseQuantity": 7},
            {"warehouseId": "W1", "skuId": "OTHER", "goodsNo": "SAME-GOODS", "canUseQuantity": 100},
        ],
    )

    assert result["assemblable_quantity"] == 7


def test_hourly_inventory_refresh_replaces_the_entire_store_day_snapshot(tmp_path: Path) -> None:
    service = InventoryService(tmp_path / "replace-snapshot.sqlite3")
    day = date(2026, 8, 22)
    service.upsert_inventory_snapshot(store_id=1, business_day=day, rows=[
        {"warehouseId": "W1", "skuId": "A", "goodsNo": "A-NO", "canUseQuantity": 5},
        {"warehouseId": "W1", "skuId": "B", "goodsNo": "B-NO", "canUseQuantity": 8},
    ])

    service.upsert_inventory_snapshot(store_id=1, business_day=day, rows=[
        {"warehouseId": "W1", "skuId": "B", "goodsNo": "B-NO", "canUseQuantity": 3},
        {"warehouseId": "W1", "skuId": "C", "goodsNo": "C-NO", "canUseQuantity": 9},
    ])

    with service.database.connect() as conn:
        rows = conn.execute(
            "select sku_id, available_quantity from jackyun_inventory_snapshots where store_id = ? and business_day = ? order by sku_id",
            (1, day.isoformat()),
        ).fetchall()
    assert [(row["sku_id"], row["available_quantity"]) for row in rows] == [("B", 3), ("C", 9)]


def test_inventory_query_returns_calculated_package_stock(tmp_path: Path) -> None:
    database_path = tmp_path / "inventory.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    service = InventoryService(database_path)
    service.upsert_package(
        store_id=1,
        product={"goodsId": "PKG-G", "skuId": "PKG-S", "goodsNo": "套餐001", "goodsName": "测试组合品"},
        components=[
            {"skuId": "A", "goodsNo": "A-NO", "goodsName": "子品A", "goodsAmount": 2},
            {"skuId": "B", "goodsNo": "B-NO", "goodsName": "子品B", "goodsAmount": 3},
        ],
    )
    service.upsert_inventory_snapshot(
        store_id=1,
        business_day=date(2026, 8, 21),
        rows=[
            {"warehouseId": "W1", "warehouseName": "一仓", "skuId": "A", "goodsNo": "A-NO", "canUseQuantity": 11},
            {"warehouseId": "W1", "warehouseName": "一仓", "skuId": "B", "goodsNo": "B-NO", "canUseQuantity": 13},
            {"warehouseId": "W2", "warehouseName": "二仓", "skuId": "A", "goodsNo": "A-NO", "canUseQuantity": 5},
            {"warehouseId": "W2", "warehouseName": "二仓", "skuId": "B", "goodsNo": "B-NO", "canUseQuantity": 20},
        ],
    )

    result = service.query(store_id=1, query="套餐001")

    assert result["status"] == "ok"
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["item_type"] == "package"
    assert item["assemblable_quantity"] == 6
    assert [warehouse["assemblable_quantity"] for warehouse in item["warehouses"]] == [4, 2]


def test_inventory_questions_select_inventory_skill() -> None:
    assert select_skill("这个组合品还能组多少套", "auto").descriptor.name == "inventory-query"
    assert select_skill("查大鱼 M 码库存", "inventory").descriptor.name == "inventory-query"
    assert select_skill("你好", "inventory").descriptor.name == "general-chat"
    assert AIAnalysisService._inventory_business_day("查大鱼 M 码库存") is None
    assert AIAnalysisService._inventory_business_day("查 2026-08-20 大鱼 M 码库存") == date(2026, 8, 20)


def test_general_chat_question_does_not_call_inventory_tool(tmp_path: Path) -> None:
    class FakeMCP:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        def execute(self, tool: str, arguments: dict):
            self.calls.append((tool, arguments))
            raise AssertionError("general chat should not reach inventory tools")

    class FakeProvider:
        configured = True
        name = "fake"
        model = "fake-model"

        def generate_answer(self, **_kwargs):
            raise AssertionError("general chat should use the fast deterministic reply")

    service = AIAnalysisService(mcp=FakeMCP(), provider=FakeProvider(), database_path=tmp_path / "ai.sqlite3")
    fake_mcp = service.mcp
    result = service.analyze(AnalysisRequest(question="你好", use_model=True), store_id=None, user_id=None)

    assert result.skill.name == "general-chat"
    assert result.answer.startswith("你好，我在")
    assert result.provider == "rules"
    assert fake_mcp.calls == []
    assert result.diagnosis.analysis_scope == {"kind": "chat"}
    assert result.diagnosis.assumptions == []
    assert result.diagnosis.causal_boundary == ""
    assert result.execution_steps[-1].detail == "通用对话使用快速回复"
    assert result.conversation_memory["last_question"] == "你好"
    assert result.conversation_memory["skill"] == "general-chat"


def test_inventory_query_builds_decision_summary_and_limits_findings(tmp_path: Path) -> None:
    items = [
        {"item_type": "sku", "goods_name": "大鱼海棠 M 码常规销售装", "goods_no": "REG-0", "available_quantity": 0},
        {"item_type": "sku", "goods_name": "大鱼海棠 M 码常规销售装 50 片", "goods_no": "REG-1", "available_quantity": 120},
        {"item_type": "sku", "goods_name": "大鱼海棠 M 码试用装 5 片", "goods_no": "SAMPLE-0", "pieces": 5, "available_quantity": 0},
        {"item_type": "sku", "goods_name": "大鱼海棠 M 码猫超专供加量装", "goods_no": "BUNDLE-1", "available_quantity": 15},
        {"item_type": "sku", "goods_name": "纸箱：大鱼海棠 M 码", "goods_no": "BOX-0", "available_quantity": 0},
    ]

    class FakeMCP:
        def execute(self, tool: str, _arguments: dict):
            assert tool == "inventory.query"
            return MCPEnvelope(
                request_id="inventory-summary",
                tool=tool,
                generated_at=datetime.now(timezone.utc).isoformat(),
                context=AnalysisContext(store_id=1, range_start=date(2026, 8, 23), range_end=date(2026, 8, 23)),
                status="ok",
                data={
                    "items": items,
                    "reason": "matched",
                    "business_day": "2026-08-23",
                    "latest_snapshot_at": "2026-08-22T23:00:00+08:00",
                    "snapshot_age_minutes": 121,
                    "freshness_status": "stale",
                    "snapshot_row_count": 5,
                },
            )

    service = AIAnalysisService(mcp=FakeMCP(), database_path=tmp_path / "inventory-summary.sqlite3")
    result = service.analyze(AnalysisRequest(question="查一下大鱼 M 码库存", use_model=False), store_id=1, user_id=None)

    summary = result.mcp_results[0].data["decision_summary"]
    regular = next(item for item in summary["groups"] if item["key"] == "regular")
    packaging = next(item for item in summary["groups"] if item["key"] == "packaging")
    assert result.diagnosis.confidence == "low"
    assert regular["item_count"] == 2
    assert regular["zero_stock_count"] == 1
    assert packaging["zero_stock_count"] == 1
    assert len(result.diagnosis.findings) <= 3
    assert [artifact.title for artifact in result.diagnosis.artifacts] == ["库存风险清单", "全部匹配库存"]
    assert len(result.diagnosis.artifacts[1].rows) == 5
    assert all("毛利率" not in item for item in result.diagnosis.assumptions)
    assert result.diagnosis.causal_boundary == ""


def test_inventory_query_uses_latest_snapshot_and_normalizes_size_terms(tmp_path: Path) -> None:
    service = InventoryService(tmp_path / "latest.sqlite3")
    service.upsert_inventory_snapshot(store_id=1, business_day=date(2026, 8, 20), rows=[
        {"goodsNo": "DAYU", "goodsName": "大鱼海棠", "skuNo": "DAYU-S", "skuName": "S码", "canUseQuantity": 3},
    ])
    service.upsert_inventory_snapshot(store_id=1, business_day=date(2026, 8, 21), rows=[
        {"goodsNo": "DAYU", "goodsName": "大鱼海棠", "skuNo": "DAYU-M", "skuName": "M码", "canUseQuantity": 8},
    ])

    result = service.query(store_id=1, query="查一下大鱼 M 码库存")

    assert InventoryService._candidate_terms("查一下大鱼 M 码库存") == ["大鱼", "m码"]
    assert result["business_day"] == date(2026, 8, 21)
    assert result["items"][0]["sku_name"] == "M码"
    assert result["items"][0]["available_quantity"] == 8
    assert result["reason"] == "matched"


def test_inventory_query_distinguishes_date_and_sku_misses(tmp_path: Path) -> None:
    service = InventoryService(tmp_path / "reasons.sqlite3")
    service.upsert_inventory_snapshot(store_id=1, business_day=date(2026, 8, 21), rows=[
        {"goodsNo": "DAYU", "goodsName": "大鱼海棠", "skuNo": "DAYU-M", "skuName": "M码", "canUseQuantity": 0},
    ])

    date_result = service.query(store_id=1, query="大鱼库存", business_day=date(2026, 8, 20))
    sku_result = service.query(store_id=1, query="大鱼 L 码库存")
    zero_result = service.query(store_id=1, query="大鱼 M 码库存")

    assert date_result["reason"] == "date_not_available"
    assert sku_result["reason"] == "sku_not_matched"
    assert zero_result["reason"] == "zero_stock"


def test_inventory_query_marks_snapshot_over_one_hour_stale(tmp_path: Path) -> None:
    service = InventoryService(tmp_path / "stale.sqlite3")
    service.upsert_inventory_snapshot(store_id=1, business_day=date(2026, 8, 21), rows=[
        {"goodsNo": "DAYU", "goodsName": "大鱼海棠", "skuName": "M码", "canUseQuantity": 4},
    ])
    old = (datetime.now(timezone.utc) - timedelta(minutes=61)).isoformat()
    with service.database.connect(initialize=True, read_only=False) as conn:
        conn.execute("update jackyun_inventory_snapshots set fetched_at = ?", (old,))
        conn.commit()

    result = service.query(store_id=1, query="大鱼 M 码库存")

    assert result["freshness_status"] == "stale"
    assert result["snapshot_age_minutes"] >= 61


def test_inventory_query_matches_code_inside_conversational_text(tmp_path: Path) -> None:
    service = InventoryService(tmp_path / "code-query.sqlite3")
    service.upsert_inventory_snapshot(store_id=1, business_day=date(2026, 8, 22), rows=[
        {
            "goodsNo": "L56L01",
            "goodsName": "胖达拉拉裤试用装",
            "skuNo": "L56L01",
            "skuName": "L码 1片",
            "canUseQuantity": 17,
        },
    ])

    assert InventoryService._candidate_terms("L56L01这个库存给我") == ["l56l01"]
    result = service.query(store_id=1, query="L56L01这个库存给我")

    assert result["status"] == "ok"
    assert result["reason"] == "matched"
    assert result["match_type"] == "exact_code"
    assert result["matched_by"] == ["goods_no", "sku_no"]
    assert result["items"][0]["available_quantity"] == 17
    assert result["items"][0]["size"] == "L"
    assert result["items"][0]["pieces"] == 1


def test_inventory_query_reports_multiple_rows_for_same_code(tmp_path: Path) -> None:
    service = InventoryService(tmp_path / "ambiguous-code.sqlite3")
    service.upsert_inventory_snapshot(store_id=1, business_day=date(2026, 8, 22), rows=[
        {"goodsNo": "L56L01", "skuId": "SKU-A", "skuName": "L码拉拉裤试用装", "canUseQuantity": 3},
        {"goodsNo": "L56L01", "skuId": "SKU-B", "skuName": "L码纸尿裤试用装", "canUseQuantity": 8},
    ])

    result = service.query(store_id=1, query="查 L56L01 库存")

    assert result["status"] == "ok"
    assert result["reason"] == "ambiguous_code"
    assert result["ambiguous"] is True
    assert result["candidate_count"] == 2
    assert len(result["items"]) == 2


def test_requested_missing_day_does_not_reuse_latest_snapshot_time(tmp_path: Path) -> None:
    service = InventoryService(tmp_path / "date-freshness.sqlite3")
    service.upsert_inventory_snapshot(store_id=1, business_day=date(2026, 8, 22), rows=[
        {"goodsNo": "L56L01", "canUseQuantity": 4},
    ])

    result = service.query(store_id=1, query="L56L01库存", business_day=date(2026, 8, 21))

    assert result["reason"] == "date_not_available"
    assert result["latest_snapshot_at"] is None
    assert result["snapshot_age_minutes"] is None
    assert result["latest_available_snapshot_at"] is not None


def test_inventory_management_joins_catalog_and_separates_unmatched_stock(tmp_path: Path) -> None:
    service = InventoryService(tmp_path / "management.sqlite3")
    with service.database.connect(initialize=True, read_only=False) as conn:
        conn.executemany(
            """
            insert into inventory_product_catalog
                (store_id, series, specification, size, goods_no, pieces, display_name, source, source_line, updated_at)
            values (1, ?, ?, ?, ?, ?, ?, 'test', ?, '2026-08-22T00:00:00+08:00')
            """,
            [
                ("胖达", "拉拉裤试用装", "L", "L56L01", 1, "拉拉裤试用装L码1片", 1),
                ("胖达", "纸尿裤试用装", "L", "Z56L01", 1, "纸尿裤试用装L码1片", 2),
            ],
        )
        conn.commit()
    service.upsert_inventory_snapshot(store_id=1, business_day=date(2026, 8, 22), rows=[
        {"goodsNo": "L56L01", "canUseQuantity": 0},
    ])

    result = service.management(store_id=1, query="L56L01")

    assert result["total"] == 1
    assert result["rows"][0]["series"] == "胖达"
    assert result["rows"][0]["stock_status"] == "零库存"
    unmatched = service.management(store_id=1, stock_status="未匹配库存")
    assert unmatched["total"] == 1
    assert unmatched["rows"][0]["goods_no"] == "Z56L01"


def test_inventory_query_resolves_series_regular_pack_stockout_sizes(tmp_path: Path) -> None:
    service = InventoryService(tmp_path / "stockout-scope.sqlite3")
    with service.database.connect(initialize=True, read_only=False) as conn:
        conn.executemany(
            """
            insert into inventory_product_catalog
                (store_id, series, specification, size, goods_no, pieces, display_name, source, source_line, updated_at)
            values (1, ?, ?, ?, ?, ?, ?, 'test', ?, '2026-08-22T00:00:00+08:00')
            """,
            [
                ("大鱼", "纸尿裤", "M", "DAYU-M", 46, "纸尿裤M码46片", 1),
                ("大鱼", "纸尿裤", "L", "DAYU-L", 38, "纸尿裤L码38片", 2),
                ("大鱼", "纸尿裤试用装", "M", "DAYU-M-TRIAL", 1, "纸尿裤试用装M码1片", 3),
            ],
        )
        conn.commit()
    service.upsert_inventory_snapshot(store_id=1, business_day=date(2026, 8, 22), rows=[
        {"goodsNo": "DAYU-M", "canUseQuantity": 0},
        {"goodsNo": "DAYU-L", "canUseQuantity": 8},
        {"goodsNo": "DAYU-M-TRIAL", "canUseQuantity": 0},
    ])

    result = service.query(store_id=1, query="大鱼海棠正装有哪些缺货的尺码")

    assert result["status"] == "ok"
    assert result["reason"] == "stockouts_found"
    assert result["scope"]["label"] == "大鱼正装"
    assert result["scope"]["checked_sku_count"] == 2
    assert [(item["specification"], item["size"]) for item in result["items"]] == [("纸尿裤", "M")]


def test_inventory_query_reports_no_stockouts_as_a_valid_result(tmp_path: Path) -> None:
    service = InventoryService(tmp_path / "no-stockouts.sqlite3")
    with service.database.connect(initialize=True, read_only=False) as conn:
        conn.execute(
            """
            insert into inventory_product_catalog
                (store_id, series, specification, size, goods_no, pieces, display_name, source, source_line, updated_at)
            values (1, '大鱼', '拉拉裤', 'L', 'DAYU-L', 32, '拉拉裤L码32片', 'test', 1, '2026-08-22T00:00:00+08:00')
            """
        )
        conn.commit()
    service.upsert_inventory_snapshot(store_id=1, business_day=date(2026, 8, 22), rows=[
        {"goodsNo": "DAYU-L", "canUseQuantity": 12},
    ])

    result = service.query(store_id=1, query="大鱼正装哪些尺码缺货")

    assert result["status"] == "ok"
    assert result["reason"] == "no_stockouts"
    assert result["items"] == []
    assert result["scope"]["checked_sku_count"] == 1


def test_inventory_query_matches_regular_diapers_without_series_and_aliases(tmp_path: Path) -> None:
    service = InventoryService(tmp_path / "all-diapers-stockout.sqlite3")
    with service.database.connect(initialize=True, read_only=False) as conn:
        conn.executemany(
            """
            insert into inventory_product_catalog
                (store_id, series, specification, size, goods_no, pieces, display_name, source, source_line, updated_at)
            values (1, ?, ?, ?, ?, ?, ?, 'test', ?, '2026-08-22T00:00:00+08:00')
            """,
            [
                ("大鱼", "纸尿裤", "M", "DAYU-M", 46, "纸尿裤M码46片", 1),
                ("小熊", "拉拉裤", "L", "BEAR-L", 32, "拉拉裤L码32片", 2),
                ("小熊", "纸尿裤试用装", "M", "BEAR-TRIAL", 1, "纸尿裤试用装M码1片", 3),
            ],
        )
        conn.commit()
    service.upsert_inventory_snapshot(store_id=1, business_day=date(2026, 8, 22), rows=[
        {"goodsNo": "DAYU-M", "canUseQuantity": 0},
        {"goodsNo": "BEAR-L", "canUseQuantity": 0},
        {"goodsNo": "BEAR-TRIAL", "canUseQuantity": 0},
    ])

    result = service.query(store_id=1, query="有哪些正装的尿裤缺货了")

    assert result["reason"] == "stockouts_found"
    assert result["scope"]["product_type"] == "尿裤"
    assert result["scope"]["checked_sku_count"] == 2
    assert {item["goods_no"] for item in result["items"]} == {"DAYU-M", "BEAR-L"}

    paper = service.query(store_id=1, query="正装纸尿裤有哪些缺货")
    assert paper["scope"]["product_type"] == "纸尿裤"
    assert [item["goods_no"] for item in paper["items"]] == ["DAYU-M"]


def test_inventory_scope_query_does_not_truncate_catalog_after_200_rows(tmp_path: Path) -> None:
    service = InventoryService(tmp_path / "catalog-over-200.sqlite3")
    with service.database.connect(initialize=True, read_only=False) as conn:
        conn.executemany(
            """
            insert into inventory_product_catalog
                (store_id, series, specification, size, goods_no, pieces, display_name, source, source_line, updated_at)
            values (1, '系列', '纸尿裤', 'M', ?, 40, ?, 'test', ?, '2026-08-22T00:00:00+08:00')
            """,
            [(f"SKU-{index:03d}", f"纸尿裤M码40片-{index:03d}", index) for index in range(205)],
        )
        conn.commit()
    service.upsert_inventory_snapshot(store_id=1, business_day=date(2026, 8, 22), rows=[
        {"goodsNo": "SKU-204", "canUseQuantity": 0},
    ])

    result = service.query(store_id=1, query="正装纸尿裤有哪些缺货")

    assert result["reason"] == "stockout_scope_partial"
    assert result["scope"]["checked_sku_count"] == 1
    assert result["scope"]["unmatched_sku_count"] == 204
    assert len(result["items"]) == 1
    assert result["items"][0]["goods_no"] == "SKU-204"
