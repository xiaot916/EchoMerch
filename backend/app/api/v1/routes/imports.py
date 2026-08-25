from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import require_permission
from app.core.config import settings
from app.modules.imports.crawl_run_store import CrawlRunMissing, CrawlRunStore
from app.modules.imports.run_store import ImportRunMissing, ImportRunStore
from app.modules.imports.schemas import (
    CreateImportRunRequest,
    CrawlRunDetail,
    CrawlRunList,
    DailyDryRunSummary,
    ImportRunDetail,
    ImportRunList,
)
from app.modules.imports.service import DryRunPlanMissing, ImportPlanService
from app.modules.access.service import Principal

router = APIRouter()


def get_import_service() -> ImportPlanService:
    return ImportPlanService(Path(settings.daily_dry_run_directory))


def get_import_run_store() -> ImportRunStore:
    return ImportRunStore(
        Path(settings.local_database_path),
        get_import_service(),
    )


def get_crawl_run_store() -> CrawlRunStore:
    return CrawlRunStore(Path(settings.local_database_path))


@router.get("/daily-dry-run", response_model=DailyDryRunSummary)
def get_daily_dry_run(
    day: str | None = Query(default=None),
    _: Principal = Depends(require_permission("data.manage")),
) -> DailyDryRunSummary:
    try:
        return get_import_service().get_latest_or_day(day)
    except DryRunPlanMissing as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runs/dry-run", response_model=ImportRunDetail)
def create_dry_run_import_run(
    request: CreateImportRunRequest,
    _: Principal = Depends(require_permission("data.manage")),
) -> ImportRunDetail:
    try:
        return get_import_run_store().create_from_dry_run(
            day=request.day,
            idempotency_key=request.idempotency_key,
        )
    except DryRunPlanMissing as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs", response_model=ImportRunList)
def list_import_runs(
    limit: int = Query(default=20, ge=1, le=100),
    _: Principal = Depends(require_permission("data.manage")),
) -> ImportRunList:
    return get_import_run_store().list_runs(limit=limit)


@router.get("/runs/{run_id}", response_model=ImportRunDetail)
def get_import_run(
    run_id: str,
    _: Principal = Depends(require_permission("data.manage")),
) -> ImportRunDetail:
    try:
        return get_import_run_store().get_detail(run_id)
    except ImportRunMissing as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/crawl-runs", response_model=CrawlRunList)
def list_crawl_runs(
    limit: int = Query(default=20, ge=1, le=100),
    _: Principal = Depends(require_permission("data.manage")),
) -> CrawlRunList:
    return get_crawl_run_store().list_runs(limit=limit)


@router.get("/crawl-runs/{run_id}", response_model=CrawlRunDetail)
def get_crawl_run(
    run_id: str,
    _: Principal = Depends(require_permission("data.manage")),
) -> CrawlRunDetail:
    try:
        return get_crawl_run_store().get_detail(run_id)
    except CrawlRunMissing as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
