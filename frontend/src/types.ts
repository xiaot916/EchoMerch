export interface DailyMetric {
  stat_date: string
  paid_amount: number
  visitors: number
  conversion_rate: number
  promotion_cost: number
  buyers: number
  refund_amount: number
  refund_rate: number
  promotion_plan_spend: number
  promotion_attributed_paid_amount: number
}

export interface ProductMetric {
  product_id: string
  product_name: string
  paid_amount: number
  buyers: number
  visitors: number
  add_cart_users: number
  favorite_users: number
  page_views: number
  search_visitors: number
  promotion_spend: number
  product_type: string
  series: string
  positioning: string
}

export interface InventoryManagementRow {
  id: number
  series: string
  specification: string
  size: string
  goods_no: string
  pieces: number | null
  display_name: string | null
  available_quantity: number | null
  warehouse_count: number
  min_warehouse_quantity: number | null
  stock_status: "有库存" | "低库存" | "零库存" | "未匹配库存"
  catalog_match_count: number
  business_day: string | null
  snapshot_at: string | null
}

export interface InventoryManagementResponse {
  summary: Record<string, number>
  latest_business_day: string | null
  latest_snapshot_at: string | null
  freshness_status: string
  snapshot_age_minutes: number | null
  dimensions: { series: string[]; specification: string[]; size: string[] }
  total: number
  page: number
  page_size: number
  rows: InventoryManagementRow[]
}

export interface InventoryCompanyRow {
  key: string
  goods_no: string
  sku_no: string
  goods_id: string
  sku_id: string
  goods_name: string | null
  sku_name: string | null
  sku_barcode: string
  series: string
  specification: string
  size: string
  pieces: number | null
  available_quantity: number
  warehouse_count: number
  stock_status: "有库存" | "低库存" | "零库存"
  catalog_match_count: number
  business_day: string | null
  snapshot_at: string | null
}

export interface InventoryWarehouseSummary {
  warehouse_id: string
  warehouse_name: string | null
  sku_count: number
  available_quantity: number
  in_stock_count: number
  low_stock_count: number
  zero_stock_count: number
}

export interface InventoryPackageRow {
  key: string
  goods_no: string
  sku_no: string
  goods_name: string | null
  sku_name: string | null
  component_count: number
  stock_status: "已同步明细" | "待同步明细"
  component_summary: string[]
  business_day: string | null
}

export interface InventoryAnalysisResponse {
  latest_business_day: string | null
  latest_snapshot_at: string | null
  freshness_status: string
  snapshot_age_minutes: number | null
  master_sync: Record<string, any>
  company_summary: Record<string, number>
  warehouse_summary: InventoryWarehouseSummary[]
  company_rows: InventoryCompanyRow[]
  stockout_rows: InventoryCompanyRow[]
  package_summary: Record<string, number | string>
  package_rows: InventoryPackageRow[]
  warnings: string[]
}

export interface InventorySyncResponse {
  configured: boolean
  refresh_minutes: number
  results: Array<{
    status: string
    store_id: number | null
    row_count?: number
    package_count?: number
    goods_master_count?: number
    component_count?: number
    master_status?: string
    goods_status?: string
    package_status?: string
    business_day?: string | null
    fetched_at?: string | null
    error_message?: string | null
  }>
}

export interface InventorySyncStatusResponse {
  configured: boolean
  credential_status?: string
  credential_detail?: string | null
  store_id: number | null
  status: string
  latest_business_day: string | null
  latest_snapshot_at: string | null
  last_attempt_at: string | null
  row_count: number
  error_message: string | null
  refresh_minutes: number
  freshness_status: string
  snapshot_age_minutes: number | null
  master_business_day: string | null
  master_status: string
  goods_status: string
  package_status: string
  goods_master_count: number
  package_count: number
  component_count: number
  master_last_attempt_at: string | null
  master_finished_at: string | null
  master_error_message: string | null
}

export interface ProductAnalysisDailyMetric {
  stat_date: string
  paid_amount: number
  buyers: number
  visitors: number
  add_cart_users: number
  favorite_users: number
  promotion_spend: number
  conversion_rate: number
}

export interface FlashSaleDailyMetric {
  stat_date: string
  item_count: number | null
  ipv: number | null
  ipv_uv: number | null
  paid_order_count: number | null
  paid_amount: number | null
  new_customers: number | null
  burst_coefficient: number | null
  record_status: "complete" | "empty" | "missing"
}

export interface FlashSaleSummary {
  active_days: number
  item_count_peak: number | null
  ipv: number
  ipv_uv: number
  paid_order_count: number
  paid_amount: number
  new_customers: number
  burst_coefficient_peak: number | null
  conversion_rate: number
  customer_unit_price: number
  shop_paid_amount: number | null
  shop_paid_share: number | null
}

export interface FlashSaleAnalysisResponse {
  range_start: string
  range_end: string
  latest_available_date: string | null
  summary: FlashSaleSummary
  previous_summary: FlashSaleSummary
  comparison: {
    paid_amount_change_percent: number | null
    paid_order_count_change_percent: number | null
    ipv_uv_change_percent: number | null
    new_customers_change_percent: number | null
  }
  daily_metrics: FlashSaleDailyMetric[]
  coverage: string[]
  empty_dates: string[]
  missing_dates: string[]
}

export interface UtryDailyMetric {
  stat_date: string
  sample_status: "complete" | "no_data" | "missing"
  repurchase_status: "complete" | "no_data" | "missing"
  sample_people: number | null
  sample_orders: number | null
  sample_gmv: number | null
  merchant_new_customers_180d: number | null
  merchant_new_customers_365d: number | null
  new_members: number | null
  new_followers: number | null
  store_30d_repurchase_amount: number | null
  store_90d_repurchase_amount: number | null
  store_365d_repurchase_amount: number | null
}

export interface UtryProductMetric {
  product_id: string
  product_name: string
  sample_people: number | null
  sample_orders: number | null
  sample_gmv: number | null
  merchant_new_customers_180d: number | null
  merchant_new_customers_365d: number | null
  new_members: number | null
  new_followers: number | null
  store_30d_repurchase_uv: number | null
  store_30d_repurchase_amount: number | null
  store_90d_repurchase_uv: number | null
  store_90d_repurchase_amount: number | null
  store_365d_repurchase_uv: number | null
  store_365d_repurchase_amount: number | null
  brand_365d_repurchase_amount: number | null
  leaf_category: string
  bind_regular_product: string
  configured_repurchase_coupon: string
  configured_repurchase_gift: string
  diagnostic_tag: string
}

export interface UtryAnalysisResponse {
  range_start: string
  range_end: string
  latest_sample_date: string | null
  latest_repurchase_date: string | null
  sample_summary: {
    sample_orders: number
    sample_people: number
    sample_gmv: number
    merchant_new_customers_180d: number
    merchant_new_customers_365d: number
    new_members: number
    new_followers: number
    average_orders_per_person: number
    sample_gmv_per_person: number
    merchant_new_customer_rate_180d: number | null
    merchant_new_customer_rate_365d: number | null
  }
  latest_repurchase: {
    business_day: string | null
    product_count: number
    bound_regular_product_count: number
    configured_coupon_count: number
    configured_gift_count: number
    bound_regular_product_share: number | null
    configured_coupon_share: number | null
    configured_gift_share: number | null
    store_30d_repurchase_uv: number
    store_30d_repurchase_amount: number
    store_90d_repurchase_uv: number
    store_90d_repurchase_amount: number
    store_365d_repurchase_uv: number
    store_365d_repurchase_amount: number
    brand_365d_repurchase_uv: number
    brand_365d_repurchase_amount: number
  }
  previous_repurchase: UtryAnalysisResponse["latest_repurchase"]
  daily_metrics: UtryDailyMetric[]
  products: UtryProductMetric[]
  sample_coverage: DataCoverage | null
  repurchase_coverage: DataCoverage | null
  warnings: string[]
}

export interface PromotionProductMetric {
  product_id: string
  product_name: string
  activity_id: string
  activity_name: string
  category_name: string
  activity_status: string
  visitors: number | null
  paid_order_count: number | null
  paid_items: number | null
  paid_amount: number | null
  new_customers: number | null
  conversion_rate: number | null
  active_days: number
}

export interface PromotionProductListResponse {
  range_start: string
  range_end: string
  available_start: string | null
  available_end: string | null
  missing_dates: string[]
  total: number
  page: number
  page_size: number
  items: PromotionProductMetric[]
}

export interface ProductAnalysisResponse {
  range_start: string
  range_end: string
  products: ProductMetric[]
  product: ProductMetric | null
  daily_metrics: ProductAnalysisDailyMetric[]
  peers: ProductMetric[]
}

export interface MarketCoverage {
  dataset: string
  range_start: string
  range_end: string
  expected_days: number
  covered_days: number
  missing_dates: string[]
  first_date: string | null
  latest_date: string | null
  latest_fetched_at: string | null
  status: "complete" | "partial" | "empty" | string
}

export interface MarketRanking {
  rank_no: number
  rank_change: number | null
  rank_type: string
  entity_type: string
  entity_id: string | null
  entity_name: string
  shop_name: string | null
  keyword: string | null
  paid_buyers_range: string | null
  visitors_range: string | null
  sale_item_count: number | null
  content_title: string | null
  content_start_time: string | null
  fan_count_range: string | null
  grass_paid_amount_range: string | null
  goods_clicks_range: string | null
  live_views_range: string | null
  is_monitored: boolean
}

export interface MarketKeyword {
  rank_no: number
  keyword_type: string
  keyword: string
  popularity_range: string | null
  click_rate: number | null
  pay_conversion_rate: string | null
  pay_conversion_midpoint: number | null
  opportunity_score: number | null
}

export interface MarketDailyMetric {
  stat_date: string
  ranking_rows: number
  shops: number
  items: number
  keywords: number
  average_click_rate: number | null
  average_pay_conversion_rate: number | null
  high_opportunity_keywords: number
  ranking_risers: number
  ranking_fallers: number
}

export interface MarketOpportunity {
  keyword: string
  keyword_type: string
  evidence: string
  action: string
  score: number | null
}

export interface MarketDemandSignal {
  keyword: string
  keyword_type: string
  current_rank: number
  previous_rank: number | null
  rank_change: number | null
  direction: "rising" | "falling" | "stable" | "new" | string
  days_seen: number
  popularity_range: string | null
  click_rate: number | null
  pay_conversion_midpoint: number | null
  opportunity_score: number | null
  evidence: string
  action: string
  confidence: "high" | "medium" | "low" | string
}

export interface MarketDecision {
  priority: string
  theme: string
  title: string
  finding: string
  evidence: string
  action: string
  validation: string
  confidence: "high" | "medium" | "low" | string
}

export interface MarketCompetitiveSignal {
  rank_type: string
  entity_id: string | null
  name: string
  current_rank: number
  rank_change: number | null
  direction: "rising" | "falling" | "stable" | string
  evidence: string
  action: string
}

export interface MarketKeywordSegment {
  keyword_type: string
  keyword_count: number
  top_keyword: string | null
  average_click_rate: number | null
  average_pay_conversion_rate: number | null
  average_opportunity_score: number | null
  high_opportunity_count: number
}

export interface MarketInsightResponse {
  range_start: string
  range_end: string
  latest_available_date: string | null
  scope_label: string
  summary: {
    ranking_rows: number
    keyword_rows: number
    shop_count: number
    item_count: number
    content_count: number
    keyword_count: number
    latest_rank_date: string | null
    latest_keyword_date: string | null
    top_shop: string | null
    top_item: string | null
    top_content: string | null
    top_keyword: string | null
    monitored_count: number
    relevant_keyword_count: number
    high_opportunity_count: number
    rank_mover_count: number
    coverage_rate: number
    rising_counts: Record<string, number>
    falling_counts: Record<string, number>
  }
  coverage: MarketCoverage[]
  daily_metrics: MarketDailyMetric[]
  rankings: MarketRanking[]
  keywords: MarketKeyword[]
  opportunities: MarketOpportunity[]
  demand_signals: MarketDemandSignal[]
  decisions: MarketDecision[]
  competitive_signals: MarketCompetitiveSignal[]
  keyword_segments: MarketKeywordSegment[]
  diagnostics: string[]
  data_quality_flags: string[]
}

export interface TrafficMetric {
  source_name: string
  visitors: number
  paid_amount: number
  buyers: number
  new_visitors: number
  add_cart_users: number
  favorite_users: number
  conversion_rate: number
  uv_value: number
}

export interface TrafficTreeNode {
  id: string
  parent_id: string | null
  level: 1 | 2 | 3
  name: string
  path: string[]
  visitors: number
  paid_amount: number
  buyers: number
  new_visitors: number
  add_cart_users: number
  favorite_users: number
  conversion_rate: number
  uv_value: number
  derived_from_children: boolean
  children: TrafficTreeNode[]
}

export interface PromotionMetric {
  plan_name: string
  scene_name: string | null
  spend: number
  paid_amount: number | null
  buyers: number | null
}

export interface PromotionSceneMetric {
  scene_name: string
  campaign_count: number
  spend: number
  paid_amount: number
  buyers: number
}

export interface PromotionSummaryMetric {
  campaign_count: number
  impressions: number
  clicks: number
  spend: number
  paid_amount: number
  direct_paid_amount: number
  indirect_paid_amount: number
  orders: number
  buyers: number
  carts: number
  favorites: number
  new_buyers: number
  member_paid_amount: number
  natural_paid_amount: number
  roi: number
  click_rate: number
  average_click_cost: number
  click_conversion_rate: number
  buyer_acquisition_cost: number
  new_buyer_share: number
}

export interface PromotionDailyMetric {
  stat_date: string
  impressions: number
  clicks: number
  spend: number
  paid_amount: number
  orders: number
  buyers: number
  carts: number
  new_buyers: number
}

export interface PromotionDimensionMetric {
  dimension_id: string
  dimension_name: string
  scene_name: string
  parent_id: string
  parent_name: string
  subject_id: string
  subject_name: string
  impressions: number
  clicks: number
  spend: number
  paid_amount: number
  direct_paid_amount: number
  indirect_paid_amount: number
  orders: number
  buyers: number
  carts: number
  favorites: number
  new_buyers: number
  member_paid_amount: number
  natural_paid_amount: number
}

export interface PromotionLayerCoverage {
  key: string
  label: string
  covered_days: number
  row_count: number
  entity_count: number
}

export interface PromotionWorkbenchResponse {
  range_start: string
  range_end: string
  summary: PromotionSummaryMetric
  daily_metrics: PromotionDailyMetric[]
  scenes: PromotionDimensionMetric[]
  campaigns: PromotionDimensionMetric[]
  adgroups: PromotionDimensionMetric[]
  audiences: PromotionDimensionMetric[]
  keywords: PromotionDimensionMetric[]
  items: PromotionDimensionMetric[]
  contents: PromotionDimensionMetric[]
  coverage: PromotionLayerCoverage[]
}

export interface DataFreshness {
  dataset: string
  latest_date: string
  first_date?: string | null
}

export interface DataCoverage {
  dataset: string
  first_date: string | null
  latest_date: string | null
  expected_days: number
  covered_days: number
  missing_dates: string[]
  no_data_dates?: string[]
  status: "complete" | "partial" | "empty"
}

export interface AIAnalysisResponse {
  request_id: string
  conversation_id?: string | null
  status: "ok" | "partial" | "no_data" | "error"
  skill: { name: string; display_name: string; description: string; version: string; domains: string[]; tools: string[]; enabled: boolean }
  supporting_skills: Array<{ name: string; display_name: string; description: string; version: string; domains: string[]; tools: string[]; enabled: boolean }>
  provider: string
  model: string | null
  elapsed_ms?: number | null
  answer: string
  diagnosis: {
    headline: string
    summary: string
    findings: Array<{ level: string; title: string; detail: string; metric_ids: string[] }>
    actions: Array<{ priority: string; title: string; detail: string; owner: string; validation: string; observation_window: string; expected_impact: string }>
    artifacts: Array<{ type: string; title: string; columns: Array<Record<string, string>>; rows: Array<Record<string, unknown>>; option: Record<string, unknown> }>
    analysis_scope: Record<string, unknown>
    coverage: {
      expected_days: number
      covered_days: number
      missing_dates: string[]
      missing_datasets: string[]
      partial_datasets: string[]
      failed_datasets: string[]
      no_data_datasets: string[]
      no_data_dates: string[]
      latest_data_date: string | null
    }
    confidence: "high" | "medium" | "low"
    assumptions: string[]
    missing_inputs: string[]
    evidence_refs: string[]
    metric_definitions: Record<string, string>
    denominator_notes: string[]
    causal_boundary: string
    next_questions: string[]
  }
  mcp_results: Array<Record<string, any>>
  conversation_memory: Record<string, unknown>
  execution_steps: Array<{ kind: string; name: string; status: string; detail: string; elapsed_ms?: number | null }>
  warnings: string[]
}

export interface AIConfiguration {
  base_url: string
  api_path: string
  endpoint: string
  model: string
  timeout_seconds: number
  api_key_configured: boolean
  api_key_masked: string | null
}

export interface AIConnectionTest {
  ok: boolean
  model: string
  status_code: number | null
  elapsed_ms: number | null
  reply: string
  error: string | null
}

export interface PeriodReportResponse {
  request_id: string
  conversation_id?: string | null
  status: "ok" | "partial" | "no_data" | "error"
  report_type: string
  range_start: string
  range_end: string
  title: string
  text: string
  diagnosis: {
    headline: string
    summary: string
    findings: Array<{ level: string; title: string; detail: string; metric_ids: string[] }>
    actions: Array<{ priority: string; title: string; detail: string; owner: string; validation: string; observation_window: string; expected_impact: string }>
    artifacts: Array<{ type: string; title: string; columns: Array<Record<string, string>>; rows: Array<Record<string, any>>; option: Record<string, any> }>
    confidence: "high" | "medium" | "low"
    coverage: { expected_days: number; covered_days: number; missing_dates: string[]; missing_datasets: string[]; partial_datasets: string[]; no_data_datasets: string[]; latest_data_date: string | null }
    next_questions: string[]
  }
  report: {
    operations: Record<string, any>
    comparison?: Record<string, { current: number | null; previous: number | null; delta: number | null; change_percent: number | null }>
    gmv_driver_bridge?: {
      formula: string
      method: string
      previous_gmv: number
      current_gmv: number
      delta_amount: number
      drivers: Array<{ key: string; label: string; metric: string; current: number | null; previous: number | null; change_percent: number | null; impact_amount: number }>
      dominant_driver?: { key: string; label: string; metric: string; current: number | null; previous: number | null; change_percent: number | null; impact_amount: number }
      reconciliation_error: number
      note: string
    } | null
    previous_period?: { range_start: string; range_end: string }
    target?: { target_gmv: number; completion_rate: number | null; gap: number; remaining_gmv?: number; remaining_days?: number; required_daily_gmv?: number | null; time_progress?: number | null; pace_gap?: number | null; source: string }
    channels: Record<string, any>
    channel_scope?: { scope_type: string; denominator: string; can_sum: boolean; note: string; rules: string[] }
    promotions: Record<string, any>
    customer?: Record<string, any>
    top_talents: Array<Record<string, any>>
    missing_sections: string[]
    no_data_sections: string[]
    coverage_by_dataset?: Array<Record<string, any>>
    data_quality?: { status: string; missing_sections: string[]; no_data_sections: string[]; missing_dates: string[]; missing_datasets?: string[]; partial_datasets?: string[]; failed_datasets?: string[]; no_data_datasets?: string[]; no_data_dates?: string[]; latest_data_date: string | null }
    decision_quality?: {
      overall: { confidence: "high" | "medium" | "low"; status: string; reason: string }
      modules: Array<{ key: string; label: string; confidence: "high" | "medium" | "low"; status: string; reason: string }>
    }
    daily_series?: Array<{ stat_date: string; paid_amount: number; visitors: number; buyers: number; conversion_rate: number; refund_amount?: number; refund_rate?: number; promotion_plan_spend?: number; promotion_attributed_paid_amount?: number }>
  }
  mcp_result: Record<string, any>
  skill: { name: string; display_name: string; version: string }
  provider: string
  model: string | null
  elapsed_ms?: number | null
  execution_steps?: Array<{ kind: string; name: string; status: string; detail: string; elapsed_ms?: number | null }>
  warnings: string[]
}

export interface AIConversationMessage {
  role: "user" | "assistant"
  text: string
  created_at: string
  payload?: { kind: "analysis" | "report"; data: AIAnalysisResponse | PeriodReportResponse } | null
}

export interface AIConversationListItem {
  conversation_id: string
  title: string
  updated_at: string
  message_count: number
}

export interface AIConversationDetail {
  conversation_id: string
  title: string
  summary: string
  memory: Record<string, unknown>
  recent_messages: AIConversationMessage[]
  updated_at?: string | null
}

export interface StoreActivityCalendarEvent {
  store_id: number
  business_day: string
  activity_id: string
  activity_name: string
  activity_type: string
  activity_status: string
  activity_start_time: string
  activity_end_time: string
  signup_start_time: string
  signup_end_time: string
  activity_tag: string
  activity_level: string
  activity_stage: string
}

export interface DashboardPeriod {
  requested_start: string
  requested_end: string
  previous_start: string
  previous_end: string
  expected_days: number
  covered_days: number
  missing_dates: string[]
}

export interface ComparisonMetric {
  current: number
  previous: number
  delta: number
  change_percent: number | null
}

export interface SummaryComparison {
  paid_amount: ComparisonMetric
  visitors: ComparisonMetric
  buyers: ComparisonMetric
  conversion_rate: ComparisonMetric
  promotion_cost: ComparisonMetric
}

export interface BusinessInsight {
  level: "warning" | "positive" | "info"
  title: string
  detail: string
  action: string | null
}

export interface AnalysisDailyMetric {
  stat_date: string
  live_paid_amount: number
  member_paid_amount: number
  customer_service_sales: number
  brand_paid_amount: number
  cps_paid_amount: number
  content_paid_amount: number
}

export interface CustomerAnalysis {
  shop_customers: number | null
  shop_customers_stat_date: string | null
  new_customers: number
  new_customer_paid_buyers: number
  new_customer_paid_amount: number
  new_customer_conversion_rate: number
  repeat_customers: number
  repeat_customer_paid_amount: number
  repeat_rate: number
  no_purchase_returners: number
  no_purchase_buyers: number
  no_purchase_conversion_rate: number
  segments: CustomerSegmentMetric[]
  daily_metrics: CustomerDailyMetric[]
}

export interface CustomerSegmentMetric {
  key: string
  label: string
  reached: number
  buyers: number
  conversion_rate: number
  paid_amount: number
  unit_price: number
  member_rate: number
  fan_rate: number
}

export interface CustomerDailyMetric {
  stat_date: string
  new_visitors: number
  new_paid_buyers: number
  new_paid_amount: number
  no_purchase_returners: number
  no_purchase_buyers: number
  repeat_returners: number
  repeat_buyers: number
  repeat_paid_amount: number
}

export interface MemberAnalysis {
  total_members: number
  paid_members: number
  paid_amount: number
  unit_price: number
  repurchase_rate: number
  repurchase_members: number
  repurchase_amount: number
  new_members: number
  new_paid_members: number
  recruit_conversion_rate: number
  high_frequency_members: number
  two_order_members: number
  first_time_members: number
  active_non_buyers: number
  inactive_members: number
  repurchase_cycle: number
  daily_metrics: MemberDailyMetric[]
  channels: MemberChannelMetric[]
}

export interface MemberDailyMetric {
  stat_date: string
  paid_members: number
  paid_amount: number
  repurchase_members: number
  repurchase_amount: number
  new_members: number
  new_paid_members: number
}

export interface MemberChannelMetric {
  channel_name: string
  new_members: number
  paid_new_members: number
  recruit_conversion_rate: number
  paid_amount: number
}

export interface CustomerServiceAnalysis {
  sales_amount: number
  sale_users: number
  consult_users: number
  reception_users: number
  reception_rate: number
  sales_conversion_rate: number
  sales_ratio: number
  avg_reply_seconds: number
  satisfaction_rate: number
  refund_amount: number
  net_sales_amount: number
}

export interface CustomerServiceDailyMetric {
  stat_date: string
  sales_amount: number
  net_sales_amount: number
  sale_users: number
  consult_users: number
  reception_users: number
  sales_ratio: number
  avg_reply_seconds: number
  satisfaction_rate: number
}

export interface CustomerServiceAccountMetric {
  account_name: string
  sales_amount: number
  net_sales_amount: number
  sale_users: number
  consult_users: number
  reception_users: number
  reception_rate: number
  sales_conversion_rate: number
}

export interface LiveAnalysis {
  paid_amount: number
  shop_paid_amount: number
  live_during_paid_amount: number
  post_paid_amount: number
  talent_paid_amount: number
  talent_count: number
  talent_sessions: number
  viewers: number
  buyers: number
  item_click_users: number
  deal_rate: number
  unit_price: number
  daily_metrics: LiveDailyMetric[]
  talents: LiveTalentMetric[]
}

export interface LiveDailyMetric {
  stat_date: string
  paid_amount: number
  shop_paid_amount: number
  live_during_paid_amount: number
  post_paid_amount: number
  viewers: number
  item_click_users: number
  buyers: number
  paid_amount_per_buyer: number
  view_click_rate: number
  click_deal_rate: number
}

export interface LiveTalentMetric {
  talent_id: string
  talent_name: string
  sessions: number
  item_click_users: number
  add_cart_users: number
  buyers: number
  paid_amount: number
  paid_items: number
  paid_orders: number
  single_output: number
  click_deal_rate: number
}

export interface PromotionAnalysis {
  campaign_count: number
  spend: number
  paid_amount: number
  buyers: number
  roi: number
}

export interface BrandZoneAnalysis {
  impressions: number
  clicks: number
  click_rate: number
  click_visitors: number
  paid_amount: number
  paid_order_count: number
  conversion_rate: number
}

export interface CpsAnalysis {
  paid_amount: number
  paid_order_count: number
  click_visitors: number
  payment_expense: number
  settlement_expense: number
  settlement_amount: number
  settlement_order_count: number
  payment_cost_rate: number
  settlement_rate: number
  preorder_deposit_amount: number
  preorder_total_amount: number
  daily_metrics: CpsDailyMetric[]
}

export interface CpsDailyMetric {
  stat_date: string
  click_visitors: number
  paid_amount: number
  paid_order_count: number
  payment_expense: number
  settlement_amount: number
  settlement_order_count: number
  settlement_expense: number
  preorder_deposit_amount: number
  preorder_total_amount: number
}

export interface ContentAnalysis {
  view_count: number
  viewers: number
  product_click_users: number
  paid_amount: number
  paid_buyers: number
  interaction_count: number
  exposure_users: number
  interaction_users: number
  add_cart_users: number
  interaction_rate: number
  product_click_rate: number
  paid_amount_ratio: number
  daily_metrics: ContentDailyMetric[]
}

export interface ContentDailyMetric {
  stat_date: string
  viewers: number
  interaction_count: number
  product_click_users: number
  add_cart_users: number
  paid_buyers: number
  paid_amount: number
}

export interface NewCustomerDiscountDailyMetric {
  stat_date: string
  product_new_visitors: number | null
  paid_buyers: number | null
  paid_amount: number | null
  conversion_rate: number | null
  shop_paid_buyers: number | null
  shop_paid_amount: number | null
  record_status: "complete" | "partial" | "missing"
}

export interface NewCustomerDiscountAnalysis {
  product_new_visitors: number
  paid_buyers: number
  paid_amount: number
  conversion_rate: number
  shop_paid_buyers: number
  shop_paid_amount: number
  buyer_share: number
  amount_share: number
  daily_metrics: NewCustomerDiscountDailyMetric[]
}

export interface ShoppingGoldDailyMetric {
  stat_date: string
  recharge_amount: number
  paid_amount: number
  recharge_buyers: number
  paid_buyers: number
  product_visitors: number
  recharge_refund_amount: number
}

export interface ShoppingGoldAnalysis {
  recharge_amount: number
  paid_amount: number
  recharge_buyers: number
  paid_buyers: number
  product_visitors: number
  recharge_items: number
  recharge_sub_order_count: number
  recharge_refund_amount: number
  recharge_capital_amount: number
  average_recharge_amount: number
  customer_unit_price: number
  recharge_rate: number
  paid_amount_ratio: number
  daily_metrics: ShoppingGoldDailyMetric[]
}

export interface BybtDailyMetric {
  stat_date: string
  record_status: "complete" | "missing" | string
  visitors: number | null
  paid_buyers: number | null
  paid_amount: number | null
  online_items: number | null
  paid_sub_order_count: number | null
  paid_items: number | null
}

export interface BybtAnalysis {
  visitors: number
  paid_buyers: number
  paid_amount: number
  online_items: number
  paid_sub_order_count: number
  paid_items: number
  conversion_rate: number
  customer_unit_price: number
  items_per_buyer: number
  expected_days: number
  covered_days: number
  missing_dates: string[]
  daily_metrics: BybtDailyMetric[]
}

export interface AnalysisSnapshot {
  daily_metrics: AnalysisDailyMetric[]
  customer: CustomerAnalysis
  member: MemberAnalysis
  customer_service: CustomerServiceAnalysis
  customer_service_daily: CustomerServiceDailyMetric[]
  customer_service_accounts: CustomerServiceAccountMetric[]
  live: LiveAnalysis
  promotion: PromotionAnalysis
  brand_zone: BrandZoneAnalysis
  cps: CpsAnalysis
  content: ContentAnalysis
  new_customer_discount: NewCustomerDiscountAnalysis
  shopping_gold: ShoppingGoldAnalysis
  bybt: BybtAnalysis
}

export interface DashboardResponse {
  range_start: string
  range_end: string
  product_range_start: string
  product_range_end: string
  summary: {
    paid_amount: number
    visitors: number
    buyers: number
  conversion_rate: number
  promotion_cost: number
  roi: number
  average_daily_paid_amount: number
    customer_unit_price: number
    refund_amount: number
    net_paid_amount: number
    promotion_plan_spend: number
    promotion_attributed_paid_amount: number
    promotion_roi: number
    promotion_fee_ratio: number
  }
  daily_metrics: DailyMetric[]
  promotion_daily_metrics: PromotionDailyMetric[]
  top_products: ProductMetric[]
  traffic_sources: TrafficMetric[]
  promotion_plans: PromotionMetric[]
  promotion_scenes: PromotionSceneMetric[]
  freshness: DataFreshness[]
  period: DashboardPeriod
  comparison: SummaryComparison
  coverage: DataCoverage[]
  insights: BusinessInsight[]
  analysis?: AnalysisSnapshot | null
}

export interface SystemCapabilities {
  mode: "read_only"
  legacy_source: "configured" | "not_configured"
  enabled_modules: string[]
  disabled_modules: string[]
  safety_rules: string[]
}

export interface CaptureFamilySummary {
  family: string
  observations: number
}

export interface CaptureSummary {
  file_count: number
  first_date: string | null
  last_date: string | null
  imported_at: string | null
  families: CaptureFamilySummary[]
  daily_requests: Array<{
    business_date: string | null
    date_mode: string
    files: number
  }>
}

export interface ResponseEvidence {
  files: number
  json_like_files: number
  samples: Array<Record<string, unknown>>
  shape: Array<Record<string, unknown>>
}

export interface EndpointContract {
  host: string
  path: string
  method: string
  calls: number
  daily_calls: number
  success_calls: number
  statuses: Record<string, number>
  date_modes: Record<string, number>
  business_dates: Record<string, number>
  sample_params: Record<string, string>
  sample_headers: Record<string, string>
  response: ResponseEvidence
}

export interface ContractSummary {
  generated_at: string | null
  source: string
  api_observations: number
  endpoint_contracts: number
  daily_observations: number
  business_dates: Record<string, number>
  date_modes: Record<string, number>
  priority_paths: EndpointContract[]
}

export interface ContractCatalog {
  generated_at: string | null
  contracts: EndpointContract[]
}

export interface ImportRequestContract {
  method: string
  url: string
  query_params: Record<string, unknown>
  body_template: Record<string, unknown> | null
  runtime_credentials: string[]
  target_table: string
  execute: boolean
  write_database: boolean
}

export interface ImportCandidate {
  function: string
  line: number | null
  priority: string
  legacy_path: string
  date_mode: string
  shape_status: string
  request_contract: ImportRequestContract
}

export interface DailyDryRunSummary {
  generated_at: string | null
  mode: string
  day: string
  timezone: string
  source: string
  capture_db: string
  guardrails: {
    platform_requests_executed: number
    mysql_writes: number
    sqlite_connection: string
    raw_cookies_or_tokens_persisted: boolean
  }
  selected_priorities: string[]
  selected: ImportCandidate[]
  deferred: Array<{
    function: string
    priority: string
    legacy_path: string
    reason: string
  }>
}

export interface ImportRun {
  run_id: string
  day: string
  mode: string
  status: string
  source: string
  generated_at: string | null
  created_at: string
  updated_at: string
  selected_count: number
  deferred_count: number
  guardrails: DailyDryRunSummary["guardrails"]
}

export interface ImportRunItem {
  item_id: number
  run_id: string
  item_order: number
  function_name: string
  priority: string
  legacy_path: string
  method: string
  url: string
  target_table: string
  date_mode: string
  shape_status: string
  runtime_credentials: string[]
  query_params: Record<string, unknown>
  body_template: Record<string, unknown> | null
  status: string
  risk_notes: string[]
}

export interface ImportRunDetail extends ImportRun {
  items: ImportRunItem[]
}

export interface ImportRunList {
  runs: ImportRun[]
}

export interface CrawlRunDay {
  item_id: number
  run_id: string
  store_id: number
  business_day: string
  status: string
  metric_count: number | null
  error_message: string | null
}

export interface CrawlRun {
  run_id: string
  store_id: number
  task_type: string
  start_day: string
  end_day: string
  mode: string
  status: string
  planned_days: number
  success_days: number
  skipped_days: number
  failed_days: number
  started_at: string
  finished_at: string | null
  log_file: string
}

export interface CrawlRunDetail extends CrawlRun {
  days: CrawlRunDay[]
}

export interface CrawlRunList {
  runs: CrawlRun[]
}

export interface PlatformSessionStatus {
  code: string
  name: string
  status: string
  detail: string
  page_detected: boolean
  authenticated: boolean
  cookie_detected: boolean
  cookie_count: number
}

export interface BrowserHealth {
  status: string
  browser_connected: boolean
  source: string
  debug_port: number
  detail: string
  last_verified_at: string
  platforms: PlatformSessionStatus[]
}

export interface CollectionSettings {
  session_source: string
  browser_port: number
  cookie_env: string
  mode: string
  safety_rules: string[]
  inventory_credentials: InventoryCredentialStatus
}

export interface InventoryCredentialStatus {
  configured: boolean
  status: "not_configured" | "ready" | "refresh_required" | "invalid" | string
  source: string
  refresh_token_configured: boolean
  access_token_configured: boolean
  access_token_expired: boolean
  updated_at: string | null
  detail: string
}

export interface UpdateInventoryCredentialsRequest {
  refresh_token: string
  access_token?: string | null
  access_token_ttl_seconds?: number
}

export interface InventoryCredentialTestResponse {
  status: string
  detail: string
  credential_status: InventoryCredentialStatus
}

export interface DatasetTableCoverage {
  table: string
  present: boolean
  row_count: number
  raw_row_count: number
  latest_date: string | null
  status: string
}

export interface DatasetCoverage {
  key: string
  label: string
  group: string
  description: string
  collection_mode: "daily_fact" | "coverage_snapshot" | string
  status: "complete" | "partial" | "missing" | "failed" | "no_data" | "collecting" | string
  target_day: string
  present_tables: number
  expected_tables: number
  row_count: number
  latest_date: string | null
  last_attempt_at: string | null
  last_run_status: string | null
  error_message: string | null
  tables: DatasetTableCoverage[]
}

export interface DayCoverage {
  day: string
  complete: number
  no_data: number
  attention: number
  total: number
  coverage_percent: number
}

export interface CollectionBatch {
  batch_id: string
  business_day: string
  dataset_names: string[]
  trigger: string
  session_source: string
  refresh_existing: boolean
  status: string
  process_id: number | null
  completed_count: number
  failed_count: number
  started_at: string
  finished_at: string | null
  log_file: string
  error_message: string | null
  total_count: number
  settled_count: number
  progress_percent: number
  success_rate: number
  current_dataset_key: string | null
  current_dataset_label: string | null
  current_task_type: string | null
  failure_details: Array<{
    dataset_key: string
    dataset_label: string
    task_type: string | null
    run_id: string | null
    status: string
    error_message: string | null
  }>
}

export interface CollectionSchedule {
  enabled: boolean
  run_time: string
  timezone: string
  dataset_names: string[]
  session_source: string
  last_triggered_day: string | null
  last_triggered_at: string | null
  next_run_at: string | null
}

export interface CollectionOverview {
  target_day: string
  generated_at: string
  total_datasets: number
  complete_count: number
  partial_count: number
  missing_count: number
  failed_count: number
  no_data_count: number
  collecting_count: number
  coverage_percent: number
  datasets: DatasetCoverage[]
  recent_days: DayCoverage[]
  latest_batch: CollectionBatch | null
  schedule: CollectionSchedule
}

export interface ReviewCollectionRun {
  run_id: string
  mode: "initial" | "incremental" | string
  status: string
  started_at: string
  finished_at: string | null
  pages: number
  fetched_count: number
  inserted_count: number
  updated_count: number
  skipped_count: number
  stopped_reason: string | null
  error: string | null
}

export interface ReviewCollectionSummary {
  total_reviews: number
  first_review_date: string | null
  latest_review_date: string | null
  last_collected_at: string | null
  last_run: ReviewCollectionRun | null
  product_count: number
  series_count: number
}

export interface ReviewRecord {
  review_key: string
  platform_review_id: string | null
  user_name: string | null
  security_id: string | null
  emotion_type: string | null
  order_id: string | null
  item_id: string | null
  item_name: string | null
  item_link: string | null
  series: string | null
  review_date: string | null
  main_content: string
  append_content: string
  merged_content: string
  main_media: string[]
  append_media: string[]
  overview: string[]
  categories: string[]
  competitors: string[]
  is_negative: boolean
  sentiment: "positive" | "neutral" | "negative" | "unknown"
  fetched_at: string | null
}

export interface ReviewCategoryCount {
  name: string
  count: number
  share: number
}

export interface ReviewTrendPoint {
  day: string
  total: number
  negative: number
}

export interface ReviewRiskMetric {
  key: string
  label: string
  series: string | null
  total_reviews: number
  issue_reviews: number
  issue_rate: number
  top_issue: string | null
}

export interface ReviewAnalysis {
  scope: string
  product_id: string | null
  series: string | null
  start_date: string | null
  end_date: string | null
  total_reviews: number
  negative_reviews: number
  normal_reviews: number
  negative_rate: number
  append_reviews: number
  media_reviews: number
  product_count: number
  category_counts: ReviewCategoryCount[]
  competitor_counts: ReviewCategoryCount[]
  trend: ReviewTrendPoint[]
  risk_products: ReviewRiskMetric[]
  risk_series: ReviewRiskMetric[]
  top_reviews: ReviewRecord[]
}

export interface ReviewListResponse {
  items: ReviewRecord[]
  total: number
  page: number
  page_size: number
}

export interface AskRecord {
  ask_id: string
  item_id: string | null
  item_name: string | null
  item_link: string | null
  series: string | null
  user_name: string | null
  question: string
  question_date: string | null
  answer_count: number
  has_answer: boolean
  categories: string[]
  competitors: string[]
  fetched_at: string | null
}

export interface AskListResponse {
  items: AskRecord[]
  total: number
  page: number
  page_size: number
}

export interface AskSummary {
  total_questions: number
  answered_questions: number
  unanswered_questions: number
  answer_rate: number
  product_count: number
  first_question_date: string | null
  latest_question_date: string | null
  category_counts: ReviewCategoryCount[]
  last_run: ReviewCollectionRun | null
}

export interface StoreDataColumn {
  key: string
  label: string
}

export interface StoreDataDataset {
  key: string
  label: string
  description: string
  row_count: number
  first_date: string | null
  latest_date: string | null
  status: "current" | "stale" | "empty" | string
  lag_days: number | null
  columns: StoreDataColumn[]
}

export interface StoreDataCatalog {
  store_id: number
  reference_date: string | null
  available_count: number
  current_count: number
  stale_count: number
  empty_count: number
  datasets: StoreDataDataset[]
}

export interface StoreDataPreview {
  dataset: { key: string; label: string; description: string }
  store_id: number
  start_date: string | null
  end_date: string | null
  page: number
  page_size: number
  total: number
  columns: StoreDataColumn[]
  rows: Array<Record<string, unknown>>
}

export interface OperationCapability {
  key: string
  title: string
  status: "enabled" | "dry_run_only" | "disabled" | "planned"
  risk_level: "low" | "medium" | "high"
  mode: string
  guardrails: string[]
}

export interface OperationCenterSummary {
  mode: "read_only" | "dry_run_only"
  capabilities: OperationCapability[]
  required_flow: string[]
}

export interface PlatformRecord {
  platform_id: number
  code: string
  name: string
  status: string
}

export interface StoreRecord {
  store_id: number
  platform_id: number
  platform_name: string
  platform_store_id: string
  store_name: string
  status: string
  first_seen_at: string
  updated_at: string
}

export interface AuthConfiguration {
  enabled: boolean
  session_days: number
}

export interface AccessUser {
  user_id: number | null
  username: string
  display_name: string
  roles: string[]
  permissions: string[]
  menus: string[]
  store_ids: number[] | null
  brand_ids: string[] | null
  is_active: boolean
  created_at: string | null
  updated_at: string | null
  last_login_at: string | null
}

export interface AccessRoleRecord {
  code: string
  name: string
  description: string
  permissions: string[]
  menus: string[]
}

export interface AccessMenuRecord {
  code: string
  parent_code: string | null
  name: string
  menu_type: string
  path: string
  component: string
  permission: string | null
  order: number
  hidden: boolean
}

export interface BrandRecord {
  brand_id: string
  brand_subject_id: string
  brand_name: string
  status: string
  store_ids: number[]
}

export interface BrandDatasetStatus {
  key: string
  label: string
  table: string
  row_count: number
  min_day: string | null
  max_day: string | null
  imported: boolean
}

export interface BrandAssetSummary {
  brand: BrandRecord
  start_date: string | null
  end_date: string | null
  latest_day: string | null
  data_status: "available" | "not_imported" | string
  overview: Record<string, string | null>
  overview_trend: Array<Record<string, string | null>>
  stages: Array<Record<string, string | null>>
  dimensions: Array<Record<string, string | null>>
  datasets: BrandDatasetStatus[]
}

export interface AccessDirectory {
  users: AccessUser[]
  roles: AccessRoleRecord[]
  permissions: Array<{
    code: string
    name: string
    description: string
  }>
  menus: AccessMenuRecord[]
}

export interface ApiPermissionRecord {
  path: string
  method: string
  name: string
  module: string
  permission: string | null
  protected: boolean
}

export interface NotificationChannel {
  channel_id: number
  name: string
  provider: "dingtalk"
  webhook_env: string
  secret_env: string | null
  enabled: boolean
  created_at: string
  updated_at: string
  webhook_configured: boolean
  secret_configured: boolean
}

export interface NotificationDelivery {
  delivery_id: number
  channel_id: number
  channel_name: string | null
  message_type: "text" | "markdown"
  title: string
  content: string
  status: "sending" | "sent" | "failed" | string
  provider_code: string | null
  provider_message: string | null
  idempotency_key: string | null
  requested_by: string | null
  created_at: string
  sent_at: string | null
}

export interface NotificationDeliveryList {
  items: NotificationDelivery[]
  total: number
  page: number
  page_size: number
}

export interface StoreDailyOverview {
  store_id: number
  business_day: string
  paid_amount: number
  net_paid_amount: number
  visitors: number
  paid_buyers: number
  conversion_rate: number
  sign_refund_rate: number
  refund_finished_amount: number
  keyword_promotion_spend: number
  precision_audience_promotion_spend: number
  smart_scene_spend: number
  all_site_promotion_spend: number
  taoke_commission: number
  total_paid_amount: number
  refund_paid_time_amount: number
  amount_refund_rate: number
  add_cart_buyers: number
  product_favorite_buyers: number
  page_views: number
  average_stay_time: number
  add_cart_items: number
  paid_sub_order_count: number
  total_paid_sub_order_count: number
  order_refund_rate: number
  paid_items: number
  customer_unit_price: number
  older_paid_amount: number
  older_paid_buyers: number
  older_repurchase_rate: number
  refund_process_days: number
  wangwang_manual_response_seconds: number
  consultation_rate: number
  platform_duty_rate: number
  pickup_24h_rate: number
  logistics_arrival_hours: number
}
