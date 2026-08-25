from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class PlatformRecord(BaseModel):
    platform_id: int
    code: str
    name: str
    status: str


class StoreRecord(BaseModel):
    store_id: int
    platform_id: int
    platform_name: str
    platform_store_id: str
    store_name: str
    status: str
    first_seen_at: str
    updated_at: str


class StoreDailyOverview(BaseModel):
    store_id: int
    business_day: date
    paid_amount: Decimal = Decimal("0")
    net_paid_amount: Decimal = Decimal("0")
    visitors: int = 0
    paid_buyers: int = 0
    conversion_rate: Decimal = Decimal("0")
    sign_refund_rate: Decimal = Decimal("0")
    refund_finished_amount: Decimal = Decimal("0")
    keyword_promotion_spend: Decimal = Decimal("0")
    precision_audience_promotion_spend: Decimal = Decimal("0")
    smart_scene_spend: Decimal = Decimal("0")
    all_site_promotion_spend: Decimal = Decimal("0")
    taoke_commission: Decimal = Decimal("0")
    total_paid_amount: Decimal = Decimal("0")
    refund_paid_time_amount: Decimal = Decimal("0")
    amount_refund_rate: Decimal = Decimal("0")
    add_cart_buyers: int = 0
    product_favorite_buyers: int = 0
    page_views: int = 0
    average_stay_time: Decimal = Decimal("0")
    add_cart_items: int = 0
    paid_sub_order_count: int = 0
    total_paid_sub_order_count: int = 0
    order_refund_rate: Decimal = Decimal("0")
    paid_items: int = 0
    customer_unit_price: Decimal = Decimal("0")
    older_paid_amount: Decimal = Decimal("0")
    older_paid_buyers: int = 0
    older_repurchase_rate: Decimal = Decimal("0")
    refund_process_days: Decimal = Decimal("0")
    wangwang_manual_response_seconds: Decimal = Decimal("0")
    consultation_rate: Decimal = Decimal("0")
    platform_duty_rate: Decimal = Decimal("0")
    pickup_24h_rate: Decimal = Decimal("0")
    logistics_arrival_hours: Decimal = Decimal("0")


class StoreDailyFlowOverviewMetric(BaseModel):
    label: str
    metric_code: str | None = None
    value: Decimal | None = None
    unit: str
    confirmation_status: str


class StoreDailyFlowOverview(BaseModel):
    store_id: int
    business_day: date
    metrics: list[StoreDailyFlowOverviewMetric]


class StoreActivityCalendarEvent(BaseModel):
    store_id: int
    business_day: date
    activity_id: str
    activity_name: str = ""
    activity_type: str = ""
    activity_status: str = ""
    activity_start_time: str = ""
    activity_end_time: str = ""
    signup_start_time: str = ""
    signup_end_time: str = ""
    activity_tag: str = ""
    activity_level: str = ""
    activity_stage: str = ""


class StoreProductCatalogItem(BaseModel):
    store_id: int
    product_id: str
    product_name: str = ""
    product_type: str = ""
    attribute: str = ""
    series: str = ""
    positioning: str = ""
    channel: str = ""


class MetricDefinition(BaseModel):
    metric_code: str
    metric_name: str
    metric_group: str
    unit: str
    description: str
    confirmation_status: str
    updated_at: str


class WarehouseIngestResult(BaseModel):
    platform: PlatformRecord
    store: StoreRecord
    business_day: date
    source_artifact_id: str
    metric_count: int
    overview: StoreDailyOverview
    warnings: list[str] = Field(default_factory=list)


class WarehouseMetricIngestResult(BaseModel):
    platform: PlatformRecord
    store: StoreRecord
    business_day: date
    source_artifact_id: str
    metric_count: int
    warnings: list[str] = Field(default_factory=list)


class ProductRankingIngestResult(BaseModel):
    platform: PlatformRecord
    store: StoreRecord
    business_day: date
    row_count: int
    warnings: list[str] = Field(default_factory=list)
