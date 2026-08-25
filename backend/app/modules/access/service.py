from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.core.local_database import LocalDatabase
from app.modules.access.catalog import MENU_CODES
from app.modules.access.schemas import AccessUser, MenuRecord, PermissionRecord, RoleRecord


SESSION_COOKIE_NAME = "echomerch_session"
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "123456"

ROLE_CODE_ALIASES = {
    "business_manager": "operations_supervisor",
    "viewer": "operator",
}


def normalize_role_codes(role_codes: list[str]) -> list[str]:
    return sorted({ROLE_CODE_ALIASES.get(role_code, role_code) for role_code in role_codes})


class AccessDenied(RuntimeError):
    pass


class InvalidCredentials(RuntimeError):
    pass


class DuplicateUsername(ValueError):
    pass


@dataclass(frozen=True)
class Principal:
    user_id: int | None
    username: str
    display_name: str
    roles: frozenset[str]
    permissions: frozenset[str]
    menus: frozenset[str]
    store_ids: frozenset[int] | None
    brand_ids: frozenset[str] | None
    is_active: bool = True
    created_at: str | None = None
    updated_at: str | None = None
    last_login_at: str | None = None

    @property
    def is_super_admin(self) -> bool:
        return "super_admin" in self.roles

    def can(self, permission: str) -> bool:
        return self.is_super_admin or permission in self.permissions

    def resolve_store_id(self, requested_store_id: int | None) -> int | None:
        if self.store_ids is None:
            return requested_store_id
        if requested_store_id is None:
            if len(self.store_ids) == 1:
                return next(iter(self.store_ids))
            raise AccessDenied("请选择已授权的店铺后再读取数据。")
        if requested_store_id not in self.store_ids:
            raise AccessDenied("当前账号没有该店铺的数据权限。")
        return requested_store_id

    def allows_store(self, store_id: int) -> bool:
        return self.store_ids is None or store_id in self.store_ids

    def resolve_brand_id(self, requested_brand_id: str | None) -> str | None:
        if self.brand_ids is None:
            return requested_brand_id
        if requested_brand_id is None:
            if len(self.brand_ids) == 1:
                return next(iter(self.brand_ids))
            raise AccessDenied("请选择已授权的品牌后再读取品牌资产。")
        if requested_brand_id not in self.brand_ids:
            raise AccessDenied("当前账号没有该品牌的数据权限。")
        return requested_brand_id

    def allows_brand(self, brand_id: str) -> bool:
        return self.brand_ids is None or brand_id in self.brand_ids

    def as_schema(self) -> AccessUser:
        return AccessUser(
            user_id=self.user_id,
            username=self.username,
            display_name=self.display_name,
            roles=sorted(self.roles),
            permissions=sorted(self.permissions),
            menus=sorted(self.menus),
            store_ids=None if self.store_ids is None else sorted(self.store_ids),
            brand_ids=None if self.brand_ids is None else sorted(self.brand_ids),
            is_active=self.is_active,
            created_at=self.created_at,
            updated_at=self.updated_at,
            last_login_at=self.last_login_at,
        )


def development_principal() -> Principal:
    return Principal(
        user_id=None,
        username="local-development",
        display_name="本地开发模式",
        roles=frozenset({"super_admin"}),
        permissions=frozenset({"*"}),
        menus=MENU_CODES,
        store_ids=None,
        brand_ids=None,
    )


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return "$".join(
        (
            "scrypt",
            "16384",
            "8",
            "1",
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        )
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, encoded_salt, encoded_digest = encoded.split("$")
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(encoded_salt.encode("ascii"))
        expected = base64.urlsafe_b64decode(encoded_digest.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, UnicodeError):
        return False


class AccessControlStore:
    def __init__(self, database_path: Path) -> None:
        self._database = LocalDatabase(database_path)

    def ensure_default_admin(self) -> None:
        """Bootstrap the documented administrator when no super administrator exists."""
        conn = self._database.connect(initialize=True, read_only=False)
        try:
            if conn.execute(
                "select user_id from access_users where username = ?",
                (DEFAULT_ADMIN_USERNAME,),
            ).fetchone() is not None:
                return
            if conn.execute(
                """
                select 1
                from access_users user
                join access_user_roles role on role.user_id = user.user_id
                where user.is_active = 1 and role.role_code = 'super_admin'
                limit 1
                """
            ).fetchone() is not None:
                return
            now = _timestamp()
            cursor = conn.execute(
                """
                insert into access_users (username, display_name, password_hash, is_active, created_at, updated_at)
                values (?, ?, ?, 1, ?, ?)
                """,
                (DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_USERNAME, hash_password(DEFAULT_ADMIN_PASSWORD), now, now),
            )
            conn.execute(
                "insert into access_user_roles (user_id, role_code) values (?, ?)",
                (int(cursor.lastrowid), "super_admin"),
            )
            conn.commit()
        finally:
            conn.close()

    def authenticate(self, username: str, password: str) -> Principal:
        normalized_username = username.strip().lower()
        conn = self._database.connect()
        try:
            row = conn.execute(
                """
                select user_id, username, display_name, password_hash, is_active
                from access_users where username = ?
                """,
                (normalized_username,),
            ).fetchone()
        finally:
            conn.close()
        if row is None or not bool(row["is_active"]) or not verify_password(password, str(row["password_hash"])):
            raise InvalidCredentials("用户名或密码错误。")
        principal = self._principal_for_user(int(row["user_id"]))
        self._record_login(principal.user_id)
        return principal

    def create_session(self, user_id: int, *, session_days: int) -> tuple[str, datetime]:
        token = secrets.token_urlsafe(48)
        session_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        expires_at = now + timedelta(days=session_days)
        conn = self._database.connect(initialize=True, read_only=False)
        try:
            conn.execute(
                """
                insert into access_sessions (session_id, user_id, token_hash, created_at, expires_at, revoked_at, last_seen_at)
                values (?, ?, ?, ?, ?, null, ?)
                """,
                (
                    session_id,
                    user_id,
                    _hash_token(token),
                    now.isoformat(timespec="seconds"),
                    expires_at.isoformat(timespec="seconds"),
                    now.isoformat(timespec="seconds"),
                ),
            )
            self._write_audit(conn, user_id, "auth.login", "session", session_id, "success", None)
            conn.commit()
        finally:
            conn.close()
        return token, expires_at

    def principal_for_token(self, token: str) -> Principal | None:
        conn = self._database.connect()
        try:
            row = conn.execute(
                """
                select s.session_id, s.user_id, s.expires_at, s.revoked_at, u.is_active
                from access_sessions s
                join access_users u on u.user_id = s.user_id
                where s.token_hash = ?
                """,
                (_hash_token(token),),
            ).fetchone()
        finally:
            conn.close()
        if row is None or row["revoked_at"] is not None or not bool(row["is_active"]):
            return None
        expires_at = datetime.fromisoformat(str(row["expires_at"]))
        if expires_at <= datetime.now(UTC):
            return None
        return self._principal_for_user(int(row["user_id"]))

    def revoke_session(self, token: str, actor_user_id: int | None = None) -> None:
        conn = self._database.connect(initialize=True, read_only=False)
        try:
            row = conn.execute(
                "select session_id, user_id from access_sessions where token_hash = ?",
                (_hash_token(token),),
            ).fetchone()
            if row is not None:
                conn.execute(
                    "update access_sessions set revoked_at = ? where session_id = ?",
                    (_timestamp(), row["session_id"]),
                )
                self._write_audit(
                    conn,
                    actor_user_id or int(row["user_id"]),
                    "auth.logout",
                    "session",
                    str(row["session_id"]),
                    "success",
                    None,
                )
            conn.commit()
        finally:
            conn.close()

    def create_user(
        self,
        *,
        username: str,
        display_name: str,
        password: str,
        role_codes: list[str],
        store_ids: list[int],
        brand_ids: list[str] | None = None,
        actor_user_id: int | None = None,
    ) -> AccessUser:
        normalized_username = username.strip().lower()
        requested_roles = normalize_role_codes(role_codes)
        requested_stores = sorted(set(store_ids))
        requested_brands = sorted(set(brand_ids or []))
        if not normalized_username or not requested_roles:
            raise ValueError("账号和至少一个角色为必填项。")
        conn = self._database.connect(initialize=True, read_only=False)
        try:
            existing = conn.execute(
                "select 1 from access_users where username = ?", (normalized_username,)
            ).fetchone()
            if existing is not None:
                raise DuplicateUsername("该用户名已存在。")
            roles, scoped_stores, scoped_brands = self._validate_user_assignment(
                conn,
                role_codes=requested_roles,
                store_ids=requested_stores,
                brand_ids=requested_brands,
            )
            now = _timestamp()
            cursor = conn.execute(
                """
                insert into access_users (username, display_name, password_hash, is_active, created_at, updated_at)
                values (?, ?, ?, 1, ?, ?)
                """,
                (normalized_username, display_name.strip(), hash_password(password), now, now),
            )
            user_id = int(cursor.lastrowid)
            conn.executemany(
                "insert into access_user_roles (user_id, role_code) values (?, ?)",
                ((user_id, role_code) for role_code in requested_roles),
            )
            if scoped_stores:
                conn.executemany(
                    "insert into access_user_store_scopes (user_id, store_id) values (?, ?)",
                    ((user_id, store_id) for store_id in scoped_stores),
                )
            if scoped_brands:
                conn.executemany(
                    "insert into access_user_brand_scopes (user_id, \"品牌ID\") values (?, ?)",
                    ((user_id, brand_id) for brand_id in scoped_brands),
                )
            self._write_audit(
                conn,
                actor_user_id,
                "access.user.create",
                "user",
                str(user_id),
                "success",
                f"roles={','.join(requested_roles)}; stores={','.join(str(value) for value in requested_stores)}; brands={','.join(requested_brands)}",
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return self._principal_for_user(user_id).as_schema()

    def update_user(
        self,
        *,
        user_id: int,
        display_name: str,
        role_codes: list[str],
        store_ids: list[int],
        brand_ids: list[str] | None = None,
        actor_user_id: int | None = None,
    ) -> AccessUser:
        normalized_roles = normalize_role_codes(role_codes)
        normalized_stores = sorted(set(store_ids))
        normalized_brands = sorted(set(brand_ids or []))
        normalized_name = display_name.strip()
        if not normalized_name or not normalized_roles:
            raise ValueError("显示名称和至少一个角色为必填项。")

        conn = self._database.connect(initialize=True, read_only=False)
        try:
            target = self._user_row(conn, user_id)
            roles, scoped_stores, scoped_brands = self._validate_user_assignment(
                conn,
                role_codes=normalized_roles,
                store_ids=normalized_stores,
                brand_ids=normalized_brands,
            )
            if bool(target["is_active"]) and self._is_last_active_super_admin(conn, user_id) and "super_admin" not in roles:
                raise ValueError("系统至少需要保留一个有效的超级管理员。")

            now = _timestamp()
            conn.execute(
                "update access_users set display_name = ?, updated_at = ? where user_id = ?",
                (normalized_name, now, user_id),
            )
            conn.execute("delete from access_user_roles where user_id = ?", (user_id,))
            conn.executemany(
                "insert into access_user_roles (user_id, role_code) values (?, ?)",
                ((user_id, role_code) for role_code in roles),
            )
            conn.execute("delete from access_user_store_scopes where user_id = ?", (user_id,))
            if scoped_stores:
                conn.executemany(
                    "insert into access_user_store_scopes (user_id, store_id) values (?, ?)",
                    ((user_id, store_id) for store_id in scoped_stores),
                )
            conn.execute("delete from access_user_brand_scopes where user_id = ?", (user_id,))
            if scoped_brands:
                conn.executemany(
                    "insert into access_user_brand_scopes (user_id, \"品牌ID\") values (?, ?)",
                    ((user_id, brand_id) for brand_id in scoped_brands),
                )
            self._write_audit(
                conn,
                actor_user_id,
                "access.user.update",
                "user",
                str(user_id),
                "success",
                f"roles={','.join(roles)}; stores={','.join(str(value) for value in scoped_stores)}; brands={','.join(scoped_brands)}",
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return self._principal_for_user(user_id).as_schema()

    def set_user_active(
        self,
        *,
        user_id: int,
        is_active: bool,
        actor_user_id: int | None,
    ) -> AccessUser:
        conn = self._database.connect(initialize=True, read_only=False)
        try:
            target = self._user_row(conn, user_id)
            currently_active = bool(target["is_active"])
            if currently_active == is_active:
                return self._principal_for_user(user_id).as_schema()
            if not is_active and self._is_last_active_super_admin(conn, user_id):
                raise ValueError("系统至少需要保留一个有效的超级管理员。")

            now = _timestamp()
            conn.execute(
                "update access_users set is_active = ?, updated_at = ? where user_id = ?",
                (int(is_active), now, user_id),
            )
            if not is_active:
                conn.execute(
                    "update access_sessions set revoked_at = ? where user_id = ? and revoked_at is null",
                    (now, user_id),
                )
            self._write_audit(
                conn,
                actor_user_id,
                "access.user.activate" if is_active else "access.user.deactivate",
                "user",
                str(user_id),
                "success",
                None,
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return self._principal_for_user(user_id, include_inactive=True).as_schema()

    def reset_user_password(
        self,
        *,
        user_id: int,
        password: str,
        actor_user_id: int | None,
    ) -> AccessUser:
        conn = self._database.connect(initialize=True, read_only=False)
        try:
            self._user_row(conn, user_id)
            now = _timestamp()
            conn.execute(
                "update access_users set password_hash = ?, updated_at = ? where user_id = ?",
                (hash_password(password), now, user_id),
            )
            conn.execute(
                "update access_sessions set revoked_at = ? where user_id = ? and revoked_at is null",
                (now, user_id),
            )
            self._write_audit(conn, actor_user_id, "access.user.reset_password", "user", str(user_id), "success", None)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return self._principal_for_user(user_id).as_schema()

    def change_own_password(
        self,
        *,
        user_id: int,
        current_password: str,
        new_password: str,
    ) -> None:
        """Verify the current password, replace it, and revoke every session."""

        conn = self._database.connect(initialize=True, read_only=False)
        try:
            row = conn.execute(
                "select password_hash from access_users where user_id = ? and is_active = 1",
                (user_id,),
            ).fetchone()
            if row is None or not verify_password(current_password, str(row["password_hash"])):
                raise InvalidCredentials("当前密码不正确。")
            if verify_password(new_password, str(row["password_hash"])):
                raise ValueError("新密码不能与当前密码相同。")
            now = _timestamp()
            conn.execute(
                "update access_users set password_hash = ?, updated_at = ? where user_id = ?",
                (hash_password(new_password), now, user_id),
            )
            conn.execute(
                "update access_sessions set revoked_at = ? where user_id = ? and revoked_at is null",
                (now, user_id),
            )
            self._write_audit(
                conn,
                user_id,
                "auth.change_password",
                "user",
                str(user_id),
                "success",
                None,
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def list_directory(self) -> tuple[list[AccessUser], list[RoleRecord], list[PermissionRecord], list[MenuRecord]]:
        conn = self._database.connect()
        try:
            user_ids = [int(row["user_id"]) for row in conn.execute("select user_id from access_users order by user_id").fetchall()]
            roles = [
                RoleRecord(
                    code=str(row["role_code"]),
                    name=str(row["role_name"]),
                    description=str(row["description"]),
                    permissions=[
                        str(permission["permission_code"])
                        for permission in conn.execute(
                            "select permission_code from access_role_permissions where role_code = ? order by permission_code",
                            (row["role_code"],),
                        ).fetchall()
                    ],
                    menus=[
                        str(menu["menu_code"])
                        for menu in conn.execute(
                            "select menu_code from access_role_menus where role_code = ? order by menu_code",
                            (row["role_code"],),
                        ).fetchall()
                    ],
                )
                for row in conn.execute(
                    """
                    select role_code, role_name, description from access_roles
                    order by case role_code
                        when 'super_admin' then 1
                        when 'admin' then 2
                        when 'operations_supervisor' then 3
                        when 'store_manager' then 4
                        when 'operator' then 5
                        else 99 end, role_code
                    """
                ).fetchall()
            ]
            permissions = [
                PermissionRecord(
                    code=str(row["permission_code"]),
                    name=str(row["permission_name"]),
                    description=str(row["description"]),
                )
                for row in conn.execute(
                    "select permission_code, permission_name, description from access_permissions order by permission_code"
                ).fetchall()
            ]
            menus = [
                MenuRecord(
                    code=str(row["menu_code"]),
                    parent_code=str(row["parent_code"]) if row["parent_code"] else None,
                    name=str(row["menu_name"]),
                    menu_type=str(row["menu_type"]),
                    path=str(row["path"]),
                    component=str(row["component"]),
                    permission=str(row["permission_code"]) if row["permission_code"] else None,
                    order=int(row["sort_order"]),
                    hidden=bool(row["is_hidden"]),
                )
                for row in conn.execute(
                    """
                    select menu_code, parent_code, menu_name, menu_type, path, component,
                           permission_code, sort_order, is_hidden
                    from access_menus order by sort_order, menu_code
                    """
                ).fetchall()
            ]
        finally:
            conn.close()
        return [self._principal_for_user(user_id, include_inactive=True).as_schema() for user_id in user_ids], roles, permissions, menus

    def update_role_access(
        self,
        *,
        role_code: str,
        permission_codes: list[str],
        menu_codes: list[str],
        actor_user_id: int | None,
    ) -> RoleRecord:
        requested_permissions = sorted(set(permission_codes))
        requested_menus = set(menu_codes)
        conn = self._database.connect(initialize=True, read_only=False)
        try:
            role = conn.execute(
                "select role_code, role_name, description from access_roles where role_code = ?",
                (role_code,),
            ).fetchone()
            if role is None:
                raise ValueError("角色不存在。")
            if role_code == "super_admin":
                raise ValueError("超级管理员始终拥有全部权限，无需调整。")

            existing_permissions = {
                str(row["permission_code"])
                for row in conn.execute(
                    f"select permission_code from access_permissions where permission_code in ({','.join('?' for _ in requested_permissions)})",
                    requested_permissions,
                ).fetchall()
            } if requested_permissions else set()
            if existing_permissions != set(requested_permissions):
                raise ValueError("包含不存在的功能权限代码。")

            menu_rows = conn.execute(
                f"select menu_code, parent_code, permission_code from access_menus where menu_code in ({','.join('?' for _ in requested_menus)})",
                sorted(requested_menus),
            ).fetchall() if requested_menus else []
            if {str(row["menu_code"]) for row in menu_rows} != requested_menus:
                raise ValueError("包含不存在的菜单代码。")
            required_permissions = {
                str(row["permission_code"])
                for row in menu_rows
                if row["permission_code"] is not None
            }
            if not required_permissions.issubset(existing_permissions):
                raise ValueError("菜单授权所需的功能权限尚未勾选。")
            requested_menus.update(
                str(row["parent_code"])
                for row in menu_rows
                if row["parent_code"] is not None
            )

            conn.execute("delete from access_role_permissions where role_code = ?", (role_code,))
            conn.executemany(
                "insert into access_role_permissions (role_code, permission_code) values (?, ?)",
                ((role_code, code) for code in requested_permissions),
            )
            conn.execute("delete from access_role_menus where role_code = ?", (role_code,))
            conn.executemany(
                "insert into access_role_menus (role_code, menu_code) values (?, ?)",
                ((role_code, code) for code in sorted(requested_menus)),
            )
            self._write_audit(
                conn,
                actor_user_id,
                "access.role.authorize",
                "role",
                role_code,
                "success",
                f"permissions={','.join(requested_permissions)}; menus={','.join(sorted(requested_menus))}",
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        _, roles, _, _ = self.list_directory()
        return next(item for item in roles if item.code == role_code)

    def _record_login(self, user_id: int | None) -> None:
        if user_id is None:
            return
        conn = self._database.connect(initialize=True, read_only=False)
        try:
            conn.execute(
                "update access_users set last_login_at = ?, updated_at = ? where user_id = ?",
                (_timestamp(), _timestamp(), user_id),
            )
            conn.commit()
        finally:
            conn.close()

    def _principal_for_user(self, user_id: int, *, include_inactive: bool = False) -> Principal:
        conn = self._database.connect()
        try:
            user = conn.execute(
                """
                select user_id, username, display_name, is_active, created_at, updated_at, last_login_at
                from access_users where user_id = ?
                """,
                (user_id,),
            ).fetchone()
            if user is None or (not include_inactive and not bool(user["is_active"])):
                raise InvalidCredentials("账号不可用。")
            roles = frozenset(
                str(row["role_code"])
                for row in conn.execute(
                    "select role_code from access_user_roles where user_id = ?",
                    (user_id,),
                ).fetchall()
            )
            permissions = frozenset(
                str(row["permission_code"])
                for row in conn.execute(
                    """
                    select distinct permission_code from access_role_permissions
                    where role_code in (select role_code from access_user_roles where user_id = ?)
                    """,
                    (user_id,),
                ).fetchall()
            )
            menus = frozenset(
                str(row["menu_code"])
                for row in conn.execute(
                    """
                    select distinct menu_code from access_role_menus
                    where role_code in (select role_code from access_user_roles where user_id = ?)
                    """,
                    (user_id,),
                ).fetchall()
            )
            store_ids = frozenset(
                int(row["store_id"])
                for row in conn.execute(
                    "select store_id from access_user_store_scopes where user_id = ?",
                    (user_id,),
                ).fetchall()
            )
            brand_ids = frozenset(
                str(row["品牌ID"])
                for row in conn.execute(
                    "select \"品牌ID\" from access_user_brand_scopes where user_id = ?",
                    (user_id,),
                ).fetchall()
            )
        finally:
            conn.close()
        return Principal(
            user_id=int(user["user_id"]),
            username=str(user["username"]),
            display_name=str(user["display_name"]),
            roles=roles,
            permissions=permissions,
            menus=MENU_CODES if "super_admin" in roles else menus,
            store_ids=None if "super_admin" in roles else store_ids,
            brand_ids=None if "super_admin" in roles else brand_ids,
            is_active=bool(user["is_active"]),
            created_at=str(user["created_at"]),
            updated_at=str(user["updated_at"]),
            last_login_at=str(user["last_login_at"]) if user["last_login_at"] else None,
        )

    @staticmethod
    def _user_row(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row:
        row = conn.execute(
            "select user_id, is_active from access_users where user_id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            raise ValueError("账号不存在。")
        return row

    @staticmethod
    def _validate_user_assignment(
        conn: sqlite3.Connection,
        *,
        role_codes: list[str],
        store_ids: list[int],
        brand_ids: list[str],
    ) -> tuple[set[str], list[int], list[str]]:
        roles = {
            str(row["role_code"])
            for row in conn.execute(
                f"select role_code from access_roles where role_code in ({','.join('?' for _ in role_codes)})",
                role_codes,
            ).fetchall()
        }
        if roles != set(role_codes):
            raise ValueError("包含不存在的角色代码。")
        if "super_admin" not in roles and not store_ids and not brand_ids:
            raise ValueError("非超级管理员必须至少授权一个店铺或品牌。")
        if store_ids:
            store_count = conn.execute(
                f"select count(*) from stores where \"店铺ID\" in ({','.join('?' for _ in store_ids)})",
                store_ids,
            ).fetchone()[0]
            if int(store_count) != len(store_ids):
                raise ValueError("包含不存在的店铺 ID。")
        if brand_ids:
            brand_count = conn.execute(
                f"select count(*) from brands where \"品牌ID\" in ({','.join('?' for _ in brand_ids)})",
                brand_ids,
            ).fetchone()[0]
            if int(brand_count) != len(brand_ids):
                raise ValueError("包含不存在的品牌 ID。")
        return (
            roles,
            [] if "super_admin" in roles else store_ids,
            [] if "super_admin" in roles else brand_ids,
        )

    @staticmethod
    def _is_last_active_super_admin(conn: sqlite3.Connection, user_id: int) -> bool:
        target_is_admin = conn.execute(
            "select 1 from access_user_roles where user_id = ? and role_code = 'super_admin'",
            (user_id,),
        ).fetchone()
        if target_is_admin is None:
            return False
        active_admins = conn.execute(
            """
            select count(*) from access_users user
            join access_user_roles role on role.user_id = user.user_id
            where user.is_active = 1 and role.role_code = 'super_admin'
            """
        ).fetchone()[0]
        return int(active_admins) <= 1

    @staticmethod
    def _write_audit(
        conn: sqlite3.Connection,
        actor_user_id: int | None,
        action_code: str,
        target_type: str,
        target_id: str | None,
        outcome: str,
        detail: str | None,
    ) -> None:
        conn.execute(
            """
            insert into access_audit_logs (actor_user_id, action_code, target_type, target_id, outcome, detail, created_at)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (actor_user_id, action_code, target_type, target_id, outcome, detail, _timestamp()),
        )
