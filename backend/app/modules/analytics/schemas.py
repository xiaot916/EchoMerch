from datetime import date
from decimal import Decimal

from typing import Literal

from pydantic import BaseModel, Field


class DailyMetric(BaseModel):
    stat_date: date
    paid_amount: Decimal
    visitors: int
    conversion_rate: Decimal
    promotion_cost: Decimal
    buyers: int
    refund_amount: Decimal = Decimal("0")
    refund_rate: Decimal = Decimal("0")
    promotion_plan_spend: Decimal = Decimal("0")
    promotion_attributed_paid_amount: Decimal = Decimal("0")


class ProductMetric(BaseModel):
    product_id: str
    product_name: str
    paid_amount: Decimal
    buyers: int
    visitors: int
    add_cart_users: int = 0
    favorite_users: int = 0
    page_views: int = 0
    search_visitors: int = 0
    promotion_spend: Decimal = Decimal("0")
    product_type: str = "未分类"
    series: str = "未分类"
    positioning: str = "未分类"


class ProductAnalysisDailyMetric(BaseModel):
    stat_date: date
    paid_amount: Decimal = Decimal("0")
    buyers: int = 0
    visitors: int = 0
    add_cart_users: int = 0
    favorite_users: int = 0
    promotion_spend: Decimal = Decimal("0")
    conversion_rate: Decimal = Decimal("0")


class ProductAnalysisResponse(BaseModel):
    range_start: date
    range_end: date
    products: list[ProductMetric] = Field(default_factory=list)
    product: ProductMetric | None = None
    daily_metrics: list[ProductAnalysisDailyMetric] = Field(default_factory=list)
    peers: list[ProductMetric] = Field(default_factory=list)


class TrafficMetric(BaseModel):
    source_name: str
    visitors: int
    paid_amount: Decimal
    buyers: int
    new_visitors: int = 0
    add_cart_users: int = 0
    favorite_users: int = 0
    conversion_rate: Decimal = Decimal("0")
    uv_value: Decimal = Decimal("0")


class TrafficTreeNode(BaseModel):
    id: str
    parent_id: str | None = None
    level: Literal[1, 2, 3]
    name: str
    path: list[str] = Field(default_factory=list)
    visitors: int = 0
    paid_amount: Decimal = Decimal("0")
    buyers: int = 0
    new_visitors: int = 0
    add_cart_users: int = 0
    favorite_users: int = 0
    conversion_rate: Decimal = Decimal("0")
    uv_value: Decimal = Decimal("0")
    derived_from_children: bool = False
    children: list["TrafficTreeNode"] = Field(default_factory=list)


class PromotionMetric(BaseModel):
    plan_name: str
    scene_name: str | None = None
    spend: Decimal
    paid_amount: Decimal | None = None
    buyers: int | None = None


class PromotionSceneMetric(BaseModel):
    scene_name: str
    campaign_count: int = 0
    spend: Decimal = Decimal("0")
    paid_amount: Decimal = Decimal("0")
    buyers: int = 0


class PromotionSummaryMetric(BaseModel):
    campaign_count: int = 0
    impressions: int = 0
    clicks: int = 0
    spend: Decimal = Decimal("0")
    paid_amount: Decimal = Decimal("0")
    direct_paid_amount: Decimal = Decimal("0")
    indirect_paid_amount: Decimal = Decimal("0")
    orders: int = 0
    buyers: int = 0
    carts: int = 0
    favorites: int = 0
    new_buyers: int = 0
    member_paid_amount: Decimal = Decimal("0")
    natural_paid_amount: Decimal = Decimal("0")
    roi: Decimal = Decimal("0")
    click_rate: Decimal = Decimal("0")
    average_click_cost: Decimal = Decimal("0")
    click_conversion_rate: Decimal = Decimal("0")
    buyer_acquisition_cost: Decimal = Decimal("0")
    new_buyer_share: Decimal = Decimal("0")


class PromotionDailyMetric(BaseModel):
    stat_date: date
    impressions: int = 0
    clicks: int = 0
    spend: Decimal = Decimal("0")
    paid_amount: Decimal = Decimal("0")
    orders: int = 0
    buyers: int = 0
    carts: int = 0
    new_buyers: int = 0


class PromotionDimensionMetric(BaseModel):
    dimension_id: str
    dimension_name: str
    scene_name: str = ""
    campaign_id: str = ""
    campaign_name: str = ""
    parent_id: str = ""
    parent_name: str = ""
    subject_id: str = ""
    subject_name: str = ""
    impressions: int = 0
    clicks: int = 0
    spend: Decimal = Decimal("0")
    paid_amount: Decimal = Decimal("0")
    direct_paid_amount: Decimal = Decimal("0")
    indirect_paid_amount: Decimal = Decimal("0")
    orders: int = 0
    buyers: int = 0
    carts: int = 0
    favorites: int = 0
    new_buyers: int = 0
    member_paid_amount: Decimal = Decimal("0")
    natural_paid_amount: Decimal = Decimal("0")


class PromotionLayerCoverage(BaseModel):
    key: str
    label: str
    covered_days: int = 0
    row_count: int = 0
    entity_count: int = 0


class PromotionWorkbenchResponse(BaseModel):
    range_start: date
    range_end: date
    summary: PromotionSummaryMetric
    daily_metrics: list[PromotionDailyMetric] = Field(default_factory=list)
    scenes: list[PromotionDimensionMetric] = Field(default_factory=list)
    campaigns: list[PromotionDimensionMetric] = Field(default_factory=list)
    adgroups: list[PromotionDimensionMetric] = Field(default_factory=list)
    audiences: list[PromotionDimensionMetric] = Field(default_factory=list)
    keywords: list[PromotionDimensionMetric] = Field(default_factory=list)
    items: list[PromotionDimensionMetric] = Field(default_factory=list)
    contents: list[PromotionDimensionMetric] = Field(default_factory=list)
    coverage: list[PromotionLayerCoverage] = Field(default_factory=list)


class FlashSaleDailyMetric(BaseModel):
    stat_date: date
    item_count: int | None = None
    ipv: int | None = None
    ipv_uv: int | None = None
    paid_order_count: int | None = None
    paid_amount: Decimal | None = None
    new_customers: int | None = None
    burst_coefficient: Decimal | None = None
    record_status: Literal["complete", "empty", "missing"] = "missing"


class FlashSaleSummary(BaseModel):
    active_days: int = 0
    item_count_peak: int | None = None
    ipv: int = 0
    ipv_uv: int = 0
    paid_order_count: int = 0
    paid_amount: Decimal = Decimal("0")
    new_customers: int = 0
    burst_coefficient_peak: Decimal | None = None
    conversion_rate: Decimal = Decimal("0")
    customer_unit_price: Decimal = Decimal("0")
    shop_paid_amount: Decimal | None = None
    shop_paid_share: Decimal | None = None


class FlashSaleComparison(BaseModel):
    paid_amount_change_percent: Decimal | None = None
    paid_order_count_change_percent: Decimal | None = None
    ipv_uv_change_percent: Decimal | None = None
    new_customers_change_percent: Decimal | None = None


class FlashSaleAnalysisResponse(BaseModel):
    range_start: date
    range_end: date
    latest_available_date: date | None = None
    summary: FlashSaleSummary
    previous_summary: FlashSaleSummary
    comparison: FlashSaleComparison
    daily_metrics: list[FlashSaleDailyMetric] = Field(default_factory=list)
    coverage: list[date] = Field(default_factory=list)
    empty_dates: list[date] = Field(default_factory=list)
    missing_dates: list[date] = Field(default_factory=list)


class UtryDailyMetric(BaseModel):
    stat_date: date
    sample_status: Literal["complete", "no_data", "missing"] = "missing"
    repurchase_status: Literal["complete", "no_data", "missing"] = "missing"
    sample_people: int | None = None
    sample_orders: int | None = None
    sample_gmv: Decimal | None = None
    merchant_new_customers_180d: int | None = None
    merchant_new_customers_365d: int | None = None
    new_members: int | None = None
    new_followers: int | None = None
    store_30d_repurchase_amount: Decimal | None = None
    store_90d_repurchase_amount: Decimal | None = None
    store_365d_repurchase_amount: Decimal | None = None


class UtryProductMetric(BaseModel):
    product_id: str
    product_name: str = ""
    sample_people: int | None = None
    sample_orders: int | None = None
    sample_gmv: Decimal | None = None
    merchant_new_customers_180d: int | None = None
    merchant_new_customers_365d: int | None = None
    new_members: int | None = None
    new_followers: int | None = None
    store_30d_repurchase_uv: int | None = None
    store_30d_repurchase_amount: Decimal | None = None
    store_90d_repurchase_uv: int | None = None
    store_90d_repurchase_amount: Decimal | None = None
    store_365d_repurchase_uv: int | None = None
    store_365d_repurchase_amount: Decimal | None = None
    brand_365d_repurchase_amount: Decimal | None = None
    leaf_category: str = ""
    bind_regular_product: str = ""
    configured_repurchase_coupon: str = ""
    configured_repurchase_gift: str = ""
    diagnostic_tag: str = ""


class UtrySampleSummary(BaseModel):
    sample_orders: int = 0
    sample_people: int = 0
    sample_gmv: Decimal = Decimal("0")
    merchant_new_customers_180d: int = 0
    merchant_new_customers_365d: int = 0
    new_members: int = 0
    new_followers: int = 0
    average_orders_per_person: Decimal = Decimal("0")
    sample_gmv_per_person: Decimal = Decimal("0")
    merchant_new_customer_rate_180d: Decimal | None = None
    merchant_new_customer_rate_365d: Decimal | None = None


class UtryRepurchaseSnapshot(BaseModel):
    business_day: date | None = None
    product_count: int = 0
    bound_regular_product_count: int = 0
    configured_coupon_count: int = 0
    configured_gift_count: int = 0
    bound_regular_product_share: Decimal | None = None
    configured_coupon_share: Decimal | None = None
    configured_gift_share: Decimal | None = None
    store_30d_repurchase_uv: int = 0
    store_30d_repurchase_amount: Decimal = Decimal("0")
    store_90d_repurchase_uv: int = 0
    store_90d_repurchase_amount: Decimal = Decimal("0")
    store_365d_repurchase_uv: int = 0
    store_365d_repurchase_amount: Decimal = Decimal("0")
    brand_365d_repurchase_uv: int = 0
    brand_365d_repurchase_amount: Decimal = Decimal("0")


class UtryAnalysisResponse(BaseModel):
    range_start: date
    range_end: date
    latest_sample_date: date | None = None
    latest_repurchase_date: date | None = None
    sample_summary: UtrySampleSummary = Field(default_factory=UtrySampleSummary)
    latest_repurchase: UtryRepurchaseSnapshot = Field(default_factory=UtryRepurchaseSnapshot)
    previous_repurchase: UtryRepurchaseSnapshot = Field(default_factory=UtryRepurchaseSnapshot)
    daily_metrics: list[UtryDailyMetric] = Field(default_factory=list)
    products: list[UtryProductMetric] = Field(default_factory=list)
    sample_coverage: "DataCoverage | None" = None
    repurchase_coverage: "DataCoverage | None" = None
    warnings: list[str] = Field(default_factory=list)


class PromotionProductMetric(BaseModel):
    product_id: str
    product_name: str = ""
    activity_id: str = ""
    activity_name: str = ""
    category_name: str = ""
    activity_status: str = ""
    visitors: int | None = None
    paid_order_count: int | None = None
    paid_items: int | None = None
    paid_amount: Decimal | None = None
    new_customers: int | None = None
    conversion_rate: Decimal | None = None
    active_days: int = 0


class PromotionProductListResponse(BaseModel):
    range_start: date
    range_end: date
    available_start: date | None = None
    available_end: date | None = None
    missing_dates: list[date] = Field(default_factory=list)
    total: int
    page: int
    page_size: int
    items: list[PromotionProductMetric] = Field(default_factory=list)


class DataFreshness(BaseModel):
    dataset: str
    latest_date: date
    first_date: date | None = None


class DataCoverage(BaseModel):
    dataset: str
    first_date: date | None = None
    latest_date: date | None = None
    expected_days: int = 0
    covered_days: int = 0
    missing_dates: list[date] = Field(default_factory=list)
    no_data_dates: list[date] = Field(default_factory=list)
    status: Literal["complete", "partial", "empty"] = "empty"


class DashboardPeriod(BaseModel):
    requested_start: date
    requested_end: date
    previous_start: date
    previous_end: date
    expected_days: int
    covered_days: int
    missing_dates: list[date] = Field(default_factory=list)


class ComparisonMetric(BaseModel):
    current: Decimal
    previous: Decimal
    delta: Decimal
    change_percent: Decimal | None = None


class SummaryComparison(BaseModel):
    paid_amount: ComparisonMetric
    visitors: ComparisonMetric
    buyers: ComparisonMetric
    conversion_rate: ComparisonMetric
    promotion_cost: ComparisonMetric
    customer_unit_price: ComparisonMetric | None = None


class BusinessInsight(BaseModel):
    level: Literal["warning", "positive", "info"]
    title: str
    detail: str
    action: str | None = None


class DecisionMetric(BaseModel):
    id: str
    label: str
    value: Decimal | int | None = None
    unit: Literal["currency", "count", "percent", "ratio"] = "count"
    formula: str
    source_metric_ids: list[str] = Field(default_factory=list)
    status: Literal["available", "unavailable", "inconsistent"] = "available"
    note: str = ""


class SummaryMetric(BaseModel):
    paid_amount: Decimal
    visitors: int
    buyers: int
    conversion_rate: Decimal
    promotion_cost: Decimal
    roi: Decimal
    average_daily_paid_amount: Decimal = Decimal("0")
    customer_unit_price: Decimal = Decimal("0")
    refund_amount: Decimal = Decimal("0")
    net_paid_amount: Decimal = Decimal("0")
    promotion_plan_spend: Decimal = Decimal("0")
    promotion_attributed_paid_amount: Decimal = Decimal("0")
    promotion_roi: Decimal = Decimal("0")
    promotion_fee_ratio: Decimal = Decimal("0")


class AnalysisDailyMetric(BaseModel):
    stat_date: date
    live_paid_amount: Decimal = Decimal("0")
    member_paid_amount: Decimal = Decimal("0")
    customer_service_sales: Decimal = Decimal("0")
    brand_paid_amount: Decimal = Decimal("0")
    cps_paid_amount: Decimal = Decimal("0")
    content_paid_amount: Decimal = Decimal("0")


class CustomerAnalysis(BaseModel):
    expected_days: int = 0
    covered_days: int = 0
    first_covered_date: date | None = None
    latest_covered_date: date | None = None
    missing_dates: list[date] = Field(default_factory=list)
    shop_customers: int | None = None
    shop_customers_stat_date: date | None = None
    new_customers: int = 0
    new_customer_paid_buyers: int = 0
    new_customer_paid_amount: Decimal = Decimal("0")
    new_customer_conversion_rate: Decimal = Decimal("0")
    repeat_customers: int = 0
    repeat_customer_paid_amount: Decimal = Decimal("0")
    repeat_rate: Decimal = Decimal("0")
    no_purchase_returners: int = 0
    no_purchase_buyers: int = 0
    no_purchase_conversion_rate: Decimal = Decimal("0")
    derived_metrics: list[DecisionMetric] = Field(default_factory=list)
    quality_warnings: list[str] = Field(default_factory=list)
    segments: list["CustomerSegmentMetric"] = Field(default_factory=list)
    daily_metrics: list["CustomerDailyMetric"] = Field(default_factory=list)


class CustomerSegmentMetric(BaseModel):
    key: str
    label: str
    reached: int = 0
    buyers: int = 0
    conversion_rate: Decimal = Decimal("0")
    paid_amount: Decimal = Decimal("0")
    unit_price: Decimal = Decimal("0")
    member_rate: Decimal = Decimal("0")
    fan_rate: Decimal = Decimal("0")


class CustomerDailyMetric(BaseModel):
    stat_date: date
    total_paid_buyers: int = 0
    total_paid_amount: Decimal = Decimal("0")
    first_purchase_paid_buyers: int | None = None
    first_purchase_paid_amount: Decimal | None = None
    new_visitors: int = 0
    new_paid_buyers: int = 0
    new_paid_amount: Decimal | None = None
    no_purchase_returners: int = 0
    no_purchase_buyers: int = 0
    repeat_returners: int = 0
    repeat_buyers: int = 0
    repeat_paid_amount: Decimal | None = None


class MemberAnalysis(BaseModel):
    total_members: int = 0
    paid_members: int = 0
    paid_amount: Decimal = Decimal("0")
    unit_price: Decimal = Decimal("0")
    repurchase_rate: Decimal = Decimal("0")
    repurchase_members: int = 0
    repurchase_amount: Decimal = Decimal("0")
    new_members: int = 0
    new_paid_members: int = 0
    recruit_conversion_rate: Decimal = Decimal("0")
    high_frequency_members: int = 0
    two_order_members: int = 0
    first_time_members: int = 0
    active_non_buyers: int = 0
    inactive_members: int = 0
    repurchase_cycle: Decimal = Decimal("0")
    daily_metrics: list["MemberDailyMetric"] = Field(default_factory=list)
    channels: list["MemberChannelMetric"] = Field(default_factory=list)


class MemberDailyMetric(BaseModel):
    stat_date: date
    paid_members: int = 0
    paid_amount: Decimal = Decimal("0")
    repurchase_members: int = 0
    repurchase_amount: Decimal = Decimal("0")
    new_members: int = 0
    new_paid_members: int = 0


class MemberChannelMetric(BaseModel):
    channel_name: str
    new_members: int = 0
    paid_new_members: int = 0
    recruit_conversion_rate: Decimal = Decimal("0")
    paid_amount: Decimal = Decimal("0")


class CustomerServiceAnalysis(BaseModel):
    sales_amount: Decimal = Decimal("0")
    sale_users: int = 0
    consult_users: int = 0
    reception_users: int = 0
    reception_rate: Decimal = Decimal("0")
    sales_conversion_rate: Decimal = Decimal("0")
    sales_ratio: Decimal = Decimal("0")
    avg_reply_seconds: Decimal = Decimal("0")
    satisfaction_rate: Decimal = Decimal("0")
    refund_amount: Decimal = Decimal("0")
    net_sales_amount: Decimal = Decimal("0")


class CustomerServiceDailyMetric(BaseModel):
    stat_date: date
    sales_amount: Decimal = Decimal("0")
    net_sales_amount: Decimal = Decimal("0")
    sale_users: int = 0
    consult_users: int = 0
    reception_users: int = 0
    sales_ratio: Decimal = Decimal("0")
    avg_reply_seconds: Decimal = Decimal("0")
    satisfaction_rate: Decimal = Decimal("0")


class CustomerServiceAccountMetric(BaseModel):
    account_name: str
    sales_amount: Decimal = Decimal("0")
    net_sales_amount: Decimal = Decimal("0")
    sale_users: int = 0
    consult_users: int = 0
    reception_users: int = 0
    reception_rate: Decimal = Decimal("0")
    sales_conversion_rate: Decimal = Decimal("0")


class LiveAnalysis(BaseModel):
    paid_amount: Decimal = Decimal("0")
    shop_paid_amount: Decimal = Decimal("0")
    live_during_paid_amount: Decimal = Decimal("0")
    post_paid_amount: Decimal = Decimal("0")
    talent_paid_amount: Decimal = Decimal("0")
    talent_count: int = 0
    talent_sessions: int = 0
    viewers: int = 0
    buyers: int = 0
    item_click_users: int = 0
    deal_rate: Decimal = Decimal("0")
    unit_price: Decimal = Decimal("0")
    daily_metrics: list["LiveDailyMetric"] = Field(default_factory=list)
    talents: list["LiveTalentMetric"] = Field(default_factory=list)


class LiveDailyMetric(BaseModel):
    stat_date: date
    paid_amount: Decimal = Decimal("0")
    shop_paid_amount: Decimal = Decimal("0")
    live_during_paid_amount: Decimal = Decimal("0")
    post_paid_amount: Decimal = Decimal("0")
    viewers: int = 0
    item_click_users: int = 0
    buyers: int = 0
    paid_amount_per_buyer: Decimal = Decimal("0")
    view_click_rate: Decimal = Decimal("0")
    click_deal_rate: Decimal = Decimal("0")


class LiveTalentMetric(BaseModel):
    talent_id: str
    talent_name: str
    sessions: int = 0
    item_click_users: int = 0
    add_cart_users: int = 0
    buyers: int = 0
    paid_amount: Decimal = Decimal("0")
    paid_items: int = 0
    paid_orders: int = 0
    single_output: Decimal = Decimal("0")
    click_deal_rate: Decimal = Decimal("0")


class PromotionAnalysis(BaseModel):
    campaign_count: int = 0
    spend: Decimal = Decimal("0")
    paid_amount: Decimal = Decimal("0")
    buyers: int = 0
    roi: Decimal = Decimal("0")


class BrandZoneAnalysis(BaseModel):
    impressions: int = 0
    clicks: int = 0
    click_rate: Decimal = Decimal("0")
    click_visitors: int = 0
    paid_amount: Decimal = Decimal("0")
    paid_order_count: int = 0
    conversion_rate: Decimal = Decimal("0")


class CpsAnalysis(BaseModel):
    paid_amount: Decimal = Decimal("0")
    paid_order_count: int = 0
    click_visitors: int = 0
    payment_expense: Decimal = Decimal("0")
    payment_commission_expense: Decimal = Decimal("0")
    payment_service_expense: Decimal = Decimal("0")
    settlement_expense: Decimal = Decimal("0")
    settlement_commission_expense: Decimal = Decimal("0")
    settlement_service_expense: Decimal = Decimal("0")
    settlement_amount: Decimal = Decimal("0")
    settlement_order_count: int = 0
    payment_cost_rate: Decimal = Decimal("0")
    settlement_rate: Decimal = Decimal("0")
    preorder_deposit_amount: Decimal = Decimal("0")
    preorder_total_amount: Decimal = Decimal("0")
    daily_metrics: list["CpsDailyMetric"] = Field(default_factory=list)


class CpsDailyMetric(BaseModel):
    stat_date: date
    click_visitors: int = 0
    paid_amount: Decimal = Decimal("0")
    paid_order_count: int = 0
    payment_expense: Decimal = Decimal("0")
    settlement_amount: Decimal = Decimal("0")
    settlement_order_count: int = 0
    settlement_expense: Decimal = Decimal("0")
    preorder_deposit_amount: Decimal = Decimal("0")
    preorder_total_amount: Decimal = Decimal("0")


class ContentAnalysis(BaseModel):
    view_count: int = 0
    viewers: int = 0
    product_click_users: int = 0
    paid_amount: Decimal = Decimal("0")
    paid_buyers: int = 0
    interaction_count: int = 0
    exposure_users: int = 0
    interaction_users: int = 0
    add_cart_users: int = 0
    interaction_rate: Decimal = Decimal("0")
    product_click_rate: Decimal = Decimal("0")
    paid_amount_ratio: Decimal = Decimal("0")
    daily_metrics: list["ContentDailyMetric"] = Field(default_factory=list)


class ContentDailyMetric(BaseModel):
    stat_date: date
    viewers: int = 0
    interaction_count: int = 0
    product_click_users: int = 0
    add_cart_users: int = 0
    paid_buyers: int = 0
    paid_amount: Decimal = Decimal("0")


class NewCustomerDiscountDailyMetric(BaseModel):
    stat_date: date
    product_new_visitors: int | None = None
    paid_buyers: int | None = None
    paid_amount: Decimal | None = None
    conversion_rate: Decimal | None = None
    shop_paid_buyers: int | None = None
    shop_paid_amount: Decimal | None = None
    record_status: Literal["complete", "partial", "missing"] = "missing"


class NewCustomerDiscountAnalysis(BaseModel):
    product_new_visitors: int = 0
    paid_buyers: int = 0
    paid_amount: Decimal = Decimal("0")
    conversion_rate: Decimal = Decimal("0")
    shop_paid_buyers: int = 0
    shop_paid_amount: Decimal = Decimal("0")
    buyer_share: Decimal = Decimal("0")
    amount_share: Decimal = Decimal("0")
    daily_metrics: list[NewCustomerDiscountDailyMetric] = Field(default_factory=list)


class ShoppingGoldDailyMetric(BaseModel):
    stat_date: date
    recharge_amount: Decimal = Decimal("0")
    paid_amount: Decimal = Decimal("0")
    recharge_buyers: int = 0
    paid_buyers: int = 0
    product_visitors: int = 0
    recharge_refund_amount: Decimal = Decimal("0")


class ShoppingGoldAnalysis(BaseModel):
    recharge_amount: Decimal = Decimal("0")
    paid_amount: Decimal = Decimal("0")
    recharge_buyers: int = 0
    paid_buyers: int = 0
    product_visitors: int = 0
    recharge_items: int = 0
    recharge_sub_order_count: int = 0
    recharge_refund_amount: Decimal = Decimal("0")
    recharge_capital_amount: Decimal = Decimal("0")
    average_recharge_amount: Decimal = Decimal("0")
    customer_unit_price: Decimal = Decimal("0")
    recharge_rate: Decimal = Decimal("0")
    paid_amount_ratio: Decimal = Decimal("0")
    daily_metrics: list[ShoppingGoldDailyMetric] = Field(default_factory=list)


class BybtDailyMetric(BaseModel):
    stat_date: date
    record_status: str = "complete"
    visitors: int | None = None
    paid_buyers: int | None = None
    paid_amount: Decimal | None = None
    online_items: int | None = None
    paid_sub_order_count: int | None = None
    paid_items: int | None = None


class BybtAnalysis(BaseModel):
    visitors: int = 0
    paid_buyers: int = 0
    paid_amount: Decimal = Decimal("0")
    online_items: int = 0
    paid_sub_order_count: int = 0
    paid_items: int = 0
    conversion_rate: Decimal = Decimal("0")
    customer_unit_price: Decimal = Decimal("0")
    items_per_buyer: Decimal = Decimal("0")
    expected_days: int = 0
    covered_days: int = 0
    missing_dates: list[date] = Field(default_factory=list)
    daily_metrics: list[BybtDailyMetric] = Field(default_factory=list)


class AnalysisSnapshot(BaseModel):
    daily_metrics: list[AnalysisDailyMetric] = Field(default_factory=list)
    customer: CustomerAnalysis = Field(default_factory=CustomerAnalysis)
    member: MemberAnalysis = Field(default_factory=MemberAnalysis)
    customer_service: CustomerServiceAnalysis = Field(default_factory=CustomerServiceAnalysis)
    customer_service_daily: list[CustomerServiceDailyMetric] = Field(default_factory=list)
    customer_service_accounts: list[CustomerServiceAccountMetric] = Field(default_factory=list)
    live: LiveAnalysis = Field(default_factory=LiveAnalysis)
    promotion: PromotionAnalysis = Field(default_factory=PromotionAnalysis)
    brand_zone: BrandZoneAnalysis = Field(default_factory=BrandZoneAnalysis)
    cps: CpsAnalysis = Field(default_factory=CpsAnalysis)
    content: ContentAnalysis = Field(default_factory=ContentAnalysis)
    new_customer_discount: NewCustomerDiscountAnalysis = Field(default_factory=NewCustomerDiscountAnalysis)
    shopping_gold: ShoppingGoldAnalysis = Field(default_factory=ShoppingGoldAnalysis)
    bybt: BybtAnalysis = Field(default_factory=BybtAnalysis)


class DashboardResponse(BaseModel):
    range_start: date
    range_end: date
    product_range_start: date
    product_range_end: date
    summary: SummaryMetric
    daily_metrics: list[DailyMetric]
    promotion_daily_metrics: list[PromotionDailyMetric] = Field(default_factory=list)
    top_products: list[ProductMetric]
    traffic_sources: list[TrafficMetric]
    promotion_plans: list[PromotionMetric]
    promotion_scenes: list[PromotionSceneMetric] = Field(default_factory=list)
    freshness: list[DataFreshness]
    period: DashboardPeriod
    comparison: SummaryComparison
    coverage: list[DataCoverage] = Field(default_factory=list)
    insights: list[BusinessInsight] = Field(default_factory=list)
    analysis: AnalysisSnapshot | None = None
