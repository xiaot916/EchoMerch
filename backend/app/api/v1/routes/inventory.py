from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import require_permission, resolve_store_scope
from app.core.config import settings
from app.integrations.jackyun_inventory import JackyunClient, JackyunInventorySyncService
from app.modules.access.service import Principal
from app.modules.inventory.schemas import (
    InventoryAnalysisResponse,
    InventoryManagementResponse,
    InventoryQueryRequest,
    InventoryQueryResponse,
    InventorySyncRequest,
    InventorySyncResponse,
    InventorySyncStatusResponse,
)
from app.modules.inventory.service import InventoryService


router = APIRouter()


def get_inventory_service() -> InventoryService:
    from pathlib import Path

    return InventoryService(Path(settings.local_database_path))


@router.get("/query", response_model=InventoryQueryResponse)
def query_inventory(
    query: str = Query(min_length=1, max_length=200),
    store_id: int | None = Query(default=None, ge=1),
    service: InventoryService = Depends(get_inventory_service),
    principal: Principal = Depends(require_permission("analytics.read")),
) -> InventoryQueryResponse:
    try:
        return InventoryQueryResponse.model_validate(service.query(
            store_id=resolve_store_scope(principal, store_id), query=query,
        ))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/query", response_model=InventoryQueryResponse)
def query_inventory_post(
    request: InventoryQueryRequest,
    service: InventoryService = Depends(get_inventory_service),
    principal: Principal = Depends(require_permission("analytics.read")),
) -> InventoryQueryResponse:
    try:
        return InventoryQueryResponse.model_validate(service.query(
            store_id=resolve_store_scope(principal, request.store_id),
            query=request.query,
            business_day=request.business_day,
        ))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/management", response_model=InventoryManagementResponse)
def inventory_management(
    store_id: int | None = Query(default=None, ge=1),
    query: str | None = Query(default=None, max_length=120),
    series: str | None = Query(default=None, max_length=80),
    specification: str | None = Query(default=None, max_length=120),
    size: str | None = Query(default=None, max_length=20),
    stock_status: str | None = Query(default=None, max_length=20),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    service: InventoryService = Depends(get_inventory_service),
    principal: Principal = Depends(require_permission("analytics.read")),
) -> InventoryManagementResponse:
    resolved_store_id = resolve_store_scope(principal, store_id)
    return InventoryManagementResponse.model_validate(service.management(
        store_id=resolved_store_id,
        query=query,
        series=series,
        specification=specification,
        size=size,
        stock_status=stock_status,
        page=page,
        page_size=page_size,
    ))


@router.get("/analysis", response_model=InventoryAnalysisResponse)
def inventory_analysis(
    store_id: int | None = Query(default=None, ge=1),
    query: str | None = Query(default=None, max_length=120),
    stock_status: str | None = Query(default=None, max_length=20),
    limit: int = Query(default=200, ge=1, le=1000),
    service: InventoryService = Depends(get_inventory_service),
    principal: Principal = Depends(require_permission("analytics.read")),
) -> InventoryAnalysisResponse:
    resolved_store_id = resolve_store_scope(principal, store_id)
    return InventoryAnalysisResponse.model_validate(service.analysis(
        store_id=resolved_store_id,
        query=query,
        stock_status=stock_status,
        limit=limit,
    ))


@router.get("/sync/status", response_model=InventorySyncStatusResponse)
def get_inventory_sync_status(
    store_id: int | None = Query(default=None, ge=1),
    service: InventoryService = Depends(get_inventory_service),
    principal: Principal = Depends(require_permission("analytics.read")),
) -> InventorySyncStatusResponse:
    resolved_store_id = resolve_store_scope(principal, store_id)
    status = service.get_sync_status(resolved_store_id)
    credentials = JackyunClient().credential_status()
    if credentials.get("status") == "not_configured":
        status["status"] = "not_configured"
    elif credentials.get("status") == "invalid":
        status["status"] = "credential_invalid"
    return InventorySyncStatusResponse(
        configured=bool(credentials.get("configured")),
        credential_status=str(credentials.get("status") or "unknown"),
        credential_detail=credentials.get("detail"),
        refresh_minutes=settings.jackyun_inventory_refresh_minutes,
        **status,
    )


@router.post("/sync", response_model=InventorySyncResponse)
def sync_inventory_now(
    request: InventorySyncRequest,
    principal: Principal = Depends(require_permission("data.manage")),
) -> InventorySyncResponse:
    resolved_store_id = resolve_store_scope(principal, request.store_id)
    sync_service = JackyunInventorySyncService()
    if not sync_service.client.configured:
        return InventorySyncResponse(
            configured=False,
            refresh_minutes=settings.jackyun_inventory_refresh_minutes,
            results=[{"status": "not_configured", "store_id": resolved_store_id, "row_count": 0}],
        )
    store_ids = [resolved_store_id] if resolved_store_id else sync_service.store_ids()
    results: list[dict[str, object]] = []
    for store_id in store_ids:
        result = sync_service.sync_store(store_id)
        # Do not return raw exception strings or platform responses: they may
        # contain request URLs, headers, or tenant-specific credentials.
        results.append({
            "status": result.get("status"),
            "store_id": store_id,
            "row_count": result.get("row_count", 0),
            "package_count": result.get("package_count", 0),
            "goods_master_count": result.get("goods_master_count", 0),
            "component_count": result.get("component_count", 0),
            "master_status": result.get("master_status"),
            "goods_status": result.get("goods_status"),
            "package_status": result.get("package_status"),
            "business_day": result.get("business_day"),
            "fetched_at": result.get("fetched_at"),
            "error_message": result.get("error"),
        })
    return InventorySyncResponse(
        configured=True,
        refresh_minutes=settings.jackyun_inventory_refresh_minutes,
        results=results,
    )
