from __future__ import annotations

import csv
import io
import sqlite3
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.local_database import LocalDatabase
from app.main import create_app
from app.modules.access.service import AccessControlStore
from app.modules.imports.crawl_run_store import CrawlRunStore
from app.modules.warehouse import store_data
from app.api.v1.routes import collection


def _seed_database(database_path: Path) -> None:
    LocalDatabase(database_path).initialize_schema()
    ledger = CrawlRunStore(database_path)
    ledger.ensure_store_reference(store_id=7, store_name="授权店铺", platform_store_id="platform-7")
    ledger.ensure_store_reference(store_id=8, store_name="未授权店铺", platform_store_id="platform-8")
    with sqlite3.connect(database_path) as connection:
        connection.executemany(
            'insert into store_daily_overviews ("店铺ID", "业务日期", "支付金额") values (?, ?, ?)',
            [
                (7, "2026-08-01", "100.00"),
                (7, "2026-08-02", "200.00"),
                (7, "2026-08-03", "300.00"),
                (8, "2026-08-01", "800.00"),
            ],
        )


def _set_database(database_path: Path, *, auth_enabled: bool = False) -> dict[str, object]:
    original = {
        "local_database_path": settings.local_database_path,
        "auth_enabled": settings.auth_enabled,
        "auth_cookie_secure": settings.auth_cookie_secure,
    }
    object.__setattr__(settings, "local_database_path", str(database_path))
    object.__setattr__(settings, "auth_enabled", auth_enabled)
    object.__setattr__(settings, "auth_cookie_secure", False)
    return original


def _restore_settings(original: dict[str, object]) -> None:
    for key, value in original.items():
        object.__setattr__(settings, key, value)


def test_store_data_preview_catalog_and_exports(tmp_path: Path) -> None:
    database_path = tmp_path / "store-data.sqlite3"
    _seed_database(database_path)
    original = _set_database(database_path)
    try:
        with TestClient(create_app()) as client:
            catalog = client.get("/api/v1/warehouse/store-data/datasets?store_id=7")
            assert catalog.status_code == 200
            catalog_payload = catalog.json()
            assert catalog_payload["reference_date"] == "2026-08-03"
            assert catalog_payload["available_count"] == 1
            assert catalog_payload["current_count"] == 1
            assert catalog_payload["empty_count"] >= 1
            overview = next(item for item in catalog_payload["datasets"] if item["key"] == "overview")
            assert overview["row_count"] == 3
            assert overview["status"] == "current"
            assert overview["lag_days"] == 0
            assert "支付金额" in [column["key"] for column in overview["columns"]]

            preview = client.get(
                "/api/v1/warehouse/store-data/preview",
                params={
                    "store_id": 7,
                    "dataset": "overview",
                    "start_date": "2026-08-02",
                    "end_date": "2026-08-03",
                    "page": 1,
                    "page_size": 1,
                },
            )
            assert preview.status_code == 200
            assert preview.json()["total"] == 2
            assert preview.json()["rows"][0]["业务日期"] == "2026-08-03"

            csv_response = client.get(
                "/api/v1/warehouse/store-data/export",
                params={"store_id": 7, "dataset": "overview", "format": "csv"},
            )
            assert csv_response.status_code == 200
            assert csv_response.content.startswith(b"\xef\xbb\xbf")
            csv_rows = list(csv.reader(io.StringIO(csv_response.content.decode("utf-8-sig"))))
            assert csv_rows[0][0] == "店铺ID"
            assert len(csv_rows) == 4

            xlsx_response = client.get(
                "/api/v1/warehouse/store-data/export",
                params={"store_id": 7, "dataset": "overview", "format": "xlsx"},
            )
            assert xlsx_response.status_code == 200
            workbook = openpyxl.load_workbook(io.BytesIO(xlsx_response.content), read_only=True)
            assert workbook["数据明细"]["A2"].value == 7
            assert workbook["数据明细"]["B2"].value == "2026-08-03"
            workbook.close()

            assert client.get(
                "/api/v1/warehouse/store-data/preview",
                params={"store_id": 7, "dataset": "not-a-dataset"},
            ).status_code == 404
    finally:
        _restore_settings(original)


def test_store_data_scope_and_export_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database_path = tmp_path / "store-data-access.sqlite3"
    _seed_database(database_path)
    access = AccessControlStore(database_path)
    access.create_user(
        username="owner",
        display_name="超级管理员",
        password="owner-password-123",
        role_codes=["super_admin"],
        store_ids=[],
        actor_user_id=None,
    )
    access.create_user(
        username="operator",
        display_name="运营用户",
        password="operator-password-123",
        role_codes=["operator"],
        store_ids=[7],
        actor_user_id=None,
    )
    original = _set_database(database_path, auth_enabled=True)
    try:
        with TestClient(create_app()) as client:
            assert client.post(
                "/api/v1/auth/login",
                json={"username": "operator", "password": "operator-password-123"},
            ).status_code == 200
            assert client.get(
                "/api/v1/warehouse/store-data/preview",
                params={"store_id": 7, "dataset": "overview"},
            ).status_code == 403
            forbidden = client.get(
                "/api/v1/warehouse/store-data/preview",
                params={"store_id": 8, "dataset": "overview"},
            )
            assert forbidden.status_code == 403

            assert client.post("/api/v1/auth/logout").status_code == 204
            assert client.post(
                "/api/v1/auth/login",
                json={"username": "owner", "password": "owner-password-123"},
            ).status_code == 200
            monkeypatch.setattr(store_data, "MAX_EXPORT_ROWS", 1)
            limited = client.get(
                "/api/v1/warehouse/store-data/export",
                params={"store_id": 7, "dataset": "overview", "format": "csv"},
            )
            assert limited.status_code == 413
    finally:
        _restore_settings(original)


def test_collection_health_separates_browser_and_cookie_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "collection-health.sqlite3"
    _seed_database(database_path)
    original = _set_database(database_path)
    original_source = settings.tmall_session_source
    original_cookie_env = settings.tmall_cookie_env
    object.__setattr__(settings, "tmall_session_source", "env")
    object.__setattr__(settings, "tmall_cookie_env", "STORE_DATA_TEST_COOKIE")
    monkeypatch.setenv("STORE_DATA_TEST_COOKIE", "session=a; token=b")
    monkeypatch.setattr(collection, "_browser_probe", lambda _port: (False, "浏览器未连接"))
    try:
        with TestClient(create_app()) as client:
            response = client.get("/api/v1/imports/health")
            assert response.status_code == 200
            payload = response.json()
            assert payload["browser_connected"] is False
            assert payload["status"] == "attention"
            assert payload["platforms"][0]["cookie_detected"] is True
    finally:
        object.__setattr__(settings, "tmall_session_source", original_source)
        object.__setattr__(settings, "tmall_cookie_env", original_cookie_env)
        _restore_settings(original)
