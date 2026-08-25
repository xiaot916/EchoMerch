from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.local_database import LocalDatabase
from app.main import create_app
from app.modules.access.schemas import CreateUserRequest, LoginRequest
from app.modules.access.service import AccessControlStore
from app.modules.imports.crawl_run_store import CrawlRunStore


def _set_auth_settings(database_path: Path) -> dict[str, object]:
    original = {
        "local_database_path": settings.local_database_path,
        "auth_enabled": settings.auth_enabled,
        "auth_cookie_secure": settings.auth_cookie_secure,
    }
    object.__setattr__(settings, "local_database_path", str(database_path))
    object.__setattr__(settings, "auth_enabled", True)
    object.__setattr__(settings, "auth_cookie_secure", False)
    return original


def _restore_auth_settings(original: dict[str, object]) -> None:
    for key, value in original.items():
        object.__setattr__(settings, key, value)


def test_two_character_username_is_valid_for_creation_and_login() -> None:
    assert CreateUserRequest(
        username="赵岩",
        display_name="数据运营",
        password="123456",
        role_codes=["operator"],
        store_ids=[1],
    ).username == "赵岩"
    assert LoginRequest(username="赵岩", password="123456").username == "赵岩"


def test_http_auth_and_store_scope_are_enforced(tmp_path: Path) -> None:
    database_path = tmp_path / "api-access.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    CrawlRunStore(database_path).ensure_store_reference(
        store_id=7,
        store_name="授权店铺",
        platform_store_id="platform-7",
    )
    CrawlRunStore(database_path).ensure_store_reference(
        store_id=8,
        store_name="未授权店铺",
        platform_store_id="platform-8",
    )
    access = AccessControlStore(database_path)
    access.create_user(
        username="operator",
        display_name="运营用户",
        password="operator-password-123",
        role_codes=["operator"],
        store_ids=[7],
        actor_user_id=None,
    )

    original = _set_auth_settings(database_path)
    try:
        with TestClient(create_app()) as client:
            assert client.get("/api/v1/warehouse/stores").status_code == 401

            login = client.post(
                "/api/v1/auth/login",
                json={"username": "operator", "password": "operator-password-123"},
            )
            assert login.status_code == 200
            assert login.json()["user"]["store_ids"] == [7]

            stores = client.get("/api/v1/warehouse/stores")
            assert stores.status_code == 200
            assert [item["store_id"] for item in stores.json()] == [7]

            assert client.get("/api/v1/access/directory").status_code == 403
            assert client.get("/api/v1/access/api-permissions").status_code == 403
            assert client.get("/api/v1/imports/overview").status_code == 403
            assert client.get("/api/v1/warehouse/store-data/datasets?store_id=7").status_code == 403
            assert client.get(
                "/api/v1/warehouse/stores/8/daily-overview?day=2026-08-01"
            ).status_code == 403

            assert client.post("/api/v1/auth/logout").status_code == 204
            assert client.get("/api/v1/warehouse/stores").status_code == 401
    finally:
        _restore_auth_settings(original)


def test_super_admin_manages_user_lifecycle_over_http(tmp_path: Path) -> None:
    database_path = tmp_path / "api-access.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    CrawlRunStore(database_path).ensure_store_reference(
        store_id=7,
        store_name="授权店铺",
        platform_store_id="platform-7",
    )
    access = AccessControlStore(database_path)
    admin = access.create_user(
        username="owner",
        display_name="管理员",
        password="owner-password-123",
        role_codes=["super_admin"],
        store_ids=[],
        actor_user_id=None,
    )
    viewer = access.create_user(
        username="operator",
        display_name="运营用户",
        password="operator-password-123",
        role_codes=["operator"],
        store_ids=[7],
        actor_user_id=admin.user_id,
    )
    assert viewer.user_id is not None

    original = _set_auth_settings(database_path)
    try:
        with TestClient(create_app()) as client:
            assert client.post(
                "/api/v1/auth/login",
                json={"username": "owner", "password": "owner-password-123"},
            ).status_code == 200

            directory = client.get("/api/v1/access/directory")
            assert directory.status_code == 200
            assert [item["code"] for item in directory.json()["roles"]] == [
                "super_admin", "admin", "operations_supervisor", "store_manager", "operator"
            ]
            assert any(item["code"] == "data.manage" for item in directory.json()["permissions"])
            assert any(item["code"] == "system.manage" for item in directory.json()["permissions"])
            assert any(item["code"] == "route:overview" for item in directory.json()["menus"])
            # 市场洞察和 AI 配置均作为独立入口纳入权限目录。
            assert any(item["code"] == "route:system-ai" for item in directory.json()["menus"])
            assert len(directory.json()["menus"]) == 46

            role_access = client.put(
                "/api/v1/access/roles/operator/access",
                json={"permission_codes": ["analytics.read"], "menu_codes": ["route:overview"]},
            )
            assert role_access.status_code == 200
            assert role_access.json()["permissions"] == ["analytics.read"]
            assert role_access.json()["menus"] == ["domain:home", "route:overview"]

            api_permissions = client.get("/api/v1/access/api-permissions")
            assert api_permissions.status_code == 200
            permission_records = api_permissions.json()
            assert any(
                item["path"] == "/api/v1/access/api-permissions"
                and item["method"] == "GET"
                and item["permission"] == "system.manage"
                and item["protected"] is True
                for item in permission_records
            )
            assert any(item["permission"] == "data.manage" for item in permission_records)

            two_character_user = client.post(
                "/api/v1/access/users",
                json={
                    "username": "赵岩",
                    "display_name": "数据运营",
                    "password": "operator-password-123",
                    "role_codes": ["operator"],
                    "store_ids": [7],
                },
            )
            assert two_character_user.status_code == 201
            assert two_character_user.json()["username"] == "赵岩"

            updated = client.put(
                f"/api/v1/access/users/{viewer.user_id}",
                json={"display_name": "运营用户", "role_codes": ["operator"], "store_ids": [7]},
            )
            assert updated.status_code == 200
            assert updated.json()["roles"] == ["operator"]
            assert "analytics.read" in updated.json()["permissions"]
            assert "data.manage" not in updated.json()["permissions"]

            reset = client.post(
                f"/api/v1/access/users/{viewer.user_id}/reset-password",
                json={"password": "reset-password-123"},
            )
            assert reset.status_code == 200

            disabled = client.patch(
                f"/api/v1/access/users/{viewer.user_id}/status",
                json={"is_active": False},
            )
            assert disabled.status_code == 200
            assert disabled.json()["is_active"] is False

            assert admin.user_id is not None
            protected = client.patch(
                f"/api/v1/access/users/{admin.user_id}/status",
                json={"is_active": False},
            )
            assert protected.status_code == 400
    finally:
        _restore_auth_settings(original)


def test_user_changes_password_and_must_relogin(tmp_path: Path) -> None:
    database_path = tmp_path / "api-change-password.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    CrawlRunStore(database_path).ensure_store_reference(
        store_id=7,
        store_name="授权店铺",
        platform_store_id="platform-7",
    )
    access = AccessControlStore(database_path)
    access.create_user(
        username="operator",
        display_name="运营用户",
        password="operator-password-123",
        role_codes=["operator"],
        store_ids=[7],
        actor_user_id=None,
    )

    original = _set_auth_settings(database_path)
    try:
        with TestClient(create_app()) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"username": "operator", "password": "operator-password-123"},
            )
            assert login.status_code == 200

            wrong_current = client.post(
                "/api/v1/auth/change-password",
                json={"current_password": "wrong-password", "new_password": "new-password-456"},
            )
            assert wrong_current.status_code == 401
            assert client.get("/api/v1/auth/me").status_code == 200

            unchanged = client.post(
                "/api/v1/auth/change-password",
                json={"current_password": "operator-password-123", "new_password": "operator-password-123"},
            )
            assert unchanged.status_code == 400
            assert client.get("/api/v1/auth/me").status_code == 200

            changed = client.post(
                "/api/v1/auth/change-password",
                json={"current_password": "operator-password-123", "new_password": "new-password-456"},
            )
            assert changed.status_code == 200
            assert changed.json()["relogin_required"] is True
            assert client.get("/api/v1/auth/me").status_code == 401

            assert client.post(
                "/api/v1/auth/login",
                json={"username": "operator", "password": "operator-password-123"},
            ).status_code == 401
            assert client.post(
                "/api/v1/auth/login",
                json={"username": "operator", "password": "new-password-456"},
            ).status_code == 200
    finally:
        _restore_auth_settings(original)
