from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.api.dependencies import require_permission, resolve_store_scope
from app.core.config import settings
from app.modules.access.service import Principal
from app.modules.warehouse.store_data import StoreDataLimitExceeded, StoreDataService, StoreDatasetMissing
from app.modules.warehouse.store_data_schemas import StoreDataCatalog, StoreDataPreview

router = APIRouter()


def get_store_data_service() -> StoreDataService:
    return StoreDataService(Path(settings.local_database_path))


@router.get("/datasets", response_model=StoreDataCatalog)
def list_store_data_datasets(
    store_id: int | None = Query(default=None),
    principal: Principal = Depends(require_permission("data.manage")),
) -> StoreDataCatalog:
    resolved_store_id = resolve_store_scope(principal, store_id)
    if resolved_store_id is None:
        raise HTTPException(status_code=400, detail="请选择店铺后再查看店铺数据。")
    datasets = get_store_data_service().list_datasets(resolved_store_id)
    reference_date = max((item["latest_date"] for item in datasets if item["latest_date"]), default=None)
    return StoreDataCatalog(
        store_id=resolved_store_id,
        reference_date=reference_date,
        available_count=sum(item["row_count"] > 0 for item in datasets),
        current_count=sum(item["status"] == "current" for item in datasets),
        stale_count=sum(item["status"] == "stale" for item in datasets),
        empty_count=sum(item["status"] == "empty" for item in datasets),
        datasets=datasets,
    )


@router.get("/preview", response_model=StoreDataPreview)
def preview_store_data(
    dataset: str,
    store_id: int | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    search: str | None = Query(default=None, max_length=80),
    principal: Principal = Depends(require_permission("data.manage")),
) -> StoreDataPreview:
    resolved_store_id = resolve_store_scope(principal, store_id)
    if resolved_store_id is None:
        raise HTTPException(status_code=400, detail="请选择店铺后再查看店铺数据。")
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期。")
    try:
        return StoreDataPreview(
            **get_store_data_service().preview(
                store_id=resolved_store_id,
                dataset_key=dataset,
                start_date=start_date,
                end_date=end_date,
                page=page,
                page_size=page_size,
                search=search,
            )
        )
    except StoreDatasetMissing as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/export")
def export_store_data(
    dataset: str,
    file_format: str = Query(default="xlsx", alias="format", pattern="^(csv|xlsx)$"),
    store_id: int | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    search: str | None = Query(default=None, max_length=80),
    principal: Principal = Depends(require_permission("data.manage")),
) -> Response:
    resolved_store_id = resolve_store_scope(principal, store_id)
    if resolved_store_id is None:
        raise HTTPException(status_code=400, detail="请选择店铺后再导出数据。")
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期。")
    try:
        payload, media_type, extension = get_store_data_service().export(
            store_id=resolved_store_id,
            dataset_key=dataset,
            start_date=start_date,
            end_date=end_date,
            search=search,
            file_format=file_format,
        )
    except StoreDatasetMissing as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StoreDataLimitExceeded as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    filename = f"store_{resolved_store_id}_{dataset}{extension}"
    disposition = f"attachment; filename=export{extension}; filename*=UTF-8''{quote(filename)}"
    return Response(content=payload, media_type=media_type, headers={"Content-Disposition": disposition})
