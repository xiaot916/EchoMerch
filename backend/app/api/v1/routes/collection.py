from __future__ import annotations

import os
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import require_permission
from app.core.config import settings
from app.integrations.collection_browser import (
    CollectionBrowserLaunchError,
    browser_debug_connected,
    launch_collection_browser,
)
from app.integrations.jackyun_inventory import JackyunClient, JackyunIntegrationError
from app.integrations.tmall_session import (
    BrowserPlatformSession,
    RuntimeSessionUnavailable,
    _cookie_count,
    _validate_cookie_header,
    inspect_browser_platform_sessions,
    open_browser_platform_session,
)
from app.modules.access.service import Principal
from app.core.business_days import parse_business_day, yesterday_in_shanghai
from app.modules.collection.schemas import (
    BrowserHealth,
    CollectionBatch,
    CollectionOverview,
    CollectionSchedule,
    CollectionSettings,
    InventoryCredentialStatus,
    InventoryCredentialTestResponse,
    UpdateInventoryCredentialsRequest,
    PlatformSessionStatus,
    StartCollectionRequest,
    UpdateCollectionScheduleRequest,
)
from app.modules.collection.locks import active_feedback_run
from app.modules.collection.registry import COLLECTION_DATASET_KEYS
from app.modules.collection.service import (
    CollectionBatchConflict,
    CollectionConfigurationError,
    CollectionService,
)

router = APIRouter()


def get_collection_service() -> CollectionService:
    return CollectionService(Path(settings.local_database_path))


@router.get("/overview", response_model=CollectionOverview)
def get_collection_overview(
    day: date | None = Query(default=None),
    _: Principal = Depends(require_permission("data.manage")),
) -> CollectionOverview:
    return get_collection_service().overview(target_day=day)


@router.post("/collect", response_model=CollectionBatch)
def start_collection(
    request: StartCollectionRequest,
    _: Principal = Depends(require_permission("data.manage")),
) -> CollectionBatch:
    try:
        day = parse_business_day(request.day) if request.day else yesterday_in_shanghai()
        feedback_run = active_feedback_run(Path(settings.local_database_path))
        if feedback_run is not None:
            feedback_label, run_id = feedback_run
            raise CollectionBatchConflict(
                f"{feedback_label}采集任务正在运行（{run_id}），请等待完成后再启动日常经营采集。"
            )
        if request.session_source == "drissionpage":
            _ensure_collection_browser()
            _preflight_collection_sessions(request.dataset_names)
        return get_collection_service().start_batch(
            business_day=day,
            dataset_names=request.dataset_names,
            session_source=request.session_source,
            refresh_existing=request.refresh_existing,
            trigger="manual",
            resume_from_latest=request.resume_from_latest,
        )
    except (
        CollectionBatchConflict,
        CollectionBrowserLaunchError,
        CollectionConfigurationError,
        RuntimeSessionUnavailable,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/batches", response_model=list[CollectionBatch])
def list_collection_batches(
    limit: int = Query(default=20, ge=1, le=100),
    _: Principal = Depends(require_permission("data.manage")),
) -> list[CollectionBatch]:
    return get_collection_service().list_batches(limit=limit)


@router.get("/schedule", response_model=CollectionSchedule)
def get_collection_schedule(
    _: Principal = Depends(require_permission("data.manage")),
) -> CollectionSchedule:
    return get_collection_service().get_schedule()


@router.post("/schedule", response_model=CollectionSchedule)
def update_collection_schedule(
    request: UpdateCollectionScheduleRequest,
    _: Principal = Depends(require_permission("data.manage")),
) -> CollectionSchedule:
    try:
        return get_collection_service().update_schedule(
            enabled=request.enabled,
            run_time=request.run_time,
            dataset_names=request.dataset_names,
            session_source=request.session_source,
        )
    except CollectionConfigurationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/browser/start", response_model=BrowserHealth)
def start_collection_browser(
    _: Principal = Depends(require_permission("data.manage")),
) -> BrowserHealth:
    try:
        launch_collection_browser(settings.tmall_browser_port)
        existing = inspect_browser_platform_sessions(settings.tmall_browser_port)
        sycm = next((item for item in existing if item.code == "sycm"), None)
        probe = open_browser_platform_session(
            settings.tmall_browser_port,
            "sycm",
            keep_open_on_success=sycm is None or not sycm.page_detected,
        )
    except (CollectionBrowserLaunchError, RuntimeSessionUnavailable) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _collection_health(platform_overrides={"sycm": probe})


@router.get("/health", response_model=BrowserHealth)
def get_collection_health(_: Principal = Depends(require_permission("data.manage"))) -> BrowserHealth:
    return _collection_health()


def _collection_health(
    *,
    platform_overrides: dict[str, BrowserPlatformSession] | None = None,
) -> BrowserHealth:
    verified_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    browser_connected, browser_detail = _browser_probe(settings.tmall_browser_port)
    source = settings.tmall_session_source
    platforms: list[PlatformSessionStatus] = []
    session_detail = "尚未检测到可用平台会话。"

    if source == "env":
        cookie_header = os.getenv(settings.tmall_cookie_env, "").strip()
        if cookie_header:
            try:
                cookie_header = _validate_cookie_header(cookie_header)
            except RuntimeError:
                cookie_header = ""
        if cookie_header:
            cookie_count = _cookie_count(cookie_header)
            session_detail = f"已读取环境变量 {settings.tmall_cookie_env}，本次进程不会持久化 Cookie。"
            platforms = _env_platform_statuses(cookie_count)
        else:
            session_detail = f"环境变量 {settings.tmall_cookie_env} 未配置。"
            platforms = _env_platform_statuses(0)
    elif browser_connected:
        try:
            browser_platforms = inspect_browser_platform_sessions(settings.tmall_browser_port)
        except RuntimeSessionUnavailable as exc:
            browser_platforms = []
            session_detail = str(exc)
        if platform_overrides:
            by_code = {item.code: item for item in browser_platforms}
            by_code.update(platform_overrides)
            browser_platforms = [
                by_code[code]
                for code in ("sycm", "cps")
                if code in by_code
            ]
        platforms = [_platform_status(item) for item in browser_platforms]
        sycm = next((item for item in platforms if item.code == "sycm"), None)
        session_detail = sycm.detail if sycm else session_detail
    else:
        session_detail = browser_detail
        platforms = [_platform_status(BrowserPlatformSession(
            code=code,
            name=name,
            status="offline",
            detail=f"采集浏览器未连接，无法检查{name}登录状态。",
        )) for code, name in (("sycm", "生意参谋"), ("cps", "淘宝客 CPS"))]

    sycm_ready = any(item.code == "sycm" and item.authenticated for item in platforms)
    # Cookie validity and browser connectivity are separate health signals.
    # A usable env cookie keeps the platform session healthy, but a disconnected
    # collection browser still requires attention in the overall status.
    overall_status = (
        "ready"
        if sycm_ready and browser_connected
        else "attention"
        if browser_connected or sycm_ready
        else "offline"
    )
    return BrowserHealth(
        status=overall_status,
        browser_connected=browser_connected,
        source=source,
        debug_port=settings.tmall_browser_port,
        detail=session_detail if browser_connected or platforms else browser_detail,
        last_verified_at=verified_at,
        platforms=platforms,
    )


@router.get("/settings", response_model=CollectionSettings)
def get_collection_settings(_: Principal = Depends(require_permission("data.manage"))) -> CollectionSettings:
    inventory_credentials = InventoryCredentialStatus(**JackyunClient().credential_status())
    return CollectionSettings(
        session_source=settings.tmall_session_source,
        browser_port=settings.tmall_browser_port,
        cookie_env=settings.tmall_cookie_env,
        mode="worker_enabled",
        safety_rules=[
            "页面和接口不返回 Cookie、Token 或原始请求头。",
            "完整性查询使用只读连接，采集入库只由后台 Worker 执行。",
            "正式采集任务由 Worker 执行，HTTP 页面不在请求内运行爬虫。",
            "采集只读取平台报表，不执行商品、订单或广告计划写操作。",
        ],
        inventory_credentials=inventory_credentials,
    )


@router.put("/settings/inventory-credentials", response_model=InventoryCredentialStatus)
def update_inventory_credentials(
    request: UpdateInventoryCredentialsRequest,
    _: Principal = Depends(require_permission("data.manage")),
) -> InventoryCredentialStatus:
    try:
        status = JackyunClient().set_refresh_credentials(
            refresh_token=request.refresh_token,
            access_token=request.access_token,
            access_token_ttl_seconds=request.access_token_ttl_seconds,
        )
        return InventoryCredentialStatus(**status)
    except JackyunIntegrationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/settings/inventory-credentials/test", response_model=InventoryCredentialTestResponse)
def test_inventory_credentials(
    _: Principal = Depends(require_permission("data.manage")),
) -> InventoryCredentialTestResponse:
    client = JackyunClient()
    try:
        status = client.validate_refresh_credentials()
        return InventoryCredentialTestResponse(status="ready", detail="Refresh Token 校验通过，Access Token 已刷新。", credential_status=InventoryCredentialStatus(**status))
    except JackyunIntegrationError as exc:
        status = client.credential_status()
        status.update({
            "configured": False,
            "status": "invalid",
            "detail": "Refresh Token 校验失败，可能已失效，请重新登录吉客云后粘贴新的 Refresh Token。",
        })
        return InventoryCredentialTestResponse(status="invalid", detail=status["detail"], credential_status=InventoryCredentialStatus(**status))


def _browser_probe(port: int) -> tuple[bool, str]:
    if browser_debug_connected(port):
        return True, f"Chrome 调试端口 {port} 已连接。"
    return False, f"无法连接 Chrome 调试端口 {port}，请启动采集浏览器。"


def _ensure_collection_browser() -> None:
    if not browser_debug_connected(settings.tmall_browser_port):
        launch_collection_browser(settings.tmall_browser_port)


def _preflight_collection_sessions(dataset_names: list[str]) -> None:
    selected = set(dataset_names or COLLECTION_DATASET_KEYS)
    unknown = selected - set(COLLECTION_DATASET_KEYS)
    if unknown:
        raise CollectionConfigurationError("未知数据集：" + ", ".join(sorted(unknown)))
    required = ["sycm"]
    if "cps_overviews" in selected:
        required.append("cps")
    for platform_code in required:
        probe = open_browser_platform_session(
            settings.tmall_browser_port,
            platform_code,
            timeout=8,
        )
        if not probe.authenticated:
            raise RuntimeSessionUnavailable(
                f"{probe.detail} 登录完成后请回到采集中心重新点击采集。"
            )


def _platform_status(item: BrowserPlatformSession) -> PlatformSessionStatus:
    return PlatformSessionStatus(
        code=item.code,
        name=item.name,
        status=item.status,
        detail=item.detail,
        page_detected=item.page_detected,
        authenticated=item.authenticated,
        cookie_detected=item.cookie_detected,
        cookie_count=item.cookie_count,
    )


def _env_platform_statuses(cookie_count: int) -> list[PlatformSessionStatus]:
    cookie_ready = cookie_count > 0
    cps_token_ready = bool(os.getenv("CPS_TB_TOKEN", "").strip())
    return [
        PlatformSessionStatus(
            code="sycm",
            name="生意参谋",
            status="healthy" if cookie_ready else "attention",
            detail=(
                f"已从 {settings.tmall_cookie_env} 读取生意参谋会话。"
                if cookie_ready
                else f"环境变量 {settings.tmall_cookie_env} 未配置或不可用。"
            ),
            authenticated=cookie_ready,
            cookie_detected=cookie_ready,
            cookie_count=cookie_count,
        ),
        PlatformSessionStatus(
            code="cps",
            name="淘宝客 CPS",
            status="healthy" if cookie_ready and cps_token_ready else "attention",
            detail=(
                "已读取 CPS Cookie 与临时令牌。"
                if cookie_ready and cps_token_ready
                else "CPS 环境会话不完整，请同时配置 Cookie 与 CPS_TB_TOKEN。"
            ),
            authenticated=cookie_ready and cps_token_ready,
            cookie_detected=cookie_ready,
            cookie_count=cookie_count,
        ),
    ]
