"""Runtime-only Jackyun inventory adapter and hourly snapshot scheduler.

The platform has deliberately not been hard-coded here: endpoint paths and
credentials vary by tenant.  Configure the URLs and credentials through the
ECHO_JACKYUN_* environment variables.  Tokens never enter SQLite or logs.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import threading
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.core.business_days import SHANGHAI_TZ, today_in_shanghai
from app.core.config import Settings, settings
from app.core.local_database import STORE_ID, q
from app.integrations.jackyun_credentials import CredentialVaultError, load_vault, save_vault
from app.modules.inventory.service import InventoryService


class JackyunIntegrationError(RuntimeError):
    pass


def _safe_error_message(exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        return f"吉客云接口返回 HTTP {exc.code}"
    message = re.sub(r"https?://\S+", "[接口地址]", str(exc))
    return message[:300] or exc.__class__.__name__


def _first_nonempty(value: Any, keys: tuple[str, ...]) -> Any:
    if isinstance(value, dict):
        for key in keys:
            current = value.get(key)
            if current not in (None, ""):
                return current
    return None


def _walk_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _extract_rows(payload: Any, *, package: bool = False) -> list[dict[str, Any]]:
    """Extract row-shaped dictionaries without assuming one tenant response shape."""

    if isinstance(payload, list):
        rows = [item for item in payload if isinstance(item, dict)]
        if rows:
            return rows
    keys = (
        ("components", "componentList", "items", "records", "rows", "list", "data")
        if package else ("items", "records", "rows", "list", "data", "inventoryList", "stockList")
    )
    candidates: list[list[dict[str, Any]]] = []
    for node in _walk_dicts(payload):
        for key in keys:
            child = node.get(key)
            if isinstance(child, list):
                rows = [item for item in child if isinstance(item, dict)]
                if rows:
                    candidates.append(rows)
    if not candidates:
        return []
    if package:
        candidates.sort(key=lambda rows: sum("component" in key.casefold() or "goodsAmount" in key for row in rows for key in row), reverse=True)
    else:
        candidates.sort(key=lambda rows: sum(any(token.casefold() in key.casefold() for token in ("stock", "quantity", "sku", "goods")) for row in rows for key in row), reverse=True)
    return candidates[0]


def _raise_for_platform_error(payload: Any) -> None:
    if not isinstance(payload, dict):
        return
    code = payload.get("code")
    if code in (None, 200, "200", "0", 0):
        return
    message = _first_nonempty(payload, ("msg", "message", "error_description", "error"))
    raise JackyunIntegrationError(f"吉客云库存接口返回业务错误（{code}）：{str(message or '未知错误')[:160]}")


class JackyunClient:
    def __init__(
        self,
        config: Settings = settings,
        *,
        opener: Callable[..., Any] = urlopen,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self.opener = opener
        self.clock = clock
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._refresh_token: str | None = None
        self._token_cache_loaded = False
        self._companion_constants: dict[str, Any] | None = None
        self._credential_values: dict[str, Any] = {}

    @property
    def configured(self) -> bool:
        if not self.config.jackyun_inventory_url:
            return False
        if self.config.jackyun_token:
            return True
        if self.config.jackyun_token_url and any((
            self.config.jackyun_client_id,
            self.config.jackyun_client_secret,
            self.config.jackyun_username,
            self.config.jackyun_password,
        )):
            return True
        try:
            values = self._bootstrap_credentials()
        except JackyunIntegrationError:
            return False
        return bool(str(values.get("refresh_token") or "").strip() or str(values.get("access_token") or "").strip())

    def credential_status(self) -> dict[str, Any]:
        """Return safe, non-secret credential health for the settings UI."""
        try:
            values = self._bootstrap_credentials()
        except JackyunIntegrationError as exc:
            return {
                "configured": False,
                "status": "invalid",
                "source": "vault",
                "refresh_token_configured": False,
                "access_token_configured": False,
                "access_token_expired": False,
                "updated_at": None,
                "detail": str(exc),
            }
        refresh = bool(str(values.get("refresh_token") or "").strip())
        access = bool(str(values.get("access_token") or "").strip() or self.config.jackyun_token)
        compatibility_configured = bool(self.config.jackyun_token_url and any((
            self.config.jackyun_client_id,
            self.config.jackyun_client_secret,
            self.config.jackyun_username,
            self.config.jackyun_password,
        )))
        expires_at = float(values.get("expires_at") or 0)
        expired = bool(expires_at and expires_at <= time.time() + 60)
        source = "environment" if self.config.jackyun_token or compatibility_configured else "vault" if refresh or access else "none"
        updated_at = values.get("updated_at")
        if isinstance(updated_at, (int, float)):
            updated_at = datetime.fromtimestamp(float(updated_at), SHANGHAI_TZ).isoformat(timespec="seconds")
        elif updated_at:
            updated_at = str(updated_at)
        if not self.config.jackyun_inventory_url:
            status, detail = "not_configured", "尚未配置吉客云库存接口地址。"
        elif not self.config.jackyun_token_url and refresh and not self.config.jackyun_token:
            status, detail = "invalid", "已填写 Refresh Token，但未配置 Token 刷新接口地址。"
        elif not refresh and not self.config.jackyun_token and not compatibility_configured:
            status, detail = "not_configured", "尚未配置 Refresh Token，请在此处填写。"
        elif refresh and (not access or expired):
            status, detail = "refresh_required", "Access Token 尚不可用或已过期，下一次库存采集会自动尝试刷新。"
        else:
            status, detail = "ready", "已配置吉客云凭证，库存采集可使用。"
        return {
            "configured": bool(self.config.jackyun_inventory_url and (refresh or self.config.jackyun_token or compatibility_configured)),
            "status": status,
            "source": source,
            "refresh_token_configured": refresh,
            "access_token_configured": access,
            "access_token_expired": expired,
            "updated_at": updated_at,
            "detail": detail,
        }

    def set_refresh_credentials(
        self,
        *,
        refresh_token: str,
        access_token: str | None = None,
        access_token_ttl_seconds: int = 3600,
    ) -> dict[str, Any]:
        refresh = refresh_token.strip()
        if not refresh:
            raise JackyunIntegrationError("Refresh Token 不能为空")
        now = time.time()
        updates: dict[str, Any] = {
            "refresh_token": refresh,
            "updated_at": now,
        }
        if access_token and access_token.strip():
            updates.update({
                "access_token": access_token.strip(),
                "expires_at": now + access_token_ttl_seconds,
            })
        else:
            # A new refresh token must not keep using an access token issued
            # for the previous session. The next request will refresh it.
            updates.update({"access_token": "", "expires_at": 0})
        self._save_credentials(updates)
        self._token_cache_loaded = False
        self._token = None
        self._refresh_token = None
        self._token_expires_at = 0
        return self.credential_status()

    def validate_refresh_credentials(self) -> dict[str, Any]:
        """Force one refresh without exposing either token in the response."""
        self._token_cache_loaded = False
        self._token = None
        self._refresh_token = None
        self._token_expires_at = 0
        self.token(force=True)
        return self.credential_status()

    def _companion_path(self) -> Path | None:
        configured_cache = self.config.jackyun_token_cache_path
        if configured_cache:
            candidate = Path(configured_cache).expanduser()
            if candidate.exists():
                return candidate.with_name("jikey.py") if candidate.name == "token_cache.json" else candidate
        if self.config.jackyun_inventory_url and "web.jackyun.com" not in self.config.jackyun_inventory_url:
            return None
        project_root = Path(__file__).resolve().parents[3]
        candidate = project_root.parent / "Arachne" / "JackyunV5" / "jikey.py"
        return candidate if candidate.exists() else None

    def _load_companion_constants(self) -> dict[str, Any]:
        if self._companion_constants is not None:
            return self._companion_constants
        constants: dict[str, Any] = {}
        path = self._companion_path()
        if path:
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
                names = {"BASE_URL", "APPKEY", "SECRET", "CLIENT_ID", "ATI", "WAREHOUSE_IDS"}
                for node in tree.body:
                    if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                        continue
                    target = node.targets[0]
                    if isinstance(target, ast.Name) and target.id in names:
                        try:
                            constants[target.id] = ast.literal_eval(node.value)
                        except (ValueError, SyntaxError):
                            continue
            except (OSError, SyntaxError, UnicodeError):
                pass
        self._companion_constants = constants
        return constants

    def _token_cache_path(self) -> Path | None:
        if self.config.jackyun_token_cache_path:
            candidate = Path(self.config.jackyun_token_cache_path).expanduser()
            if candidate.exists():
                return candidate
        # The implicit companion cache is a production migration path for the
        # default vault only. Custom vaults used by tests/tenants must remain
        # isolated from another local project's credentials.
        default_vault = (Path(__file__).resolve().parents[3] / "artifacts" / "runtime" / "jackyun_credentials.bin").resolve()
        if self._credentials_path() != default_vault:
            return None
        companion = self._companion_path()
        if companion:
            candidate = companion.with_name("token_cache.json")
            if candidate.exists():
                return candidate
        return None

    def _credentials_path(self) -> Path:
        return Path(self.config.jackyun_credentials_path).expanduser().resolve()

    def _load_credentials(self) -> dict[str, Any]:
        try:
            return load_vault(self._credentials_path())
        except CredentialVaultError as exc:
            raise JackyunIntegrationError(str(exc)) from exc

    def _save_credentials(self, updates: dict[str, Any]) -> None:
        try:
            current = load_vault(self._credentials_path())
            # Empty strings are intentional revocations (for example replacing
            # a refresh token must invalidate the previous access token).
            current.update({key: value for key, value in updates.items() if value is not None})
            save_vault(self._credentials_path(), current)
        except CredentialVaultError as exc:
            raise JackyunIntegrationError(str(exc)) from exc

    def _bootstrap_credentials(self) -> dict[str, Any]:
        """Migrate local cache material and pick up later login refreshes.

        The legacy cache is kept only as an import source. Once a user logs in
        again and that cache receives a newer token pair, copy it into the
        DPAPI vault so restarts continue using the durable encrypted store.
        """
        path = self._credentials_path()
        try:
            existing = load_vault(path)
        except CredentialVaultError as exc:
            raise JackyunIntegrationError(str(exc)) from exc
        legacy: dict[str, Any] = {}
        cache_path = self._token_cache_path()
        if cache_path:
            try:
                raw = json.loads(cache_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    legacy.update({key: raw.get(key) for key in ("access_token", "refresh_token", "expires_at", "updated_at", "user_id", "member_name")})
            except (OSError, UnicodeError, json.JSONDecodeError):
                pass
        if existing:
            legacy_updated = float(legacy.get("updated_at") or 0)
            stored_updated = float(existing.get("updated_at") or 0)
            # updated_at is emitted by the login helper. For older caches that
            # lack it, the file mtime still lets a later login be imported.
            cache_newer = False
            if cache_path and not legacy_updated:
                try:
                    cache_newer = cache_path.stat().st_mtime > path.stat().st_mtime
                except OSError:
                    cache_newer = False
            if legacy.get("refresh_token") and (legacy_updated > stored_updated or cache_newer):
                updates = {key: value for key, value in legacy.items() if value not in (None, "", [])}
                try:
                    save_vault(path, {**existing, **updates})
                    existing = {**existing, **updates}
                except CredentialVaultError as exc:
                    raise JackyunIntegrationError(str(exc)) from exc
            return existing
        constants = self._load_companion_constants()
        legacy.update({
            "appkey": self._constant(self.config.jackyun_appkey, "APPKEY"),
            "ati": self._constant(self.config.jackyun_ati, "ATI"),
            "signature_secret": self._constant(self.config.jackyun_signature_secret, "SECRET"),
            "client_id": self._constant(self.config.jackyun_client_id, "CLIENT_ID"),
            "warehouse_ids": self._warehouse_ids(),
            "token_url": self.config.jackyun_token_url,
            "inventory_url": self.config.jackyun_inventory_url,
            "package_url": self.config.jackyun_package_url,
            "package_detail_url": self.config.jackyun_package_detail_url,
            "goods_url": self.config.jackyun_goods_url,
        })
        legacy = {key: value for key, value in legacy.items() if value not in (None, "", [])}
        if legacy:
            try:
                save_vault(path, legacy)
            except CredentialVaultError as exc:
                raise JackyunIntegrationError(str(exc)) from exc
        return legacy

    def _constant(self, configured: Any, name: str) -> Any:
        aliases = {"SECRET": "signature_secret", "CLIENT_ID": "client_id", "APPKEY": "appkey", "ATI": "ati"}
        return configured or self._credential_values.get(aliases.get(name, name.casefold())) or self._credential_values.get(name) or self._load_companion_constants().get(name)

    def _warehouse_ids(self) -> list[str]:
        configured = [str(value).strip() for value in self.config.jackyun_warehouse_ids if str(value).strip()]
        if configured:
            return configured
        stored = self._credential_values.get("warehouse_ids")
        if isinstance(stored, list) and stored:
            return [str(value).strip() for value in stored if str(value).strip()]
        raw = self._load_companion_constants().get("WAREHOUSE_IDS")
        return [value.strip() for value in str(raw or "").split(",") if value.strip()]

    def token(self, *, force: bool = False) -> str:
        if self.config.jackyun_token and not self.config.jackyun_token_url:
            return self.config.jackyun_token
        self._load_cached_token()
        if not force and self._token and self.clock() < self._token_expires_at - 60:
            return self._token
        if self.config.jackyun_token and not force:
            return self.config.jackyun_token
        if not self._refresh_token and not force and any((self.config.jackyun_client_id, self.config.jackyun_client_secret, self.config.jackyun_username, self.config.jackyun_password)):
            return self._request_compatibility_token()
        if not self._refresh_token and force and any((self.config.jackyun_client_id, self.config.jackyun_client_secret, self.config.jackyun_username, self.config.jackyun_password)):
            return self._request_compatibility_token()
        if not self.config.jackyun_token_url or not self._refresh_token:
            raise JackyunIntegrationError("未找到可用的吉客云 Refresh Token，请先登录吉客云或配置 ECHO_JACKYUN_TOKEN_CACHE_PATH")
        self._refresh_access_token()
        if not self._token:
            raise JackyunIntegrationError("吉客云 Token 刷新响应中没有 access_token")
        return self._token

    def _request_compatibility_token(self) -> str:
        """Support tenants that expose OAuth-style token issuance instead of V5 refresh."""
        payload = {
            key: value for key, value in {
                "client_id": self.config.jackyun_client_id,
                "client_secret": self.config.jackyun_client_secret,
                "username": self.config.jackyun_username,
                "password": self.config.jackyun_password,
                "grant_type": "password" if self.config.jackyun_username else "client_credentials",
            }.items() if value
        }
        response = self._open_json(self.config.jackyun_token_url or "", payload, headers={})
        _raise_for_platform_error(response)
        token = next((candidate for node in _walk_dicts(response) for candidate in (
            _first_nonempty(node, ("access_token", "accessToken", "token", "jwt")),
        ) if candidate), None)
        if not token:
            raise JackyunIntegrationError("吉客云 Token 响应中没有 access_token/token")
        expires_in = next((candidate for node in _walk_dicts(response) for candidate in (
            _first_nonempty(node, ("expires_in", "expiresIn", "expireSeconds")),
        ) if candidate not in (None, "")), self.config.jackyun_token_ttl_seconds)
        try:
            ttl = max(60, min(int(float(expires_in)), self.config.jackyun_token_ttl_seconds))
        except (TypeError, ValueError):
            ttl = self.config.jackyun_token_ttl_seconds
        self._token = str(token)
        self._token_expires_at = self.clock() + ttl
        return self._token

    def _load_cached_token(self) -> None:
        if self._token_cache_loaded:
            return
        self._token_cache_loaded = True
        cache = self._bootstrap_credentials()
        self._credential_values = cache
        self._refresh_token = str(cache.get("refresh_token") or "") or None
        cached_token = str(cache.get("access_token") or "") or None
        expires_at = float(cache.get("expires_at") or 0)
        remaining = expires_at - time.time()
        if cached_token and remaining > 60:
            self._token = cached_token
            self._token_expires_at = self.clock() + min(remaining, self.config.jackyun_token_ttl_seconds)

    def _refresh_access_token(self) -> None:
        url = self.config.jackyun_token_url or ""
        access = self._token
        headers = self._web_headers(
            module_code="mainframe",
            referer=f"{self._base_url()}/home/mainframe_web.html",
            content_type="application/x-www-form-urlencoded; charset=UTF-8",
        )
        if self._constant(self.config.jackyun_client_id, "CLIENT_ID"):
            client_id = str(self._constant(self.config.jackyun_client_id, "CLIENT_ID"))
            headers["clientId"] = client_id
            headers["clientid"] = client_id
        if access:
            headers["Authorization"] = f"Bearer {access}"
        payload = {"refreshToken": self._refresh_token or ""}
        response = self._open_form(url, payload, headers=headers)
        _raise_for_platform_error(response)
        token_node = next((node for node in _walk_dicts(response) if _first_nonempty(node, ("access_token", "accessToken", "token"))), {})
        token = _first_nonempty(token_node, ("access_token", "accessToken", "token"))
        if not token:
            raise JackyunIntegrationError("吉客云 Refresh Token 已失效或响应中没有 access_token")
        expires_in = _first_nonempty(token_node, ("expires_in", "expiresIn", "expireSeconds")) or 7200
        try:
            ttl = max(60, min(int(float(expires_in)), self.config.jackyun_token_ttl_seconds))
        except (TypeError, ValueError):
            ttl = self.config.jackyun_token_ttl_seconds
        self._token = str(token)
        self._refresh_token = str(_first_nonempty(token_node, ("refresh_token", "refreshToken")) or self._refresh_token or "") or None
        self._token_expires_at = self.clock() + ttl
        self._save_credentials({
            "access_token": self._token,
            "refresh_token": self._refresh_token,
            "expires_at": time.time() + max(60, self._token_expires_at - self.clock()),
            "updated_at": time.time(),
        })

    def fetch_inventory(self, store_id: int) -> list[dict[str, Any]]:
        page_size = 1000
        rows: list[dict[str, Any]] = []
        for page_index in range(100):
            payload = self._authorized_form(self.config.jackyun_inventory_url or "", self._inventory_form(page_index, page_size))
            _raise_for_platform_error(payload)
            page_rows = _extract_rows(payload)
            rows.extend(page_rows)
            if len(page_rows) < page_size:
                break
        return rows

    def fetch_package_products(self, store_id: int) -> list[dict[str, Any]]:
        """Fetch combination-product master rows (without stock quantities)."""
        if not self.config.jackyun_package_url:
            return []
        rows: list[dict[str, Any]] = []
        page_size = 1000
        for page_index in range(1, 101):
            data = {
                "blockUp": "0", "packageGood": "1", "pageIndex": str(page_index), "pageSize": str(page_size),
                "sortField": "", "sortOrder": "", "isNeedPkeyOrder": "0", "businessType": "goods.sku.info.search",
                "cols": json.dumps([
                    "goodsNo", "goodsName", "skuProperitesName", "cateName", "creator", "brandName", "unitName",
                    "skuBarcode", "flagData", "skuWeight", "skuLength", "skuWidth", "skuHeight", "volume",
                    "retailPrice", "stockPrice", "ownerName", "modifiedBy", "auditor", "gmtCreate", "gmtModified",
                    "goodsMainImgUrl", "isSplitOrder", "isSplitSale", "skuCount", "amount", "goodsId", "skuId",
                    "skuNo", "packageGood", "aduitStatus", "imgUrl",
                ], separators=(",", ":"), ensure_ascii=False),
            }
            payload = self._authorized_form_with_contract(
                self.config.jackyun_package_url,
                self._signed_form(data),
                module_code="goods_managet_combination",
                referer=f"{self._base_url()}/erp/goods_file_erp/goods_managet_combination_v2.html",
            )
            _raise_for_platform_error(payload)
            page_rows = _extract_rows(payload, package=False)
            rows.extend(page_rows)
            if len(page_rows) < page_size:
                break
        return rows

    def fetch_packages(self, store_id: int) -> list[dict[str, Any]]:
        """Backward-compatible alias; callers should use daily master sync."""
        return self.fetch_package_products(store_id)

    def fetch_goods(self, store_id: int) -> list[dict[str, Any]]:
        """Fetch ordinary goods master data once per daily sync.

        This endpoint is deliberately separate from the warehouse snapshot:
        its ``packageGood=0`` contract returns goods/SKU metadata, not stock.
        """
        if not self.config.jackyun_goods_url:
            return []
        rows: list[dict[str, Any]] = []
        page_size = 1000
        for page_index in range(1, 101):
            data = {
                "blockUp": "0", "packageGood": "0", "pageIndex": str(page_index), "pageSize": str(page_size),
                "sortField": "", "sortOrder": "", "isNeedPkeyOrder": "0", "businessType": "goods.sku.info.search",
                "cols": json.dumps([
                    "goodsNo", "goodsName", "cateName", "brandName", "unitName", "assistUnit",
                    "goodsAssistStockUnit", "ownerName", "goodsField1", "goodsField2", "goodsField3",
                    "goodsField4", "goodsField5", "goodsField6", "goodsField7", "goodsField8",
                    "goodsField9", "goodsField10", "goodsField11", "goodsField12", "goodsField13",
                    "goodsField14", "goodsField15", "goodsField16", "gmtCreate", "gmtModified",
                    "goodsAttr", "goodsUnits", "goodsMemberId", "goodsDesc", "packageGood", "aduitStatus",
                ], separators=(",", ":"), ensure_ascii=False),
            }
            payload = self._authorized_form_with_contract(
                self.config.jackyun_goods_url,
                self._signed_form(data),
                module_code="goods_managet_query",
                referer=f"{self._base_url()}/erp/goods_file_erp/goods_managet_v3.html?mode=0",
            )
            _raise_for_platform_error(payload)
            page_rows = _extract_rows(payload, package=False)
            rows.extend(page_rows)
            if len(page_rows) < page_size:
                break
        return rows

    def fetch_package_components(self, package_goods_id: str) -> list[dict[str, Any]]:
        """Fetch one combination's component rows by its goods ID."""
        if not self.config.jackyun_package_detail_url or not package_goods_id:
            return []
        data = {
            "businessType": "goods.package.stock.search", "goodsId": str(package_goods_id),
            "pageIndex": "0", "pageSize": "50", "sortField": "", "sortOrder": "",
            "cols": json.dumps([
                "goodsNo", "goodsName", "skuProperitesName", "goodsAmount", "skuBarcode",
                "imgUrl", "unitName", "sharePrice", "shareAmount", "shareRatio", "isGiveaway",
                "retailPrice", "assistUnit", "isMainSku", "isBlockup", "isStopSelling", "isStopPurchasing",
            ], separators=(",", ":"), ensure_ascii=False),
        }
        payload = self._authorized_get_with_contract(
            self.config.jackyun_package_detail_url,
            data,
            module_code="goods_managet_combination",
            referer=f"{self._base_url()}/erp/goods_file_erp/goods_managet_combination_v2.html",
        )
        _raise_for_platform_error(payload)
        return _extract_rows(payload, package=True)

    def _inventory_form(self, page_index: int, page_size: int) -> dict[str, str]:
        warehouse_ids = ",".join(self._warehouse_ids())
        cols = [
            "goodsNo", "goodsName", "canUseQuantity", "warehouseName", "skuName", "skuBarcode", "brandName",
            "unitName", "cateName", "distrubuteQuantity", "stockInQuantity", "stockOutQuantity", "lockingQuantity",
            "purchasingQuantity", "threedayQuantity", "allocateQuantity", "currentQuantity", "salesReturnQuantity",
            "productingQuantity", "orderingQuantity", "orderAbleQuantity", "residualQuantityDefective", "goodsAttr",
            "mainBarcode", "ownerName", "preSaleQuantity", "preSales5", "preSales7", "preSales10", "preSales15",
            "preSales20", "preSales25", "preSaleStockQuantity", "shelfLifeStr", "refundingQuantity", "id", "warehouseId",
            "goodsId", "skuId", "skuIds", "goodsAlias", "totalSaleQuantity", "isBlockup", "isStopSelling", "isStopPurchasing",
            "isBatchManagement", "isSerialManagement", "aduitStatus", "warehouseTypeCode", "isPositonStock", "flagData",
            "maxValue", "minValue", "skuFlags",
        ]
        data = {
            "searchNoType": "goodsNo", "searchNos": "", "isQuickSearch": "0", "goodsNo": "", "goodsName": "",
            "cateIds": "", "skuBarcode": "", "assistBarcode": "", "skuName": "", "unitName": "", "brandIds": "",
            "lowOrHigh": "", "flagData": "", "goodsAttrs": "", "ownerName": "", "dataShop": "", "pageIndex": str(page_index),
            "pageSize": str(page_size), "sortField": "", "sortOrder": "", "cols": json.dumps(cols, separators=(",", ":"), ensure_ascii=False),
            "searchType": "2", "searchWarehouseType": "2", "isHideZeroQuantity": "0", "isShowBlockup": "0",
            "warehouseId": warehouse_ids, "isHideStopSelling": "", "isHideStopPurchasing": "", "isPaidService": "",
            "serviceType": "stock.search.v2", "groupByGoods": "",
        }
        return self._signed_form(data)

    def _signed_form(self, data: dict[str, str]) -> dict[str, str]:
        timestamp = str(int(time.time() * 1000))
        token = self.token()
        access_token = f"Bearer {token}"
        signed = {"appkey": str(self._constant(self.config.jackyun_appkey, "APPKEY") or ""), "timestamp": timestamp, "access_token": access_token, **data}
        secret = self._constant(self.config.jackyun_signature_secret, "SECRET")
        if not secret:
            raise JackyunIntegrationError("未配置吉客云签名密钥，无法请求库存接口")
        # Match the browser helper: null and blank values are omitted from the
        # signature even though they remain in the submitted form payload.
        sign_input = "".join(
            key + str(signed[key])
            for key in sorted(signed)
            if signed[key] is not None and str(signed[key]).strip() != ""
        )
        signed.update({"timestamp": timestamp, "access_token": access_token, "appkey": str(self._constant(self.config.jackyun_appkey, "APPKEY") or ""), "sign": hashlib.md5(f"{secret}{sign_input}{secret}".encode("utf-8")).hexdigest().upper()})
        return signed

    def _authorized_form(self, url: str, payload: dict[str, str]) -> Any:
        return self._authorized_form_with_contract(
            url, payload, module_code="branch_stock",
            referer=f"{self._base_url()}/erp_stock/goods_stock/branch_stock_main_v4.html?mode=sku",
        )

    def _authorized_form_with_contract(
        self,
        url: str,
        payload: dict[str, str],
        *,
        module_code: str,
        referer: str,
    ) -> Any:
        token = self.token()
        try:
            return self._open_form(url, payload, headers=self._web_headers(module_code=module_code, referer=referer))
        except HTTPError as exc:
            if exc.code != 401 or not self.config.jackyun_token_url:
                raise
            self.token(force=True)
            return self._open_form(url, {**payload, **self._signed_form({key: value for key, value in payload.items() if key not in {"timestamp", "access_token", "appkey", "sign"}})}, headers=self._web_headers(module_code=module_code, referer=referer))

    def _authorized_get_with_contract(
        self,
        url: str,
        payload: dict[str, str],
        *,
        module_code: str,
        referer: str,
    ) -> Any:
        signed = self._signed_form(payload)
        query_url = f"{url}?{urlencode(signed)}"
        try:
            return self._open_get(query_url, headers=self._web_headers(module_code=module_code, referer=referer))
        except HTTPError as exc:
            if exc.code != 401 or not self.config.jackyun_token_url:
                raise
            self.token(force=True)
            signed = self._signed_form(payload)
            return self._open_get(f"{url}?{urlencode(signed)}", headers=self._web_headers(module_code=module_code, referer=referer))

    def _base_url(self) -> str:
        companion = self._load_companion_constants().get("BASE_URL")
        return str(companion or "https://web.jackyun.com").rstrip("/")

    def _web_headers(self, *, module_code: str, referer: str, content_type: str = "application/x-www-form-urlencoded; charset=UTF-8") -> dict[str, str]:
        token = self._token or ""
        headers = {
            "Accept": "text/plain, */*; q=0.01", "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8", "ati": str(self._constant(self.config.jackyun_ati, "ATI") or ""),
            "Content-Type": content_type, "module_code": module_code, "Origin": self._base_url(), "Referer": referer,
            "X-Requested-With": "XMLHttpRequest", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151.0.0.0 Safari/537.36",
            "Authorization": f"Bearer {token}",
        }
        cookie = self.config.jackyun_cookie or self._credential_values.get("cookie")
        if cookie:
            # The browser Cookie contains a token cookie that becomes stale
            # whenever /auth/refresh rotates the access token. Keep the
            # session cookies intact while aligning that one value with the
            # Authorization header used for this request.
            headers["Cookie"] = re.sub(
                r"(?i)(^|;\s*)token=[^;]*",
                lambda match: f"{match.group(1)}token={token}",
                str(cookie),
            )
        else:
            headers["Cookie"] = "; ".join(filter(None, [f"_ati={headers['ati']}", "group=g003", f"token={token}" if token else ""]))
        return headers

    def _authorized_json(self, url: str, payload: dict[str, Any]) -> Any:
        token = self.token()
        try:
            return self._open_json(url, payload, headers=self._auth_headers(token))
        except HTTPError as exc:
            # A platform may revoke a token before its advertised expiry. Do
            # one forced refresh, then retry exactly once; never loop forever.
            if exc.code != 401 or not self.config.jackyun_token_url:
                raise
            return self._open_json(url, payload, headers=self._auth_headers(self.token(force=True)))

    def _auth_headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}", "X-Access-Token": token}

    def _open_form(self, url: str, payload: dict[str, Any], *, headers: dict[str, str]) -> Any:
        if not url:
            raise JackyunIntegrationError("未配置吉客云接口地址")
        request_headers = {"Accept": "application/json", **headers}
        request = Request(url, data=urlencode(payload).encode("utf-8"), headers=request_headers, method="POST")
        try:
            with self.opener(request, timeout=30) as response:
                raw = response.read()
        except HTTPError:
            raise
        except (URLError, TimeoutError) as exc:
            raise JackyunIntegrationError(f"吉客云接口请求失败：{exc}") from exc
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise JackyunIntegrationError("吉客云接口返回不是有效 JSON") from exc

    def _open_get(self, url: str, *, headers: dict[str, str]) -> Any:
        if not url:
            raise JackyunIntegrationError("未配置吉客云接口地址")
        request = Request(url, headers={"Accept": "application/json", **headers}, method="GET")
        try:
            with self.opener(request, timeout=30) as response:
                raw = response.read()
        except HTTPError:
            raise
        except (URLError, TimeoutError) as exc:
            raise JackyunIntegrationError(f"吉客云接口请求失败：{exc}") from exc
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise JackyunIntegrationError("吉客云接口返回不是有效 JSON") from exc

    def _open_json(self, url: str, payload: dict[str, Any], *, headers: dict[str, str]) -> Any:
        if not url:
            raise JackyunIntegrationError("未配置吉客云接口地址")
        request_headers = {"Accept": "application/json", "Content-Type": "application/json", **headers}
        request = Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=request_headers, method="POST")
        try:
            with self.opener(request, timeout=30) as response:
                raw = response.read()
        except HTTPError:
            # Keep HTTPError intact so the caller can distinguish an expired
            # token (401) from other platform failures and retry safely.
            raise
        except (URLError, TimeoutError) as exc:
            raise JackyunIntegrationError(f"吉客云接口请求失败：{exc}") from exc
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise JackyunIntegrationError("吉客云接口返回不是有效 JSON") from exc


class JackyunInventorySyncService:
    def __init__(self, database_path: Path | None = None, client: JackyunClient | None = None) -> None:
        self.database_path = Path(database_path or settings.local_database_path).resolve()
        self.inventory = InventoryService(self.database_path)
        self.client = client or JackyunClient()

    def store_ids(self) -> list[int]:
        if self.client.config.jackyun_store_ids:
            return list(self.client.config.jackyun_store_ids)
        with self.inventory.database.connect(initialize=True) as conn:
            rows = conn.execute(f"select {q(STORE_ID)} as store_id from stores order by {q(STORE_ID)}").fetchall()
            return [int(row["store_id"]) for row in rows]

    def sync_store(self, store_id: int, *, business_day: date | None = None) -> dict[str, Any]:
        if not self.client.configured:
            self.inventory.record_sync_status(store_id=store_id, status="not_configured", error_message="未配置吉客云 Token 或库存接口")
            return {"status": "not_configured", "store_id": store_id, "row_count": 0}
        day = business_day or today_in_shanghai()
        inventory_result: dict[str, Any]
        try:
            rows = self.client.fetch_inventory(store_id)
            count = self.inventory.upsert_inventory_snapshot(store_id=store_id, business_day=day, rows=rows)
            if count == 0:
                self.inventory.record_sync_status(store_id=store_id, status="no_data", latest_business_day=day, row_count=0, error_message="吉客云库存接口返回空数据")
                inventory_result = {"status": "no_data", "store_id": store_id, "row_count": 0, "business_day": day.isoformat()}
            else:
                fetched_at = datetime.now(SHANGHAI_TZ).isoformat(timespec="seconds")
                self.inventory.record_sync_status(store_id=store_id, status="success", latest_business_day=day, latest_snapshot_at=fetched_at, row_count=count)
                inventory_result = {"status": "success", "store_id": store_id, "row_count": count, "business_day": day.isoformat(), "fetched_at": fetched_at}
        except Exception as exc:
            message = _safe_error_message(exc)
            self.inventory.record_sync_status(store_id=store_id, status="failed", error_message=message)
            inventory_result = {"status": "failed", "store_id": store_id, "row_count": 0, "business_day": day.isoformat(), "error": message}

        master_result = self.sync_daily_masters(store_id, business_day=day) if self._master_due(store_id, day) else {
            "status": "already_collected",
            **self.inventory.get_master_sync(store_id),
        }
        return {
            **inventory_result,
            "master_status": master_result.get("status"),
            "goods_status": master_result.get("goods_status"),
            "package_status": master_result.get("package_status"),
            "goods_master_count": int(master_result.get("goods_count") or 0),
            "package_count": int(master_result.get("package_count") or 0),
            "component_count": int(master_result.get("component_count") or 0),
        }

    def sync_daily_masters(self, store_id: int, *, business_day: date | None = None) -> dict[str, Any]:
        """Collect ordinary goods and combination relations at most once a day."""
        day = business_day or today_in_shanghai()
        goods_status = "not_configured"
        package_status = "not_configured"
        goods_count = package_count = component_count = 0
        errors: list[str] = []

        if self.client.config.jackyun_goods_url:
            try:
                goods = self.client.fetch_goods(store_id)
                if goods:
                    goods_count = self.inventory.replace_goods_master(store_id=store_id, rows=goods)
                    goods_status = "success"
                else:
                    goods_status = "no_data"
                    errors.append("普通货品主档接口返回空数据，已保留上次成功数据")
            except Exception as exc:
                goods_status = "failed"
                errors.append(f"普通货品主档：{_safe_error_message(exc)}")

        if self.client.config.jackyun_package_url and self.client.config.jackyun_package_detail_url:
            try:
                products = self.client.fetch_package_products(store_id)
                if products:
                    records: list[dict[str, Any]] = []
                    for product in products:
                        goods_id = _first_nonempty(product, ("goodsId", "goods_id", "id"))
                        if not goods_id:
                            raise JackyunIntegrationError("组合货品主档缺少 goodsId，无法查询组成明细")
                        records.append({"product": product, "components": self.client.fetch_package_components(str(goods_id))})
                    package_count, component_count = self.inventory.replace_package_master(store_id=store_id, records=records)
                    package_status = "success"
                else:
                    package_status = "no_data"
                    errors.append("组合货品主档接口返回空数据，已保留上次成功数据")
            except Exception as exc:
                package_status = "failed"
                errors.append(f"组合货品主档：{_safe_error_message(exc)}")

        status = "success" if goods_status == package_status == "success" else "partial"
        message = "；".join(errors)[:300] or None
        self.inventory.record_master_sync(
            store_id=store_id, business_day=day, goods_status=goods_status,
            package_status=package_status, goods_count=goods_count,
            package_count=package_count, component_count=component_count,
            error_message=message, finished=True,
        )
        return {
            "status": status, "store_id": store_id, "business_day": day.isoformat(),
            "goods_status": goods_status, "package_status": package_status,
            "goods_count": goods_count, "package_count": package_count,
            "component_count": component_count,
        }

    def run_due(self) -> list[dict[str, Any]]:
        if not self.client.configured:
            return []
        results = []
        for store_id in self.store_ids():
            if self._due(store_id):
                results.append(self.sync_store(store_id))
            elif self._master_due(store_id, today_in_shanghai()):
                results.append(self.sync_daily_masters(store_id))
        return results

    def _due(self, store_id: int) -> bool:
        with self.inventory.database.connect(initialize=True) as conn:
            row = conn.execute("select latest_snapshot_at, last_attempt_at from jackyun_inventory_sync_status where store_id = ?", (store_id,)).fetchone()
        if not row:
            return True
        timestamps = []
        for value in (row["latest_snapshot_at"], row["last_attempt_at"]):
            if not value:
                continue
            try:
                parsed = datetime.fromisoformat(str(value))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=SHANGHAI_TZ)
                timestamps.append(parsed.astimezone(SHANGHAI_TZ))
            except ValueError:
                continue
        if not timestamps:
            return True
        age = (datetime.now(SHANGHAI_TZ) - max(timestamps)).total_seconds() / 60
        return age >= self.client.config.jackyun_inventory_refresh_minutes

    def _master_due(self, store_id: int, business_day: date) -> bool:
        with self.inventory.database.connect(initialize=True) as conn:
            row = conn.execute(
                "select goods_status, package_status from jackyun_inventory_master_sync_status where store_id = ? and business_day = ?",
                (store_id, business_day.isoformat()),
            ).fetchone()
        if row is None:
            return True
        # A successful daily dimension slice is not repeated every hour. A
        # failed slice remains eligible for a safe retry so a later collection
        # can fill the day's gap without deleting the last successful slice.
        return str(row["goods_status"] or "") == "failed" or str(row["package_status"] or "") == "failed"


class JackyunInventoryScheduler:
    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="jackyun-inventory-scheduler")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _run(self) -> None:
        service = JackyunInventorySyncService()
        while not self._stop_event.is_set():
            try:
                service.run_due()
            except Exception:
                pass
            self._stop_event.wait(60)


jackyun_inventory_scheduler = JackyunInventoryScheduler()
