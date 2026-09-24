from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import require_permission
from app.core.config import settings
from app.modules.imports.crawl_run_store import CrawlRunMissing, CrawlRunStore
from app.modules.imports.schemas import CrawlRunDetail, CrawlRunList
from app.modules.access.service import Principal

router = APIRouter()


def get_crawl_run_store() -> CrawlRunStore:
    return CrawlRunStore(Path(settings.local_database_path))


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
