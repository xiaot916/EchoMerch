from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.local_database import (
    BRAND_ASSET_OVERVIEW_TABLE,
    BRAND_ASSET_STAGE_TABLE,
    BRAND_PRODUCT_ASSET_CONSUMERS,
    BRAND_PRODUCT_DAILY_TABLE,
    BRAND_PRODUCT_ID,
    BRAND_PRODUCT_NAME,
    BRAND_PRODUCT_NEW_ASSET_CONSUMERS,
    BRAND_PRODUCT_SERIES,
    BRAND_PRODUCT_STATUS,
    BRAND_PRODUCT_TABLE,
    BRAND_ID,
    BRAND_NAME,
    BRAND_STATISTIC_SCOPE,
    BRAND_STATUS,
    BRAND_SUBJECT_ID,
    BUSINESS_DAY,
    BRAND_CONSUMER_COUNT,
    BRAND_TRANSACTION_AMOUNT,
    CREATED_AT,
    LocalDatabase,
    q,
    UPDATED_AT,
)
from app.main import create_app
from app.modules.access.service import AccessControlStore


def _set_settings(database_path: Path) -> dict[str, object]:
    original = {
        "local_database_path": settings.local_database_path,
        "auth_enabled": settings.auth_enabled,
        "auth_cookie_secure": settings.auth_cookie_secure,
    }
    object.__setattr__(settings, "local_database_path", str(database_path))
    object.__setattr__(settings, "auth_enabled", True)
    object.__setattr__(settings, "auth_cookie_secure", False)
    return original


def _restore_settings(original: dict[str, object]) -> None:
    for key, value in original.items():
        object.__setattr__(settings, key, value)


def test_brand_asset_subject_and_scope_are_separate(tmp_path: Path) -> None:
    database_path = tmp_path / "brand-assets.sqlite3"
    database = LocalDatabase(database_path)
    database.initialize_schema()
    with database.connect(read_only=False) as conn:
        conn.execute(
            f"insert into brands ({BRAND_ID}, {BRAND_SUBJECT_ID}, {BRAND_NAME}, {BRAND_STATUS}, {CREATED_AT}, {UPDATED_AT}) values (?, ?, ?, ?, ?, ?)",
            ("brand-1", "subject-1", "测试品牌", "active", "2026-08-20", "2026-08-20"),
        )
        conn.execute(
            f"insert into {q(BRAND_ASSET_OVERVIEW_TABLE)} ({q(BRAND_ID)}, {q(BRAND_STATISTIC_SCOPE)}, {q(BUSINESS_DAY)}, {q(BRAND_CONSUMER_COUNT)}) values (?, ?, ?, ?)",
            ("brand-1", "品牌整体", "2026-08-19", "1200"),
        )
        conn.execute(
            f"insert into {q(BRAND_ASSET_OVERVIEW_TABLE)} ({q(BRAND_ID)}, {q(BRAND_STATISTIC_SCOPE)}, {q(BUSINESS_DAY)}, {q(BRAND_CONSUMER_COUNT)}) values (?, ?, ?, ?)",
            ("brand-1", "品牌整体", "2026-08-18", "1100"),
        )
        conn.executemany(
            f'''insert into {q(BRAND_ASSET_STAGE_TABLE)}
                ({q(BRAND_ID)}, {q(BUSINESS_DAY)}, {q("资产阶段编码")}, {q("资产阶段名称")}, {q(BRAND_CONSUMER_COUNT)})
                values (?, ?, ?, ?, ?)''',
            (
                ("brand-1", "2026-08-18", "a", "认知人群", "700"),
                ("brand-1", "2026-08-19", "a", "认知人群", "750"),
                ("brand-1", "2026-08-19", "i", "兴趣人群", "450"),
            ),
        )
        columns = {row[1] for row in conn.execute(f"pragma table_info({q(BRAND_ASSET_OVERVIEW_TABLE)})")}
        assert "店铺ID" not in columns

    access = AccessControlStore(database_path)
    user = access.create_user(
        username="brand-viewer",
        display_name="品牌访客",
        password="brand-password-123",
        role_codes=["viewer"],
        store_ids=[],
        brand_ids=["brand-1"],
        actor_user_id=None,
    )
    assert user.brand_ids == ["brand-1"]

    original = _set_settings(database_path)
    try:
        with TestClient(create_app()) as client:
            login = client.post("/api/v1/auth/login", json={"username": "brand-viewer", "password": "brand-password-123"})
            assert login.status_code == 200
            assert [item["brand_id"] for item in client.get("/api/v1/brand-assets/brands").json()] == ["brand-1"]
            summary = client.get("/api/v1/brand-assets/summary?brand_id=brand-1&start_date=2026-08-18&end_date=2026-08-19")
            assert summary.status_code == 200
            assert summary.json()["brand"]["brand_id"] == "brand-1"
            assert summary.json()["overview"]["消费者数"] == "1200"
            assert [row["业务日期"] for row in summary.json()["overview_trend"]] == ["2026-08-18", "2026-08-19"]
            assert {row["资产阶段名称"] for row in summary.json()["stages"]} == {"认知人群", "兴趣人群"}
            assert client.get("/api/v1/brand-assets/summary?brand_id=other-brand").status_code == 403
    finally:
        _restore_settings(original)


def test_brand_store_scope_survives_repeated_schema_initialization(tmp_path: Path) -> None:
    database_path = tmp_path / "brand-schema-reinitialize.sqlite3"
    database = LocalDatabase(database_path)

    database.initialize_schema()
    database.initialize_schema(force=True)

    with database.connect() as conn:
        table = conn.execute(
            "select name from sqlite_master where type = 'table' and name = 'brand_store_scopes'"
        ).fetchone()
        index = conn.execute(
            "select name from sqlite_master where type = 'index' and name = 'idx_brand_store_scopes_store'"
        ).fetchone()

    assert table is not None
    assert index is not None


def test_product_analysis_uses_product_id_and_series_across_authorized_brands(tmp_path: Path) -> None:
    database_path = tmp_path / "product-analysis.sqlite3"
    database = LocalDatabase(database_path)
    database.initialize_schema()
    with database.connect(read_only=False) as conn:
        conn.executemany(
            f"insert into brands ({BRAND_ID}, {BRAND_SUBJECT_ID}, {BRAND_NAME}, {BRAND_STATUS}, {CREATED_AT}, {UPDATED_AT}) values (?, ?, ?, ?, ?, ?)",
            (
                ("brand-a", "subject-a", "数据主体 A", "active", "2026-08-20", "2026-08-20"),
                ("brand-b", "subject-b", "数据主体 B", "active", "2026-08-20", "2026-08-20"),
            ),
        )
        conn.executemany(
            f"""
            insert into {q(BRAND_PRODUCT_TABLE)} (
                {q(BRAND_ID)}, {q(BRAND_PRODUCT_ID)}, {q(BRAND_PRODUCT_NAME)},
                {q(BRAND_PRODUCT_SERIES)}, {q(BRAND_PRODUCT_STATUS)}, {q(CREATED_AT)}, {q(UPDATED_AT)}
            ) values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ("brand-a", "1001", "系列一商品 A", "系列一", "active", "2026-08-20", "2026-08-20"),
                ("brand-b", "2001", "系列一商品 B", "系列一", "active", "2026-08-20", "2026-08-20"),
                ("brand-b", "3001", "系列二商品", "系列二", "active", "2026-08-20", "2026-08-20"),
            ),
        )
        conn.executemany(
            f"""
            insert into {q(BRAND_PRODUCT_DAILY_TABLE)} (
                {q(BRAND_ID)}, {q(BUSINESS_DAY)}, {q(BRAND_PRODUCT_ID)},
                {q(BRAND_PRODUCT_ASSET_CONSUMERS)}, {q(BRAND_PRODUCT_NEW_ASSET_CONSUMERS)},
                {q(BRAND_TRANSACTION_AMOUNT)}
            ) values (?, ?, ?, ?, ?, ?)
            """,
            (
                ("brand-a", "2026-08-19", "1001", "100", "10", "1000"),
                ("brand-b", "2026-08-19", "2001", "80", "8", "800"),
                ("brand-b", "2026-08-19", "3001", "60", "6", "600"),
            ),
        )

    access = AccessControlStore(database_path)
    access.create_user(
        username="product-viewer",
        display_name="商品分析访客",
        password="product-password-123",
        role_codes=["viewer"],
        store_ids=[],
        brand_ids=["brand-a", "brand-b"],
        actor_user_id=None,
    )

    original = _set_settings(database_path)
    try:
        with TestClient(create_app()) as client:
            login = client.post("/api/v1/auth/login", json={"username": "product-viewer", "password": "product-password-123"})
            assert login.status_code == 200

            products = client.get("/api/v1/brand-assets/products")
            assert products.status_code == 200
            assert [item["product_id"] for item in products.json()] == ["1001", "2001", "3001"]

            response = client.get(
                "/api/v1/brand-assets/products/1001/analysis?start_date=2026-08-19&end_date=2026-08-19"
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["product"]["product_id"] == "1001"
            assert payload["product"]["series"] == "系列一"
            assert payload["period_metrics"]["成交金额"] == 1000
            assert {item["商品ID"] for item in payload["peers"]} == {"1001", "2001"}
    finally:
        _restore_settings(original)
