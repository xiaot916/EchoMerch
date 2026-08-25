from pathlib import Path

import pytest

from app.core.local_database import LocalDatabase
from app.modules.access.service import AccessDenied, AccessControlStore, DuplicateUsername, InvalidCredentials
from app.modules.imports.crawl_run_store import CrawlRunStore


def test_access_control_bootstraps_default_admin_without_overwriting_it(tmp_path: Path) -> None:
    database_path = tmp_path / "access.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    store = AccessControlStore(database_path)

    store.ensure_default_admin()
    admin = store.authenticate("admin", "123456")
    assert admin.display_name == "admin"
    assert admin.roles == frozenset({"super_admin"})

    store.ensure_default_admin()
    users, _, _, _ = store.list_directory()
    assert [user.username for user in users] == ["admin"]

    store.create_user(
        username="owner",
        display_name="Owner",
        password="owner-password-123",
        role_codes=["super_admin"],
        store_ids=[],
        actor_user_id=admin.user_id,
    )
    store.ensure_default_admin()
    users, _, _, _ = store.list_directory()
    assert [user.username for user in users] == ["admin", "owner"]


def test_access_control_does_not_bootstrap_admin_when_super_admin_exists(tmp_path: Path) -> None:
    database_path = tmp_path / "access.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    store = AccessControlStore(database_path)
    store.create_user(
        username="owner",
        display_name="Owner",
        password="owner-password-123",
        role_codes=["super_admin"],
        store_ids=[],
        actor_user_id=None,
    )

    store.ensure_default_admin()
    users, _, _, _ = store.list_directory()
    assert [user.username for user in users] == ["owner"]


def test_access_control_issues_revocable_session_and_scopes(tmp_path: Path) -> None:
    database_path = tmp_path / "access.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    CrawlRunStore(database_path).ensure_store_reference(
        store_id=7,
        store_name="测试店铺",
        platform_store_id="shop-7",
    )
    store = AccessControlStore(database_path)

    admin = store.create_user(
        username="owner",
        display_name="Owner",
        password="owner-password-123",
        role_codes=["super_admin"],
        store_ids=[],
        actor_user_id=None,
    )
    assert admin.store_ids is None

    viewer = store.create_user(
        username="operator",
        display_name="Operator",
        password="operator-password-123",
        role_codes=["operator"],
        store_ids=[7],
        actor_user_id=admin.user_id,
    )
    assert viewer.store_ids == [7]

    principal = store.authenticate("operator", "operator-password-123")
    assert principal.can("analytics.read")
    assert not principal.can("imports.manage")
    assert not principal.can("data.manage")
    assert not principal.can("system.manage")
    assert principal.resolve_store_id(None) == 7
    with pytest.raises(AccessDenied):
        principal.resolve_store_id(8)

    token, _ = store.create_session(principal.user_id or 0, session_days=1)
    assert store.principal_for_token(token) is not None
    store.revoke_session(token, actor_user_id=principal.user_id)
    assert store.principal_for_token(token) is None


def test_access_control_rejects_duplicate_usernames(tmp_path: Path) -> None:
    database_path = tmp_path / "access.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    store = AccessControlStore(database_path)
    store.create_user(
        username="owner",
        display_name="Owner",
        password="owner-password-123",
        role_codes=["super_admin"],
        store_ids=[],
        actor_user_id=None,
    )
    with pytest.raises(DuplicateUsername):
        store.create_user(
            username="OWNER",
            display_name="Other",
            password="other-password-123",
            role_codes=["super_admin"],
            store_ids=[],
            actor_user_id=None,
        )


def test_access_control_updates_role_menu_and_function_access(tmp_path: Path) -> None:
    database_path = tmp_path / "access.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    store = AccessControlStore(database_path)

    updated = store.update_role_access(
        role_code="operator",
        permission_codes=["analytics.read"],
        menu_codes=["route:product-analysis"],
        actor_user_id=None,
    )

    assert updated.permissions == ["analytics.read"]
    assert updated.menus == ["domain:products", "route:product-analysis"]
    with pytest.raises(ValueError, match="功能权限"):
        store.update_role_access(
            role_code="operator",
            permission_codes=[],
            menu_codes=["route:product-analysis"],
            actor_user_id=None,
        )


def test_access_control_updates_account_lifecycle_and_revokes_sessions(tmp_path: Path) -> None:
    database_path = tmp_path / "access.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    CrawlRunStore(database_path).ensure_store_reference(
        store_id=7,
        store_name="测试店铺",
        platform_store_id="shop-7",
    )
    store = AccessControlStore(database_path)
    admin = store.create_user(
        username="owner",
        display_name="Owner",
        password="owner-password-123",
        role_codes=["super_admin"],
        store_ids=[],
        actor_user_id=None,
    )
    viewer = store.create_user(
        username="operator",
        display_name="Operator",
        password="operator-password-123",
        role_codes=["operator"],
        store_ids=[7],
        actor_user_id=admin.user_id,
    )
    assert viewer.user_id is not None

    session, _ = store.create_session(viewer.user_id, session_days=1)
    updated = store.update_user(
        user_id=viewer.user_id,
        display_name="运营用户",
        role_codes=["operator"],
        store_ids=[7],
        actor_user_id=admin.user_id,
    )
    assert updated.display_name == "运营用户"
    assert updated.roles == ["operator"]
    assert "analytics.read" in updated.permissions
    assert "imports.manage" not in updated.permissions
    assert store.principal_for_token(session) is not None

    reset = store.reset_user_password(
        user_id=viewer.user_id,
        password="reset-password-123",
        actor_user_id=admin.user_id,
    )
    assert reset.is_active
    assert store.principal_for_token(session) is None
    with pytest.raises(InvalidCredentials):
        store.authenticate("operator", "operator-password-123")
    assert store.authenticate("operator", "reset-password-123").username == "operator"

    disabled = store.set_user_active(user_id=viewer.user_id, is_active=False, actor_user_id=admin.user_id)
    assert not disabled.is_active
    with pytest.raises(InvalidCredentials):
        store.authenticate("operator", "reset-password-123")

    assert admin.user_id is not None
    with pytest.raises(ValueError, match="至少需要保留"):
        store.set_user_active(user_id=admin.user_id, is_active=False, actor_user_id=admin.user_id)


def test_access_control_changes_own_password_and_revokes_all_sessions(tmp_path: Path) -> None:
    database_path = tmp_path / "change-own-password.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    CrawlRunStore(database_path).ensure_store_reference(
        store_id=7,
        store_name="测试店铺",
        platform_store_id="shop-7",
    )
    store = AccessControlStore(database_path)
    user = store.create_user(
        username="operator",
        display_name="Operator",
        password="operator-password-123",
        role_codes=["operator"],
        store_ids=[7],
        actor_user_id=None,
    )
    assert user.user_id is not None

    first_session, _ = store.create_session(user.user_id, session_days=1)
    second_session, _ = store.create_session(user.user_id, session_days=1)

    with pytest.raises(InvalidCredentials, match="当前密码不正确"):
        store.change_own_password(
            user_id=user.user_id,
            current_password="wrong-password",
            new_password="new-password-456",
        )
    assert store.principal_for_token(first_session) is not None

    with pytest.raises(ValueError, match="不能与当前密码相同"):
        store.change_own_password(
            user_id=user.user_id,
            current_password="operator-password-123",
            new_password="operator-password-123",
        )
    assert store.principal_for_token(second_session) is not None

    store.change_own_password(
        user_id=user.user_id,
        current_password="operator-password-123",
        new_password="new-password-456",
    )

    assert store.principal_for_token(first_session) is None
    assert store.principal_for_token(second_session) is None
    with pytest.raises(InvalidCredentials):
        store.authenticate("operator", "operator-password-123")
    assert store.authenticate("operator", "new-password-456").username == "operator"
