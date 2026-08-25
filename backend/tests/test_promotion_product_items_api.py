from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.local_database import BYBT_ITEM_COLUMNS, LocalDatabase, TAOBAO_FLASH_SALE_ITEM_COLUMNS, q
from app.main import create_app
from app.modules.imports.crawl_run_store import CrawlRunStore


def test_bybt_product_items_are_paginated_and_use_percent_conversion(tmp_path: Path) -> None:
    database_path = tmp_path / "promotion-product-items.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    CrawlRunStore(database_path).ensure_store_reference(
        store_id=1,
        store_name="Store 1",
        platform_store_id="p-1",
    )
    with sqlite3.connect(database_path) as connection:
        columns = ", ".join(q(column) for column in BYBT_ITEM_COLUMNS)
        placeholders = ", ".join("?" for _ in BYBT_ITEM_COLUMNS)
        connection.executemany(
            f"insert into store_daily_bybt_items ({columns}) values ({placeholders})",
            [
                (1, "2026-08-19", "1001", "m-1", "商品 A", "纸尿裤", "日常", "自营", "母婴", "直降", "100", "5", "4", "20", "0.2"),
                (1, "2026-08-20", "1001", "m-1", "商品 A", "纸尿裤", "日常", "自营", "母婴", "直降", "150", "6", "5", "30", "0.1667"),
                (1, "2026-08-20", "1002", "m-2", "商品 B", "湿巾", "日常", "自营", "母婴", "直降", "80", "3", "2", "10", "0.2"),
            ],
        )

    original_database = settings.local_database_path
    original_auth = settings.auth_enabled
    object.__setattr__(settings, "local_database_path", str(database_path))
    object.__setattr__(settings, "auth_enabled", False)
    try:
        with TestClient(create_app()) as client:
            response = client.get(
                "/api/v1/analytics/marketing/bybt/items",
                params={
                    "store_id": 1,
                    "start_date": "2026-08-19",
                    "end_date": "2026-08-20",
                    "page": 1,
                    "page_size": 1,
                    "sort": "paid_amount",
                },
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["total"] == 2
            assert len(payload["items"]) == 1
            assert payload["items"][0]["product_id"] == "1001"
            assert payload["items"][0]["paid_amount"] == "250.0"
            assert payload["items"][0]["conversion_rate"] == "18.0"
    finally:
        object.__setattr__(settings, "local_database_path", original_database)
        object.__setattr__(settings, "auth_enabled", original_auth)


def test_bybt_product_items_clip_requested_range_to_available_dates(tmp_path: Path) -> None:
    database_path = tmp_path / "promotion-product-items-range.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    CrawlRunStore(database_path).ensure_store_reference(store_id=1, store_name="Store 1", platform_store_id="p-1")
    with sqlite3.connect(database_path) as connection:
        columns = ", ".join(q(column) for column in BYBT_ITEM_COLUMNS)
        placeholders = ", ".join("?" for _ in BYBT_ITEM_COLUMNS)
        connection.execute(
            f"insert into store_daily_bybt_items ({columns}) values ({placeholders})",
            (1, "2026-08-19", "1001", "m-1", "商品 A", "纸尿裤", "日常", "自营", "母婴", "直降", "100", "5", "4", "20", "0.2"),
        )
        connection.commit()

    original_database = settings.local_database_path
    original_auth = settings.auth_enabled
    object.__setattr__(settings, "local_database_path", str(database_path))
    object.__setattr__(settings, "auth_enabled", False)
    try:
        with TestClient(create_app()) as client:
            response = client.get(
                "/api/v1/analytics/marketing/bybt/items",
                params={"store_id": 1, "start_date": "2026-08-19", "end_date": "2026-08-22"},
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["range_start"] == "2026-08-19"
            assert payload["range_end"] == "2026-08-19"
            assert payload["available_start"] == "2026-08-19"
            assert payload["available_end"] == "2026-08-19"
            assert payload["missing_dates"] == ["2026-08-20", "2026-08-21", "2026-08-22"]
            assert payload["total"] == 1
    finally:
        object.__setattr__(settings, "local_database_path", original_database)
        object.__setattr__(settings, "auth_enabled", original_auth)


def test_flash_sale_product_items_include_activity_and_new_customer_metrics(tmp_path: Path) -> None:
    database_path = tmp_path / "flash-sale-product-items.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    CrawlRunStore(database_path).ensure_store_reference(
        store_id=1,
        store_name="Store 1",
        platform_store_id="p-1",
    )
    with sqlite3.connect(database_path) as connection:
        columns = ", ".join(q(column) for column in TAOBAO_FLASH_SALE_ITEM_COLUMNS)
        placeholders = ", ".join("?" for _ in TAOBAO_FLASH_SALE_ITEM_COLUMNS)
        connection.executemany(
            f"insert into store_daily_taobao_flash_sale_items ({columns}) values ({placeholders})",
            [
                (1, "2026-08-19", "2001", "flash-1", "商品 A", "限时秒杀", "进行中", "2026-08-19 00:00:00", "2026-08-20 23:59:59", "180", "100", "20", "300", "4", "0.2"),
                (1, "2026-08-20", "2001", "flash-1", "商品 A", "限时秒杀", "已结束", "2026-08-19 00:00:00", "2026-08-20 23:59:59", "220", "150", "30", "450", "6", "0.2"),
            ],
        )

    original_database = settings.local_database_path
    original_auth = settings.auth_enabled
    object.__setattr__(settings, "local_database_path", str(database_path))
    object.__setattr__(settings, "auth_enabled", False)
    try:
        with TestClient(create_app()) as client:
            response = client.get(
                "/api/v1/analytics/marketing/flash-sale/items",
                params={
                    "store_id": 1,
                    "start_date": "2026-08-19",
                    "end_date": "2026-08-20",
                },
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["total"] == 1
            assert payload["items"][0] == {
                "product_id": "2001",
                "product_name": "商品 A",
                "activity_id": "flash-1",
                "activity_name": "限时秒杀",
                "category_name": "",
                "activity_status": "已结束",
                "visitors": 250,
                "paid_order_count": 50,
                "paid_items": None,
                "paid_amount": "750.0",
                "new_customers": 10,
                "conversion_rate": "20.0",
                "active_days": 2,
            }
    finally:
        object.__setattr__(settings, "local_database_path", original_database)
        object.__setattr__(settings, "auth_enabled", original_auth)
