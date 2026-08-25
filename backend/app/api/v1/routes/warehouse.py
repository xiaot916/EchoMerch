from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import require_permission, resolve_store_scope
from app.core.config import settings
from app.warehouse.schemas import (
    MetricDefinition,
    PlatformRecord,
    StoreActivityCalendarEvent,
    StoreDailyFlowOverview,
    StoreDailyOverview,
    StoreRecord,
)
from app.warehouse.store import WarehouseDataNotAvailable, WarehouseStore
from app.modules.access.service import Principal

router = APIRouter()


def get_warehouse_store() -> WarehouseStore:
    return WarehouseStore(Path(settings.local_database_path))


@router.get("/platforms", response_model=list[PlatformRecord])
def list_platforms(_: Principal = Depends(require_permission("warehouse.read"))) -> list[PlatformRecord]:
    return get_warehouse_store().list_platforms()


@router.get("/stores", response_model=list[StoreRecord])
def list_stores(principal: Principal = Depends(require_permission("warehouse.read"))) -> list[StoreRecord]:
    return [store for store in get_warehouse_store().list_stores() if principal.allows_store(store.store_id)]


@router.get("/metric-definitions", response_model=list[MetricDefinition])
def list_metric_definitions(_: Principal = Depends(require_permission("warehouse.read"))) -> list[MetricDefinition]:
    return get_warehouse_store().list_metric_definitions()


@router.get("/stores/{store_id}/daily-overview", response_model=StoreDailyOverview)
def get_daily_overview(
    store_id: int,
    day: date | None = Query(default=None),
    principal: Principal = Depends(require_permission("warehouse.read")),
) -> StoreDailyOverview:
    overview = get_warehouse_store().get_daily_overview(
        store_id=resolve_store_scope(principal, store_id) or store_id,
        business_day=day,
    )
    if overview is None:
        raise HTTPException(
            status_code=404,
            detail=f"No daily overview found for store {store_id}.",
        )
    return overview


@router.get("/stores/{store_id}/daily-flow-overview", response_model=StoreDailyFlowOverview)
def get_daily_flow_overview(
    store_id: int,
    day: date | None = Query(default=None),
    principal: Principal = Depends(require_permission("warehouse.read")),
) -> StoreDailyFlowOverview:
    overview = get_warehouse_store().get_daily_flow_overview(
        store_id=resolve_store_scope(principal, store_id) or store_id,
        business_day=day,
    )
    if overview is None:
        raise HTTPException(
            status_code=404,
            detail=f"No daily flow overview found for store {store_id}.",
    )
    return overview


@router.get("/stores/{store_id}/activity-calendar", response_model=list[StoreActivityCalendarEvent])
def get_activity_calendar_events(
    store_id: int,
    day: date | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    principal: Principal = Depends(require_permission("warehouse.read")),
) -> list[StoreActivityCalendarEvent]:
    return get_warehouse_store().get_activity_calendar_events(
        store_id=resolve_store_scope(principal, store_id) or store_id,
        business_day=day,
        start_date=start_date,
        end_date=end_date,
    )
