from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from app.api.dependencies import require_permission
from app.core.config import settings
from app.integrations.collection_browser import (
    CollectionBrowserLaunchError,
    browser_debug_connected,
    launch_collection_browser,
)
from app.modules.access.service import Principal
from app.modules.collection.locks import active_daily_batch, active_feedback_run
from app.modules.reviews.schemas import AskCollectRequest, AskListResponse, AskSummary, ReviewAnalysis, ReviewCollectionRun, ReviewCollectionSummary, ReviewCollectRequest, ReviewListResponse
from app.modules.reviews.service import ReviewCollectionError, ReviewService


router = APIRouter()


def get_review_service() -> ReviewService:
    return ReviewService(Path(settings.local_database_path))


def _ensure_review_browser() -> None:
    env_cookie_ready = settings.tmall_session_source == "env" and bool(
        os.getenv(settings.tmall_cookie_env, "").strip()
    )
    if env_cookie_ready or browser_debug_connected(settings.tmall_browser_port):
        return
    launch_collection_browser(settings.tmall_browser_port)


def _ensure_feedback_collection_slot(kind: str) -> None:
    database_path = Path(settings.local_database_path)
    batch_id = active_daily_batch(database_path)
    if batch_id is not None:
        raise HTTPException(
            status_code=409,
            detail=f"日常经营采集正在运行（{batch_id}），请等待完成后再启动{kind}采集。",
        )
    feedback_run = active_feedback_run(database_path)
    if feedback_run is not None:
        label, run_id = feedback_run
        raise HTTPException(
            status_code=409,
            detail=f"{label}采集任务正在运行（{run_id}），请等待完成后再启动{kind}采集。",
        )


@router.get("/summary", response_model=ReviewCollectionSummary)
def get_summary(_: Principal = Depends(require_permission("analytics.read"))) -> ReviewCollectionSummary:
    return get_review_service().summary()


@router.get("/products")
def get_products(_: Principal = Depends(require_permission("analytics.read"))) -> list[dict[str, str | int | None]]:
    return get_review_service().list_products()


@router.get("/series")
def get_series(_: Principal = Depends(require_permission("analytics.read"))) -> list[dict[str, str | int | None]]:
    return get_review_service().list_series()


@router.get("/analysis", response_model=ReviewAnalysis)
def get_analysis(
    product_id: str | None = Query(default=None, max_length=120),
    series: str | None = Query(default=None, max_length=120),
    sentiment: str | None = Query(default=None, pattern="^(positive|neutral|negative|unknown)$"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    _: Principal = Depends(require_permission("analytics.read")),
) -> ReviewAnalysis:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期。")
    return get_review_service().analysis(
        product_id=product_id,
        series=series,
        sentiment=sentiment,
        start_date=start_date.isoformat() if start_date else None,
        end_date=end_date.isoformat() if end_date else None,
    )


@router.get("", response_model=ReviewListResponse)
def get_reviews(
    product_id: str | None = Query(default=None, max_length=120),
    series: str | None = Query(default=None, max_length=120),
    category: str | None = Query(default=None, max_length=80),
    sentiment: str | None = Query(default=None, pattern="^(positive|neutral|negative|unknown)$"),
    search: str | None = Query(default=None, max_length=120),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=20, ge=1, le=100),
    _: Principal = Depends(require_permission("analytics.read")),
) -> ReviewListResponse:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期。")
    return get_review_service().list_reviews(
        product_id=product_id,
        series=series,
        category=category,
        sentiment=sentiment,
        search=search,
        start_date=start_date.isoformat() if start_date else None,
        end_date=end_date.isoformat() if end_date else None,
        page=page,
        page_size=page_size,
    )


@router.get("/runs", response_model=list[ReviewCollectionRun])
def get_runs(
    limit: int = Query(default=20, ge=1, le=100),
    _: Principal = Depends(require_permission("data.manage")),
) -> list[ReviewCollectionRun]:
    # A worker can disappear during browser preflight or process restart. Run
    # the same stale-lock reconciliation used by collection entry points so
    # the UI does not keep showing a permanently running task.
    active_feedback_run(Path(settings.local_database_path))
    service = get_review_service()
    conn = service.database.connect()
    try:
        rows = conn.execute("select * from review_collection_runs order by started_at desc limit ?", (limit,)).fetchall()
    finally:
        conn.close()
    return [ReviewCollectionRun(**dict(row)) for row in rows]


@router.post("/collect", response_model=ReviewCollectionRun)
def collect_reviews(
    request: ReviewCollectRequest,
    background_tasks: BackgroundTasks,
    _: Principal = Depends(require_permission("data.manage")),
) -> ReviewCollectionRun:
    try:
        _ensure_feedback_collection_slot("评价")
        _ensure_review_browser()
        service = get_review_service()
        try:
            start_date = date.fromisoformat(request.start_date)
            end_date = date.fromisoformat(request.end_date) if request.end_date else date.today()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="采集日期格式必须为 YYYY-MM-DD。") from exc
        if start_date > end_date:
            raise HTTPException(status_code=400, detail="采集开始日期不能晚于结束日期。")
        run = service.start_collection(mode=request.mode)
        background_tasks.add_task(
            service.execute_collection,
            run.run_id,
            mode=request.mode,
            max_pages=request.max_pages,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
        )
        return run
    except (CollectionBrowserLaunchError, ReviewCollectionError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/asks/summary", response_model=AskSummary)
def get_ask_summary(_: Principal = Depends(require_permission("analytics.read"))) -> AskSummary:
    return get_review_service().ask_summary()


@router.get("/asks", response_model=AskListResponse)
def get_asks(
    product_id: str | None = Query(default=None, max_length=120),
    series: str | None = Query(default=None, max_length=120),
    category: str | None = Query(default=None, max_length=80),
    search: str | None = Query(default=None, max_length=120),
    has_answer: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=20, ge=1, le=100),
    _: Principal = Depends(require_permission("analytics.read")),
) -> AskListResponse:
    return get_review_service().list_asks(
        product_id=product_id,
        series=series,
        category=category,
        search=search,
        has_answer=has_answer,
        page=page,
        page_size=page_size,
    )


@router.get("/asks/runs", response_model=list[ReviewCollectionRun])
def get_ask_runs(
    limit: int = Query(default=20, ge=1, le=100),
    _: Principal = Depends(require_permission("data.manage")),
) -> list[ReviewCollectionRun]:
    active_feedback_run(Path(settings.local_database_path))
    return get_review_service().ask_runs(limit)


@router.post("/asks/collect", response_model=ReviewCollectionRun)
def collect_asks(
    request: AskCollectRequest,
    background_tasks: BackgroundTasks,
    _: Principal = Depends(require_permission("data.manage")),
) -> ReviewCollectionRun:
    try:
        _ensure_feedback_collection_slot("问答")
        _ensure_review_browser()
        service = get_review_service()
        run = service.start_ask_collection(mode=request.mode)
        background_tasks.add_task(service.execute_ask_collection, run.run_id, mode=request.mode, max_pages=request.max_pages)
        return run
    except (CollectionBrowserLaunchError, ReviewCollectionError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
