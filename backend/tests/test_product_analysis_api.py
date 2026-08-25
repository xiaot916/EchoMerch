from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.local_database import LocalDatabase
from app.main import create_app
from app.modules.imports.crawl_run_store import CrawlRunStore


def test_product_analysis_uses_store_product_rankings(tmp_path: Path) -> None:
    database_path = tmp_path / "product-analysis.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    CrawlRunStore(database_path).ensure_store_reference(store_id=1, store_name="测试店铺", platform_store_id="shop-1")
    with LocalDatabase(database_path).connect(read_only=False) as conn:
        conn.executemany(
            '''insert into store_daily_product_rankings
               ("店铺ID", "业务日期", "商品ID", "商品名称", "支付金额", "支付买家数", "商品访客数",
                "商品加购人数", "商品收藏人数", "商品浏览量", "搜索引导访客数", "推广消耗")
               values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                (1, "2026-08-19", "1001", "测试商品 A", "1200", "12", "100", "20", "9", "230", "40", "100"),
                (1, "2026-08-20", "1001", "测试商品 A", "1800", "18", "120", "25", "11", "260", "48", "120"),
                (1, "2026-08-20", "1002", "测试商品 B", "900", "9", "90", "16", "6", "180", "30", "80"),
            ),
        )
        conn.executemany(
            '''insert into store_product_catalog
               ("店铺ID", "商品ID", "商品名称", "类型", "系列", "定位") values (?, ?, ?, ?, ?, ?)''',
            (
                (1, "1001", "测试商品 A", "主销", "系列一", "利润款"),
                (1, "1002", "测试商品 B", "主销", "系列一", "引流款"),
            ),
        )

    original_database = settings.local_database_path
    original_auth = settings.auth_enabled
    object.__setattr__(settings, "local_database_path", str(database_path))
    object.__setattr__(settings, "auth_enabled", False)
    try:
        with TestClient(create_app()) as client:
            products = client.get("/api/v1/analytics/products?store_id=1&start_date=2026-08-19&end_date=2026-08-20")
            assert products.status_code == 200
            assert [item["product_id"] for item in products.json()] == ["1001", "1002"]

            detail = client.get("/api/v1/analytics/products/1001?store_id=1&start_date=2026-08-19&end_date=2026-08-20")
            assert detail.status_code == 200
            payload = detail.json()
            assert payload["product"]["paid_amount"] == "3000.0"
            assert payload["product"]["series"] == "系列一"
            assert len(payload["daily_metrics"]) == 2
            assert {item["product_id"] for item in payload["peers"]} == {"1001", "1002"}
    finally:
        object.__setattr__(settings, "local_database_path", original_database)
        object.__setattr__(settings, "auth_enabled", original_auth)
