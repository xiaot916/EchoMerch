from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field


class InventoryQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    store_id: int | None = Field(default=None, ge=1)
    business_day: date | None = None


class InventoryComponentResult(BaseModel):
    component_sku_id: str | None = None
    component_goods_no: str | None = None
    component_sku_barcode: str | None = None
    component_goods_name: str | None = None
    required_quantity: float
    available_quantity: float
    assemblable_quantity: int


class InventoryWarehouseResult(BaseModel):
    warehouse_id: str
    warehouse_name: str | None = None
    assemblable_quantity: int
    components: list[InventoryComponentResult] = Field(default_factory=list)


class InventoryItemResult(BaseModel):
    item_type: str
    store_id: int | None = None
    goods_id: str | None = None
    sku_id: str | None = None
    goods_no: str | None = None
    sku_no: str | None = None
    goods_name: str | None = None
    sku_name: str | None = None
    sku_barcode: str | None = None
    series: str | None = None
    specification: str | None = None
    size: str | None = None
    pieces: int | None = None
    display_name: str | None = None
    catalog_match_count: int = 0
    catalog_candidates: list[dict[str, Any]] = Field(default_factory=list)
    match_type: str | None = None
    matched_by: list[str] = Field(default_factory=list)
    candidate_count: int = 1
    business_day: date | None = None
    available_quantity: float | None = 0
    assemblable_quantity: int | None = None
    warehouses: list[InventoryWarehouseResult] = Field(default_factory=list)
    components: list[dict[str, Any]] = Field(default_factory=list)
    formula: str = ""
    warnings: list[str] = Field(default_factory=list)


class InventoryQueryResponse(BaseModel):
    status: str
    reason: Literal[
        "not_configured",
        "not_collected",
        "date_not_available",
        "product_not_matched",
        "code_known_no_snapshot",
        "ambiguous_code",
        "sku_not_matched",
        "zero_stock",
        "stockouts_found",
        "no_stockouts",
        "stockout_scope_partial",
        "matched",
    ] | None = None
    query: str
    business_day: date | None = None
    latest_snapshot_at: str | None = None
    latest_available_snapshot_at: str | None = None
    last_attempt_at: str | None = None
    latest_business_day: date | None = None
    snapshot_age_minutes: int | None = None
    freshness_status: str = "unknown"
    snapshot_row_count: int = 0
    items: list[InventoryItemResult] = Field(default_factory=list)
    query_terms: list[str] = Field(default_factory=list)
    matched_by: list[str] = Field(default_factory=list)
    match_type: str = "none"
    ambiguous: bool = False
    candidate_count: int = 0
    scope: dict[str, Any] = Field(default_factory=dict)
    checked_items: list[InventoryItemResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class InventorySyncStatusResponse(BaseModel):
    configured: bool
    credential_status: str = "unknown"
    credential_detail: str | None = None
    store_id: int | None = None
    status: str
    latest_business_day: date | None = None
    latest_snapshot_at: str | None = None
    last_attempt_at: str | None = None
    row_count: int = 0
    error_message: str | None = None
    refresh_minutes: int = 60
    freshness_status: str = "unknown"
    snapshot_age_minutes: int | None = None
    master_business_day: date | None = None
    master_status: str = "never_run"
    goods_status: str = "never_run"
    package_status: str = "never_run"
    goods_master_count: int = 0
    package_count: int = 0
    component_count: int = 0
    master_last_attempt_at: str | None = None
    master_finished_at: str | None = None
    master_error_message: str | None = None


class InventorySyncRequest(BaseModel):
    store_id: int | None = Field(default=None, ge=1)


class InventorySyncResponse(BaseModel):
    configured: bool
    refresh_minutes: int = 60
    results: list[dict[str, Any]] = Field(default_factory=list)


class InventoryManagementRow(BaseModel):
    id: int
    series: str = ""
    specification: str = ""
    size: str = ""
    goods_no: str
    pieces: int | None = None
    display_name: str | None = None
    available_quantity: float | None = None
    warehouse_count: int = 0
    min_warehouse_quantity: float | None = None
    stock_status: Literal["有库存", "低库存", "零库存", "未匹配库存"]
    catalog_match_count: int = 1
    business_day: date | None = None
    snapshot_at: str | None = None


class InventoryManagementResponse(BaseModel):
    summary: dict[str, int | float] = Field(default_factory=dict)
    latest_business_day: date | None = None
    latest_snapshot_at: str | None = None
    freshness_status: str = "unknown"
    snapshot_age_minutes: int | None = None
    dimensions: dict[str, list[str]] = Field(default_factory=dict)
    total: int = 0
    page: int = 1
    page_size: int = 50
    rows: list[InventoryManagementRow] = Field(default_factory=list)


class InventoryCompanyRow(BaseModel):
    """One deduplicated company/ERP SKU across all warehouses."""

    key: str
    goods_no: str = ""
    sku_no: str = ""
    goods_id: str = ""
    sku_id: str = ""
    goods_name: str | None = None
    sku_name: str | None = None
    sku_barcode: str = ""
    series: str = ""
    specification: str = ""
    size: str = ""
    pieces: int | None = None
    available_quantity: float = 0
    warehouse_count: int = 0
    stock_status: Literal["有库存", "低库存", "零库存"]
    catalog_match_count: int = 0
    business_day: date | None = None
    snapshot_at: str | None = None


class InventoryWarehouseSummary(BaseModel):
    warehouse_id: str
    warehouse_name: str | None = None
    sku_count: int = 0
    available_quantity: float = 0
    in_stock_count: int = 0
    low_stock_count: int = 0
    zero_stock_count: int = 0


class InventoryPackageRow(BaseModel):
    key: str
    goods_no: str = ""
    sku_no: str = ""
    goods_name: str | None = None
    sku_name: str | None = None
    component_count: int = 0
    stock_status: Literal["已同步明细", "待同步明细"]
    component_summary: list[str] = Field(default_factory=list)
    business_day: date | None = None


class InventoryAnalysisResponse(BaseModel):
    latest_business_day: date | None = None
    latest_snapshot_at: str | None = None
    freshness_status: str = "unknown"
    snapshot_age_minutes: int | None = None
    master_sync: dict[str, Any] = Field(default_factory=dict)
    company_summary: dict[str, int | float] = Field(default_factory=dict)
    warehouse_summary: list[InventoryWarehouseSummary] = Field(default_factory=list)
    company_rows: list[InventoryCompanyRow] = Field(default_factory=list)
    stockout_rows: list[InventoryCompanyRow] = Field(default_factory=list)
    package_summary: dict[str, int | float | str] = Field(default_factory=dict)
    package_rows: list[InventoryPackageRow] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
