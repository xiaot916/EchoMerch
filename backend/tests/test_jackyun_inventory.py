from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from pathlib import Path

from app.core.config import settings
from app.core.local_database import LocalDatabase
from app.integrations.jackyun_credentials import load_vault, save_vault, vault_contains_plaintext
from app.integrations.jackyun_inventory import JackyunClient, JackyunInventorySyncService
from app.modules.imports.crawl_run_store import CrawlRunStore


class _Response:
    def __init__(self, payload: dict, status: int = 200):
        self.payload = payload
        self.status = status

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        if self.status >= 400:
            from urllib.error import HTTPError
            raise HTTPError("https://jackyun.test", self.status, "expired", {}, None)
        return self

    def __exit__(self, *_args):
        return False


def _config(tmp_path: Path):
    return replace(
        settings,
        local_database_path=str(tmp_path / "jackyun.sqlite3"),
        jackyun_credentials_path=str(tmp_path / "credentials.bin"),
        jackyun_token_cache_path=None,
        jackyun_token_url="https://jackyun.test/token",
        jackyun_inventory_url="https://jackyun.test/inventory",
        jackyun_package_url=None,
        jackyun_goods_url="https://jackyun.test/jkyun/erp-goods/search/getgoodsinfoandbaseunit",
        jackyun_package_detail_url=None,
        jackyun_token=None,
        jackyun_client_id="client",
        jackyun_client_secret="secret",
        jackyun_warehouse_ids=[],
        jackyun_cookie=None,
        jackyun_appkey="appkey",
        jackyun_ati="ati",
        jackyun_signature_secret="secret-signature",
        jackyun_store_ids=[1],
        jackyun_token_ttl_seconds=3600,
        jackyun_inventory_refresh_minutes=60,
    )


def test_token_is_cached_for_one_hour(tmp_path: Path):
    config = _config(tmp_path)
    now = [1000.0]
    calls: list[str] = []

    def opener(request, timeout=30):
        calls.append(request.full_url)
        return _Response({"access_token": "token-1", "expires_in": 3600})

    client = JackyunClient(config, opener=opener, clock=lambda: now[0])
    assert client.token() == "token-1"
    now[0] += 1800
    assert client.token() == "token-1"
    assert calls == ["https://jackyun.test/token"]
    now[0] += 1801
    assert client.token() == "token-1"
    assert calls == ["https://jackyun.test/token", "https://jackyun.test/token"]


def test_inventory_401_forces_one_token_refresh(tmp_path: Path):
    config = _config(tmp_path)
    token_calls = 0
    inventory_calls = 0

    def opener(request, timeout=30):
        nonlocal token_calls, inventory_calls
        if request.full_url.endswith("/token"):
            token_calls += 1
            return _Response({"access_token": f"token-{token_calls}", "expires_in": 3600})
        inventory_calls += 1
        return _Response({"items": [{"goodsNo": "DAYU", "canUseQuantity": 4}]}, status=401 if inventory_calls == 1 else 200)

    client = JackyunClient(config, opener=opener)
    assert client.fetch_inventory(1)[0]["goodsNo"] == "DAYU"
    assert token_calls == 2
    assert inventory_calls == 2


def test_sync_service_waits_until_sixty_minutes(tmp_path: Path):
    config = _config(tmp_path)
    def opener(request, timeout=30):
        if request.full_url.endswith("/token"):
            return _Response({"access_token": "runtime-token", "expires_in": 3600})
        return _Response({"items": [{"goodsNo": "DAYU", "canUseQuantity": 4}]})

    client = JackyunClient(config, opener=opener)
    service = JackyunInventorySyncService(tmp_path / "sync.sqlite3", client)
    assert service._due(1)
    service.sync_store(1, business_day=date(2026, 8, 21))
    assert not service._due(1)
    with service.inventory.database.connect() as conn:
        stored = json.dumps([dict(row) for row in conn.execute("select * from jackyun_inventory_sync_status").fetchall()])
    assert "runtime-token" not in stored


def test_daily_master_endpoints_are_not_repeated_within_one_business_day(tmp_path: Path):
    config = _config(tmp_path)
    calls: list[str] = []

    def opener(request, timeout=30):
        calls.append(request.full_url)
        if request.full_url.endswith("/token"):
            return _Response({"access_token": "runtime-token", "expires_in": 3600})
        if request.full_url.endswith("/inventory"):
            return _Response({"items": [{"goodsNo": "DAYU", "canUseQuantity": 4}]})
        return _Response({"items": [{"goodsId": "G1", "goodsNo": "DAYU", "goodsName": "大鱼"}]})

    client = JackyunClient(config, opener=opener)
    service = JackyunInventorySyncService(tmp_path / "daily-master.sqlite3", client)
    first = service.sync_store(1, business_day=date(2026, 8, 21))
    second = service.sync_store(1, business_day=date(2026, 8, 21))

    assert first["goods_master_count"] == 1
    assert first["master_status"] == "partial"  # 组合接口未配置，普通主档仍成功
    assert second["master_status"] == "already_collected"
    assert len([url for url in calls if url.endswith("/inventory")]) == 2
    assert len([url for url in calls if not url.endswith("/inventory") and not url.endswith("/token")]) == 1


def test_v5_form_protocol_refreshes_and_persists_credentials(tmp_path: Path):
    config = replace(
        _config(tmp_path),
        jackyun_token_url="https://web.jackyun.com/auth/refresh",
        jackyun_inventory_url="https://web.jackyun.com/jkyun/erp-stock/warehouseStock/stockSkuList",
        jackyun_credentials_path=str(tmp_path / "credentials.bin"),
        jackyun_client_id="client-1",
        jackyun_appkey="appkey-1",
        jackyun_ati="ati-1",
        jackyun_signature_secret="signature-secret",
        jackyun_warehouse_ids=["warehouse-1"],
    )
    save_vault(Path(config.jackyun_credentials_path), {
        "refresh_token": "refresh-1",
        "access_token": "expired",
        "expires_at": 1,
    })
    requests: list[tuple[str, str]] = []

    def opener(request, timeout=30):
        body = request.data.decode("utf-8") if request.data else ""
        requests.append((request.full_url, body))
        if request.full_url.endswith("/auth/refresh"):
            return _Response({"access_token": "fresh-access", "refresh_token": "refresh-2", "expires_in": 3600})
        assert "warehouseId=warehouse-1" in body
        assert "sign=" in body
        return _Response({"code": 200, "result": {"data": [{"goodsNo": "DAYU", "canUseQuantity": 4}]}})

    client = JackyunClient(config, opener=opener)
    rows = client.fetch_inventory(1)

    assert rows[0]["goodsNo"] == "DAYU"
    assert requests[0][0].endswith("/auth/refresh")
    assert "refreshToken=refresh-1" in requests[0][1]
    assert load_vault(Path(config.jackyun_credentials_path))["refresh_token"] == "refresh-2"
    assert not vault_contains_plaintext(Path(config.jackyun_credentials_path), ["fresh-access", "refresh-2", "signature-secret"])


def test_manual_refresh_token_replaces_stale_access_token(tmp_path: Path):
    config = _config(tmp_path)
    save_vault(Path(config.jackyun_credentials_path), {
        "refresh_token": "old-refresh",
        "access_token": "old-access",
        "expires_at": 9_999_999_999,
    })

    client = JackyunClient(config)
    status = client.set_refresh_credentials(refresh_token="new-refresh")
    stored = load_vault(Path(config.jackyun_credentials_path))

    assert status["refresh_token_configured"] is True
    assert status["access_token_configured"] is False
    assert stored["refresh_token"] == "new-refresh"
    assert stored["access_token"] == ""
    assert stored["expires_at"] == 0
    assert not vault_contains_plaintext(Path(config.jackyun_credentials_path), ["new-refresh", "old-access"])


def test_credential_status_does_not_treat_empty_vault_as_configured(tmp_path: Path):
    config = replace(
        _config(tmp_path),
        jackyun_client_id=None,
        jackyun_client_secret=None,
        jackyun_username=None,
        jackyun_password=None,
    )
    client = JackyunClient(config)

    status = client.credential_status()

    assert status["configured"] is False
    assert status["status"] == "not_configured"
    assert status["refresh_token_configured"] is False


def test_new_legacy_login_cache_is_imported_after_vault_bootstrap(tmp_path: Path):
    config = _config(tmp_path)
    cache_path = tmp_path / "token_cache.json"
    config = replace(config, jackyun_token_cache_path=str(cache_path))
    save_vault(Path(config.jackyun_credentials_path), {
        "access_token": "old-access",
        "refresh_token": "old-refresh",
        "expires_at": 9_999_999_999,
        "updated_at": 100,
    })
    cache_path.write_text(json.dumps({
        "access_token": "new-access",
        "refresh_token": "new-refresh",
        "expires_at": 9_999_999_999,
        "updated_at": 200,
    }), encoding="utf-8")

    client = JackyunClient(config)
    assert client.token() == "new-access"
    stored = load_vault(Path(config.jackyun_credentials_path))
    assert stored["refresh_token"] == "new-refresh"


def test_web_cookie_token_tracks_refreshed_access_token(tmp_path: Path):
    config = replace(_config(tmp_path), jackyun_cookie="session=abc; token=stale-token; group=g003")
    client = JackyunClient(config)
    client._token = "fresh-token"

    headers = client._web_headers(module_code="branch_stock", referer="https://web.jackyun.com/stock")

    assert "session=abc" in headers["Cookie"]
    assert "token=fresh-token" in headers["Cookie"]
    assert "stale-token" not in headers["Cookie"]


def test_sync_service_reads_store_ids_from_localized_store_schema(tmp_path: Path):
    database_path = tmp_path / "stores.sqlite3"
    database = LocalDatabase(database_path)
    database.initialize_schema()
    CrawlRunStore(database_path).ensure_store_reference(
        store_id=7,
        store_name="测试店铺",
        platform_store_id="platform-7",
    )

    service = JackyunInventorySyncService(
        database_path,
        JackyunClient(replace(_config(tmp_path), jackyun_store_ids=[])),
    )

    assert service.store_ids() == [7]
