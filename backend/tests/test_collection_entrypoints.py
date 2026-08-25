from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.main as main_module
from app.api.dependencies import get_current_principal
from app.api.v1.routes import collection as collection_routes
from app.api.v1.routes import inventory as inventory_routes
from app.api.v1.routes import reviews as review_routes
from app.core.config import settings
from app.core.local_database import LocalDatabase
from app.main import create_app
from app.modules.access.service import Principal
from app.modules.collection.schemas import CollectionBatch
from app.integrations.tmall_session import BrowserPlatformSession, RuntimeSessionUnavailable
from app.integrations.jackyun_inventory import JackyunIntegrationError
from app.modules.reviews.schemas import ReviewCollectionRun


def _principal(*permissions: str, store_ids: frozenset[int] | None = None) -> Principal:
    return Principal(
        user_id=1,
        username="test-user",
        display_name="测试用户",
        roles=frozenset(),
        permissions=frozenset(permissions),
        menus=frozenset(),
        store_ids=store_ids,
        brand_ids=None,
    )


@pytest.fixture
def route_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    original_database_path = settings.local_database_path
    object.__setattr__(settings, "local_database_path", str(tmp_path / "entrypoints.sqlite3"))
    monkeypatch.setattr(main_module.collection_scheduler, "start", lambda: None)
    monkeypatch.setattr(main_module.collection_scheduler, "stop", lambda: None)
    monkeypatch.setattr(main_module.jackyun_inventory_scheduler, "start", lambda: None)
    monkeypatch.setattr(main_module.jackyun_inventory_scheduler, "stop", lambda: None)
    app = create_app()
    try:
        yield app
    finally:
        object.__setattr__(settings, "local_database_path", original_database_path)


class FakeCollectionService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def start_batch(self, **kwargs: object) -> CollectionBatch:
        self.calls.append(kwargs)
        return CollectionBatch(
            batch_id="batch-entrypoint",
            business_day=str(kwargs["business_day"]),
            dataset_names=list(kwargs["dataset_names"]),
            trigger=str(kwargs["trigger"]),
            session_source=str(kwargs["session_source"]),
            refresh_existing=bool(kwargs["refresh_existing"]),
            status="running",
            process_id=4321,
            started_at="2026-08-23T08:00:00+08:00",
            log_file="entrypoint.log",
        )


class FakeReviewService:
    def __init__(self) -> None:
        self.executed_reviews: list[str] = []
        self.executed_asks: list[str] = []

    @staticmethod
    def _run(run_id: str, mode: str) -> ReviewCollectionRun:
        return ReviewCollectionRun(
            run_id=run_id,
            mode=mode,
            status="queued",
            started_at="2026-08-23T08:00:00+08:00",
        )

    def start_collection(self, *, mode: str) -> ReviewCollectionRun:
        return self._run("review-entrypoint", mode)

    def execute_collection(self, run_id: str, **_kwargs: object) -> None:
        self.executed_reviews.append(run_id)

    def start_ask_collection(self, *, mode: str) -> ReviewCollectionRun:
        return self._run("ask-entrypoint", mode)

    def execute_ask_collection(self, run_id: str, **_kwargs: object) -> None:
        self.executed_asks.append(run_id)


def test_daily_collection_starts_browser_before_creating_batch(
    route_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeCollectionService()
    browser_launches: list[int] = []
    monkeypatch.setattr(collection_routes, "get_collection_service", lambda: service)
    monkeypatch.setattr(collection_routes, "browser_debug_connected", lambda _port: False)
    monkeypatch.setattr(
        collection_routes,
        "launch_collection_browser",
        lambda port: browser_launches.append(port),
    )
    preflight: list[list[str]] = []
    monkeypatch.setattr(
        collection_routes,
        "_preflight_collection_sessions",
        lambda names: preflight.append(list(names)),
    )
    route_app.dependency_overrides[get_current_principal] = lambda: _principal("data.manage")

    with TestClient(route_app) as client:
        response = client.post(
            "/api/v1/imports/collect",
            json={
                "day": "2026-08-22",
                "dataset_names": ["sycm_overviews"],
                "session_source": "drissionpage",
                "refresh_existing": False,
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert browser_launches == [settings.tmall_browser_port]
    assert preflight == [["sycm_overviews"]]
    assert service.calls[0]["dataset_names"] == ["sycm_overviews"]


def test_daily_collection_does_not_create_batch_when_login_preflight_fails(
    route_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeCollectionService()
    monkeypatch.setattr(collection_routes, "get_collection_service", lambda: service)
    monkeypatch.setattr(collection_routes, "browser_debug_connected", lambda _port: True)
    monkeypatch.setattr(
        collection_routes,
        "_preflight_collection_sessions",
        lambda _names: (_ for _ in ()).throw(
            RuntimeSessionUnavailable("生意参谋登录页已打开，请完成登录后重试。")
        ),
    )
    route_app.dependency_overrides[get_current_principal] = lambda: _principal("data.manage")

    with TestClient(route_app) as client:
        response = client.post(
            "/api/v1/imports/collect",
            json={
                "day": "2026-08-22",
                "dataset_names": ["sycm_overviews"],
                "session_source": "drissionpage",
                "refresh_existing": False,
            },
        )

    assert response.status_code == 409
    assert "生意参谋登录页" in response.json()["detail"]
    assert service.calls == []


def test_cps_collection_preflight_checks_sycm_then_cps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked: list[str] = []

    def fake_probe(_port: int, code: str, **_kwargs: object) -> BrowserPlatformSession:
        checked.append(code)
        return BrowserPlatformSession(
            code=code,
            name="生意参谋" if code == "sycm" else "淘宝客 CPS",
            status="healthy",
            detail="已登录",
            page_detected=True,
            authenticated=True,
            cookie_detected=True,
            cookie_count=2,
        )

    monkeypatch.setattr(collection_routes, "open_browser_platform_session", fake_probe)

    collection_routes._preflight_collection_sessions(["cps_overviews"])

    assert checked == ["sycm", "cps"]


def test_review_collection_starts_browser_and_runs_background_task(
    route_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeReviewService()
    browser_launches: list[int] = []
    monkeypatch.delenv(settings.tmall_cookie_env, raising=False)
    monkeypatch.setattr(review_routes, "get_review_service", lambda: service)
    monkeypatch.setattr(review_routes, "browser_debug_connected", lambda _port: False)
    monkeypatch.setattr(
        review_routes,
        "launch_collection_browser",
        lambda port: browser_launches.append(port),
    )
    route_app.dependency_overrides[get_current_principal] = lambda: _principal("data.manage")

    with TestClient(route_app) as client:
        response = client.post(
            "/api/v1/reviews/collect",
            json={"mode": "incremental", "max_pages": 2, "start_date": "2026-08-01"},
        )

    assert response.status_code == 200
    assert response.json()["run_id"] == "review-entrypoint"
    assert browser_launches == [settings.tmall_browser_port]
    assert service.executed_reviews == ["review-entrypoint"]


def test_ask_collection_reuses_connected_browser(
    route_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeReviewService()
    monkeypatch.delenv(settings.tmall_cookie_env, raising=False)
    monkeypatch.setattr(review_routes, "get_review_service", lambda: service)
    monkeypatch.setattr(review_routes, "browser_debug_connected", lambda _port: True)
    monkeypatch.setattr(
        review_routes,
        "launch_collection_browser",
        lambda _port: pytest.fail("已连接的采集浏览器不应重复启动"),
    )
    route_app.dependency_overrides[get_current_principal] = lambda: _principal("data.manage")

    with TestClient(route_app) as client:
        response = client.post(
            "/api/v1/reviews/asks/collect",
            json={"mode": "incremental", "max_pages": 2},
        )

    assert response.status_code == 200
    assert response.json()["run_id"] == "ask-entrypoint"
    assert service.executed_asks == ["ask-entrypoint"]


def test_daily_collection_rejects_active_feedback_run(
    route_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = LocalDatabase(Path(settings.local_database_path))
    database.initialize_schema()
    with database.connect(initialize=True) as conn:
        conn.execute(
            """
            create table if not exists review_collection_runs (
                run_id text primary key, mode text not null, status text not null, started_at text not null
            )
            """
        )
        conn.execute(
            "insert into review_collection_runs(run_id, mode, status, started_at) values (?, ?, ?, ?)",
            ("review-running", "incremental", "running", "2026-08-23T08:00:00+08:00"),
        )
        conn.commit()

    service = FakeCollectionService()
    monkeypatch.setattr(collection_routes, "get_collection_service", lambda: service)
    monkeypatch.setattr(
        collection_routes,
        "launch_collection_browser",
        lambda _port: pytest.fail("存在评价任务时不应启动日常采集浏览器"),
    )
    route_app.dependency_overrides[get_current_principal] = lambda: _principal("data.manage")

    with TestClient(route_app) as client:
        response = client.post(
            "/api/v1/imports/collect",
            json={
                "day": "2026-08-22",
                "dataset_names": ["sycm_overviews"],
                "session_source": "drissionpage",
                "refresh_existing": False,
            },
        )

    assert response.status_code == 409
    assert "评价采集任务正在运行" in response.json()["detail"]
    assert service.calls == []


def test_review_collection_rejects_active_daily_batch(
    route_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = LocalDatabase(Path(settings.local_database_path))
    database.initialize_schema()
    with database.connect(initialize=True) as conn:
        conn.execute(
            """
            insert into collection_batches (
                batch_id, business_day, dataset_names_json, trigger_type,
                session_source, refresh_existing, status, process_id,
                started_at, log_file
            ) values (?, ?, ?, ?, ?, ?, 'running', ?, ?, ?)
            """,
            (
                "batch-running", "2026-08-22", '["sycm_overviews"]', "manual",
                "drissionpage", 0, 4321, "2026-08-23T08:00:00+08:00", "batch.log",
            ),
        )
        conn.commit()

    service = FakeReviewService()
    monkeypatch.setattr(review_routes, "get_review_service", lambda: service)
    monkeypatch.setattr(
        review_routes,
        "launch_collection_browser",
        lambda _port: pytest.fail("存在日常批次时不应启动评价采集浏览器"),
    )
    route_app.dependency_overrides[get_current_principal] = lambda: _principal("data.manage")

    with TestClient(route_app) as client:
        response = client.post(
            "/api/v1/reviews/collect",
            json={"mode": "incremental", "max_pages": 2, "start_date": "2026-08-01"},
        )

    assert response.status_code == 409
    assert "日常经营采集正在运行" in response.json()["detail"]
    assert service.executed_reviews == []


def test_inventory_sync_requires_data_manage_permission(
    route_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeInventorySyncService:
        def __init__(self) -> None:
            self.client = type("Client", (), {"configured": False})()

    monkeypatch.setattr(inventory_routes, "JackyunInventorySyncService", FakeInventorySyncService)

    route_app.dependency_overrides[get_current_principal] = lambda: _principal(
        "data.manage",
        store_ids=frozenset({7}),
    )
    with TestClient(route_app) as client:
        allowed = client.post("/api/v1/inventory/sync", json={"store_id": 7})
        route_app.dependency_overrides[get_current_principal] = lambda: _principal(
            "analytics.read",
            store_ids=frozenset({7}),
        )
        forbidden = client.post("/api/v1/inventory/sync", json={"store_id": 7})

    assert allowed.status_code == 200
    assert allowed.json()["configured"] is False
    assert allowed.json()["results"][0]["status"] == "not_configured"
    assert forbidden.status_code == 403


def test_inventory_credentials_can_be_replaced_and_validated_safely(
    route_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[dict[str, object]] = []

    class FakeJackyunClient:
        def credential_status(self) -> dict[str, object]:
            return {
                "configured": False,
                "status": "not_configured",
                "source": "none",
                "refresh_token_configured": False,
                "access_token_configured": False,
                "access_token_expired": False,
                "updated_at": None,
                "detail": "尚未配置。",
            }

        def set_refresh_credentials(self, **kwargs: object) -> dict[str, object]:
            saved.append(kwargs)
            return {
                "configured": True,
                "status": "refresh_required",
                "source": "vault",
                "refresh_token_configured": True,
                "access_token_configured": False,
                "access_token_expired": False,
                "updated_at": "2026-08-23T10:00:00+08:00",
                "detail": "下一次采集会自动刷新。",
            }

        def validate_refresh_credentials(self) -> dict[str, object]:
            raise JackyunIntegrationError("platform echoed super-secret-refresh-token")

    monkeypatch.setattr(collection_routes, "JackyunClient", FakeJackyunClient)
    route_app.dependency_overrides[get_current_principal] = lambda: _principal("data.manage")

    with TestClient(route_app) as client:
        updated = client.put(
            "/api/v1/imports/settings/inventory-credentials",
            json={"refresh_token": "super-secret-refresh-token", "access_token": None},
        )
        tested = client.post("/api/v1/imports/settings/inventory-credentials/test")
        route_app.dependency_overrides[get_current_principal] = lambda: _principal("analytics.read")
        forbidden = client.put(
            "/api/v1/imports/settings/inventory-credentials",
            json={"refresh_token": "another-token"},
        )

    assert updated.status_code == 200
    assert updated.json()["refresh_token_configured"] is True
    assert "super-secret-refresh-token" not in updated.text
    assert saved == [{"refresh_token": "super-secret-refresh-token", "access_token": None, "access_token_ttl_seconds": 3600}]
    assert tested.status_code == 200
    assert tested.json()["status"] == "invalid"
    assert "super-secret-refresh-token" not in tested.text
    assert "重新登录吉客云" in tested.json()["detail"]
    assert forbidden.status_code == 403
