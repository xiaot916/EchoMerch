import type {
  CaptureSummary,
  AccessDirectory,
  AccessRoleRecord,
  AccessUser,
  ApiPermissionRecord,
  BrandAssetSummary,
  BrandRecord,
  AuthConfiguration,
  ContractCatalog,
  ContractSummary,
  CrawlRunDetail,
  CrawlRunList,
  CollectionBatch,
  CollectionOverview,
  CollectionSchedule,
  DailyDryRunSummary,
  DashboardResponse,
  FlashSaleAnalysisResponse,
  UtryAnalysisResponse,
  PromotionProductListResponse,
  ProductAnalysisResponse,
  ProductMetric,
  TrafficTreeNode,
  PromotionWorkbenchResponse,
  ImportRunDetail,
  ImportRunList,
  OperationCenterSummary,
  StoreRecord,
  StoreActivityCalendarEvent,
  StoreDataCatalog,
  StoreDataPreview,
  BrowserHealth,
  CollectionSettings,
  SystemCapabilities,
  ReviewAnalysis,
  ReviewCollectionRun,
  ReviewCollectionSummary,
  ReviewListResponse,
  AskListResponse,
  AskSummary,
  AIAnalysisResponse,
  AIConfiguration,
  AIConnectionTest,
  AIConversationDetail,
  AIConversationListItem,
  PeriodReportResponse,
  NotificationChannel,
  NotificationDelivery,
  NotificationDeliveryList,
  InventoryManagementResponse,
  InventoryAnalysisResponse,
  InventorySyncResponse,
  InventorySyncStatusResponse,
  InventoryCredentialStatus,
  InventoryCredentialTestResponse,
  UpdateInventoryCredentialsRequest,
  MarketInsightResponse,
} from "./types"

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "")

function numeric(value: string | number): number {
  return typeof value === "number" ? value : Number(value)
}

function optionalNumeric(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null
  return numeric(value)
}

function normalizeAnalysis(analysis: NonNullable<DashboardResponse["analysis"]>): NonNullable<DashboardResponse["analysis"]> {
  return {
    ...analysis,
    daily_metrics: analysis.daily_metrics.map((item) => ({
      ...item,
      live_paid_amount: numeric(item.live_paid_amount),
      member_paid_amount: numeric(item.member_paid_amount),
      customer_service_sales: numeric(item.customer_service_sales),
      brand_paid_amount: numeric(item.brand_paid_amount),
      cps_paid_amount: numeric(item.cps_paid_amount),
      content_paid_amount: numeric(item.content_paid_amount),
    })),
    customer: {
      ...analysis.customer,
      new_customer_paid_amount: numeric(analysis.customer.new_customer_paid_amount),
      new_customer_conversion_rate: percent(analysis.customer.new_customer_conversion_rate),
      repeat_customer_paid_amount: numeric(analysis.customer.repeat_customer_paid_amount),
      repeat_rate: percent(analysis.customer.repeat_rate),
      no_purchase_conversion_rate: percent(analysis.customer.no_purchase_conversion_rate),
      segments: (analysis.customer.segments ?? []).map((item) => ({
        ...item,
        conversion_rate: percent(item.conversion_rate),
        paid_amount: numeric(item.paid_amount),
        unit_price: numeric(item.unit_price),
        member_rate: percent(item.member_rate),
        fan_rate: percent(item.fan_rate),
      })),
      daily_metrics: (analysis.customer.daily_metrics ?? []).map((item) => ({
        ...item,
        new_paid_amount: numeric(item.new_paid_amount),
        repeat_paid_amount: numeric(item.repeat_paid_amount),
      })),
    },
    member: {
      ...analysis.member,
      paid_amount: numeric(analysis.member.paid_amount),
      unit_price: numeric(analysis.member.unit_price),
      repurchase_rate: percent(analysis.member.repurchase_rate),
      repurchase_amount: numeric(analysis.member.repurchase_amount),
      recruit_conversion_rate: percent(analysis.member.recruit_conversion_rate),
      repurchase_cycle: numeric(analysis.member.repurchase_cycle),
      daily_metrics: (analysis.member.daily_metrics ?? []).map((item) => ({
        ...item,
        paid_amount: numeric(item.paid_amount),
        repurchase_amount: numeric(item.repurchase_amount),
      })),
      channels: (analysis.member.channels ?? []).map((item) => ({
        ...item,
        recruit_conversion_rate: percent(item.recruit_conversion_rate),
        paid_amount: numeric(item.paid_amount),
      })),
    },
    customer_service: {
      ...analysis.customer_service,
      sales_amount: numeric(analysis.customer_service.sales_amount),
      reception_rate: percent(analysis.customer_service.reception_rate),
      sales_conversion_rate: percent(analysis.customer_service.sales_conversion_rate),
      sales_ratio: percent(analysis.customer_service.sales_ratio),
      avg_reply_seconds: numeric(analysis.customer_service.avg_reply_seconds),
      satisfaction_rate: percent(analysis.customer_service.satisfaction_rate),
      refund_amount: numeric(analysis.customer_service.refund_amount),
      net_sales_amount: numeric(analysis.customer_service.net_sales_amount),
    },
    customer_service_daily: (analysis.customer_service_daily ?? []).map((item) => ({
      ...item,
      sales_amount: numeric(item.sales_amount),
      net_sales_amount: numeric(item.net_sales_amount),
      sales_ratio: percent(item.sales_ratio),
      avg_reply_seconds: numeric(item.avg_reply_seconds),
      satisfaction_rate: percent(item.satisfaction_rate),
    })),
    customer_service_accounts: (analysis.customer_service_accounts ?? []).map((item) => ({
      ...item,
      sales_amount: numeric(item.sales_amount),
      net_sales_amount: numeric(item.net_sales_amount),
      reception_rate: percent(item.reception_rate),
      sales_conversion_rate: percent(item.sales_conversion_rate),
    })),
    live: {
      ...analysis.live,
      paid_amount: numeric(analysis.live.paid_amount),
      shop_paid_amount: numeric(analysis.live.shop_paid_amount),
      live_during_paid_amount: numeric(analysis.live.live_during_paid_amount),
      post_paid_amount: numeric(analysis.live.post_paid_amount),
      talent_paid_amount: numeric(analysis.live.talent_paid_amount),
      deal_rate: percent(analysis.live.deal_rate),
      unit_price: numeric(analysis.live.unit_price),
      daily_metrics: (analysis.live.daily_metrics ?? []).map((item) => ({
        ...item,
        paid_amount: numeric(item.paid_amount),
        shop_paid_amount: numeric(item.shop_paid_amount),
        live_during_paid_amount: numeric(item.live_during_paid_amount),
        post_paid_amount: numeric(item.post_paid_amount),
        paid_amount_per_buyer: numeric(item.paid_amount_per_buyer),
        view_click_rate: percent(item.view_click_rate),
        click_deal_rate: percent(item.click_deal_rate),
      })),
      talents: (analysis.live.talents ?? []).map((item) => ({
        ...item,
        paid_amount: numeric(item.paid_amount),
        single_output: numeric(item.single_output),
        click_deal_rate: percent(item.click_deal_rate),
      })),
    },
    promotion: {
      ...analysis.promotion,
      spend: numeric(analysis.promotion.spend),
      paid_amount: numeric(analysis.promotion.paid_amount),
      roi: numeric(analysis.promotion.roi),
    },
    brand_zone: {
      ...analysis.brand_zone,
      click_rate: percent(analysis.brand_zone.click_rate),
      paid_amount: numeric(analysis.brand_zone.paid_amount),
      conversion_rate: percent(analysis.brand_zone.conversion_rate),
    },
    cps: {
      ...analysis.cps,
      paid_amount: numeric(analysis.cps.paid_amount),
      payment_expense: numeric(analysis.cps.payment_expense),
      settlement_expense: numeric(analysis.cps.settlement_expense),
      settlement_amount: numeric(analysis.cps.settlement_amount),
      payment_cost_rate: percent(analysis.cps.payment_cost_rate),
      settlement_rate: percent(analysis.cps.settlement_rate),
      preorder_deposit_amount: numeric(analysis.cps.preorder_deposit_amount),
      preorder_total_amount: numeric(analysis.cps.preorder_total_amount),
      daily_metrics: (analysis.cps.daily_metrics ?? []).map((item) => ({
        ...item,
        paid_amount: numeric(item.paid_amount),
        payment_expense: numeric(item.payment_expense),
        settlement_amount: numeric(item.settlement_amount),
        settlement_expense: numeric(item.settlement_expense),
        preorder_deposit_amount: numeric(item.preorder_deposit_amount),
        preorder_total_amount: numeric(item.preorder_total_amount),
      })),
    },
    content: {
      ...analysis.content,
      paid_amount: numeric(analysis.content.paid_amount),
      interaction_rate: percent(analysis.content.interaction_rate),
      product_click_rate: percent(analysis.content.product_click_rate),
      paid_amount_ratio: percent(analysis.content.paid_amount_ratio),
      daily_metrics: (analysis.content.daily_metrics ?? []).map((item) => ({
        ...item,
        paid_amount: numeric(item.paid_amount),
      })),
    },
    new_customer_discount: {
      ...analysis.new_customer_discount,
      paid_amount: numeric(analysis.new_customer_discount.paid_amount),
      conversion_rate: percent(analysis.new_customer_discount.conversion_rate),
      shop_paid_amount: numeric(analysis.new_customer_discount.shop_paid_amount),
      buyer_share: percent(analysis.new_customer_discount.buyer_share),
      amount_share: percent(analysis.new_customer_discount.amount_share),
      daily_metrics: (analysis.new_customer_discount.daily_metrics ?? []).map((item) => ({
        ...item,
        product_new_visitors: item.product_new_visitors === null ? null : numeric(item.product_new_visitors),
        paid_buyers: item.paid_buyers === null ? null : numeric(item.paid_buyers),
        paid_amount: item.paid_amount === null ? null : numeric(item.paid_amount),
        conversion_rate: item.conversion_rate === null ? null : percent(item.conversion_rate),
        shop_paid_buyers: item.shop_paid_buyers === null ? null : numeric(item.shop_paid_buyers),
        shop_paid_amount: item.shop_paid_amount === null ? null : numeric(item.shop_paid_amount),
      })),
    },
    shopping_gold: {
      ...analysis.shopping_gold,
      recharge_amount: numeric(analysis.shopping_gold.recharge_amount),
      paid_amount: numeric(analysis.shopping_gold.paid_amount),
      recharge_refund_amount: numeric(analysis.shopping_gold.recharge_refund_amount),
      recharge_capital_amount: numeric(analysis.shopping_gold.recharge_capital_amount),
      average_recharge_amount: numeric(analysis.shopping_gold.average_recharge_amount),
      customer_unit_price: numeric(analysis.shopping_gold.customer_unit_price),
      recharge_rate: percent(analysis.shopping_gold.recharge_rate),
      paid_amount_ratio: percent(analysis.shopping_gold.paid_amount_ratio),
      daily_metrics: (analysis.shopping_gold.daily_metrics ?? []).map((item) => ({
        ...item,
        recharge_amount: numeric(item.recharge_amount),
        paid_amount: numeric(item.paid_amount),
        recharge_refund_amount: numeric(item.recharge_refund_amount),
      })),
    },
    bybt: {
      ...analysis.bybt,
      paid_amount: numeric(analysis.bybt.paid_amount),
      conversion_rate: percent(analysis.bybt.conversion_rate),
      customer_unit_price: numeric(analysis.bybt.customer_unit_price),
      items_per_buyer: numeric(analysis.bybt.items_per_buyer),
      daily_metrics: (analysis.bybt.daily_metrics ?? []).map((item) => ({
        ...item,
        visitors: optionalNumeric(item.visitors),
        paid_buyers: optionalNumeric(item.paid_buyers),
        paid_amount: optionalNumeric(item.paid_amount),
        online_items: optionalNumeric(item.online_items),
        paid_sub_order_count: optionalNumeric(item.paid_sub_order_count),
        paid_items: optionalNumeric(item.paid_items),
      })),
    },
  }
}

function percent(value: string | number): number {
  const nextValue = numeric(value)
  return Math.abs(nextValue) <= 1 ? nextValue * 100 : nextValue
}

function normalizeDashboard(payload: DashboardResponse): DashboardResponse {
  return {
    ...payload,
    summary: {
      ...payload.summary,
      paid_amount: numeric(payload.summary.paid_amount),
      conversion_rate: numeric(payload.summary.conversion_rate),
      promotion_cost: numeric(payload.summary.promotion_cost),
      roi: numeric(payload.summary.roi),
      average_daily_paid_amount: numeric(payload.summary.average_daily_paid_amount),
      customer_unit_price: numeric(payload.summary.customer_unit_price),
      refund_amount: numeric(payload.summary.refund_amount),
      net_paid_amount: numeric(payload.summary.net_paid_amount),
      promotion_plan_spend: numeric(payload.summary.promotion_plan_spend),
      promotion_attributed_paid_amount: numeric(payload.summary.promotion_attributed_paid_amount),
      promotion_roi: numeric(payload.summary.promotion_roi),
      promotion_fee_ratio: numeric(payload.summary.promotion_fee_ratio),
    },
    daily_metrics: payload.daily_metrics.map((item) => ({
      ...item,
      paid_amount: numeric(item.paid_amount),
      conversion_rate: percent(item.conversion_rate),
      promotion_cost: numeric(item.promotion_cost),
      refund_amount: numeric(item.refund_amount),
      refund_rate: percent(item.refund_rate),
      promotion_plan_spend: numeric(item.promotion_plan_spend),
      promotion_attributed_paid_amount: numeric(item.promotion_attributed_paid_amount),
    })),
    promotion_daily_metrics: (payload.promotion_daily_metrics ?? []).map((item) => ({
      ...item,
      spend: numeric(item.spend),
      paid_amount: numeric(item.paid_amount),
    })),
    top_products: payload.top_products.map((item) => ({
      ...item,
      paid_amount: numeric(item.paid_amount),
      promotion_spend: numeric(item.promotion_spend),
    })),
    traffic_sources: payload.traffic_sources.map((item) => ({
      ...item,
      paid_amount: numeric(item.paid_amount),
      conversion_rate: percent(item.conversion_rate),
      uv_value: numeric(item.uv_value),
    })),
    promotion_plans: payload.promotion_plans.map((item) => ({
      ...item,
      spend: numeric(item.spend),
      paid_amount: optionalNumeric(item.paid_amount),
      buyers: item.buyers === null || item.buyers === undefined ? null : numeric(item.buyers),
    })),
    promotion_scenes: (payload.promotion_scenes ?? []).map((item) => ({
      ...item,
      campaign_count: numeric(item.campaign_count),
      spend: numeric(item.spend),
      paid_amount: numeric(item.paid_amount),
      buyers: numeric(item.buyers),
    })),
    comparison: {
      paid_amount: normalizeComparison(payload.comparison.paid_amount),
      visitors: normalizeComparison(payload.comparison.visitors),
      buyers: normalizeComparison(payload.comparison.buyers),
      conversion_rate: normalizeComparison(payload.comparison.conversion_rate),
      promotion_cost: normalizeComparison(payload.comparison.promotion_cost),
    },
    analysis: payload.analysis ? normalizeAnalysis(payload.analysis) : null,
  }
}

function normalizeComparison(value: DashboardResponse["comparison"]["paid_amount"]): DashboardResponse["comparison"]["paid_amount"] {
  return {
    current: numeric(value.current),
    previous: numeric(value.previous),
    delta: numeric(value.delta),
    change_percent: value.change_percent === null ? null : numeric(value.change_percent),
  }
}

async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { Accept: "application/json" },
    signal,
    credentials: "include",
  })

  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail || `请求失败：${response.status}`)
  }

  return response.json() as Promise<T>
}

async function apiPost<T>(path: string, body: Record<string, unknown>, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
    signal,
    credentials: "include",
  })

  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail || `请求失败：${response.status}`)
  }

  return response.json() as Promise<T>
}

export async function analyzeWithAI(request: {
  question: string
  conversation_id?: string | null
  store_id?: number | null
  start_date?: string | null
  end_date?: string | null
  domain?: "auto" | "overview" | "traffic" | "promotion" | "market" | "product" | "customer" | "customer-service" | "content" | "live" | "campaign" | "reviews"
  page_context?: Record<string, unknown>
  use_model?: boolean
}): Promise<AIAnalysisResponse> {
  return apiPost<AIAnalysisResponse>("/api/v1/ai/analyze", request)
}

export type AIStreamEvent = {
  event: "planner" | "skill" | "mcp" | "model" | "token" | "final" | "error" | string
  status?: string
  name?: string
  detail?: string
  text?: string
  response?: AIAnalysisResponse | PeriodReportResponse
  skill?: AIAnalysisResponse["skill"]
  supporting_skills?: AIAnalysisResponse["supporting_skills"]
  result_status?: string
  elapsed_ms?: number
}

function errorDetailText(value: unknown, fallback: string): string {
  if (typeof value === "string" && value.trim()) return value
  if (Array.isArray(value)) {
    const items = value.map((item) => {
      if (!item || typeof item !== "object") return String(item || "")
      const detail = item as { loc?: unknown[]; msg?: unknown }
      const field = Array.isArray(detail.loc) ? detail.loc.filter((part) => part !== "body").join(".") : ""
      return [field, detail.msg].filter(Boolean).join("：")
    }).filter(Boolean)
    if (items.length) return items.join("；")
  }
  if (value && typeof value === "object") return JSON.stringify(value)
  return fallback
}

async function streamAIResponse<T>(path: string, request: Record<string, unknown>, onEvent: (event: AIStreamEvent) => void): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { Accept: "text/event-stream", "Content-Type": "application/json" },
    body: JSON.stringify(request),
    credentials: "include",
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(errorDetailText(payload?.detail, `请求失败：${response.status}`))
  }
  if (!response.body) throw new Error("浏览器不支持 AI 流式响应")
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""
  let final: T | null = null
  const consume = (block: string) => {
    const lines = block.split(/\r?\n/)
    let event = "message"
    const data: string[] = []
    for (const line of lines) {
      if (line.startsWith("event:")) event = line.slice(6).trim()
      else if (line.startsWith("data:")) data.push(line.slice(5).trimStart())
    }
    if (!data.length) return
    try {
      const payload = JSON.parse(data.join("\n")) as Omit<AIStreamEvent, "event"> & { response?: T }
      const parsed = { event, ...payload } as AIStreamEvent
      // Rendering progress must never turn a valid final response into a
      // failed request. Some browsers can briefly receive a progress payload
      // before Vue has mounted the pending message; keep parsing the stream
      // even if the UI callback cannot consume that individual event.
      try {
        onEvent(parsed)
      } catch (error) {
        console.warn("AI 流式进度展示失败，继续等待最终结果", error)
      }
      if (event === "final" && payload.response) final = payload.response
      if (event === "error") throw new Error(payload.detail || "AI 分析失败")
    } catch (error) {
      if (error instanceof SyntaxError) return
      throw error
    }
  }
  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
    const blocks = buffer.split(/\r?\n\r?\n/)
    buffer = blocks.pop() || ""
    for (const block of blocks) consume(block)
    if (done) break
  }
  if (buffer.trim()) consume(buffer)
  if (!final) throw new Error("AI 流式响应未返回最终结果")
  return final
}

export async function streamAnalyzeWithAI(
  request: Parameters<typeof analyzeWithAI>[0],
  onEvent: (event: AIStreamEvent) => void,
): Promise<AIAnalysisResponse> {
  return streamAIResponse<AIAnalysisResponse>("/api/v1/ai/analyze/stream", request as Record<string, unknown>, onEvent)
}

export async function buildPeriodReport(request: {
  report_type: "daily" | "weekly" | "monthly" | "mtd" | "daily_series"
  conversation_id?: string | null
  anchor_date?: string | null
  store_id?: number | null
  target_gmv?: number | null
  use_model?: boolean
}): Promise<PeriodReportResponse> {
  return apiPost<PeriodReportResponse>("/api/v1/ai/reports/period", request)
}

export async function streamPeriodReport(
  request: Parameters<typeof buildPeriodReport>[0],
  onEvent: (event: AIStreamEvent) => void,
): Promise<PeriodReportResponse> {
  return streamAIResponse<PeriodReportResponse>("/api/v1/ai/reports/period/stream", request as Record<string, unknown>, onEvent)
}

export async function fetchAIConversations(storeId?: number | null): Promise<AIConversationListItem[]> {
  const params = new URLSearchParams()
  if (storeId) params.set("store_id", String(storeId))
  const suffix = params.size ? `?${params.toString()}` : ""
  return apiGet<AIConversationListItem[]>(`/api/v1/ai/conversations${suffix}`)
}

export async function fetchAIConversation(conversationId: string, storeId?: number | null): Promise<AIConversationDetail> {
  const params = new URLSearchParams()
  if (storeId) params.set("store_id", String(storeId))
  const suffix = params.size ? `?${params.toString()}` : ""
  return apiGet<AIConversationDetail>(`/api/v1/ai/conversations/${encodeURIComponent(conversationId)}${suffix}`)
}

export async function deleteAIConversation(conversationId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1/ai/conversations/${encodeURIComponent(conversationId)}`, {
    method: "DELETE",
    credentials: "include",
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail || `删除会话失败：${response.status}`)
  }
}

export async function fetchAIConfiguration(): Promise<AIConfiguration> {
  return apiGet<AIConfiguration>("/api/v1/ai/configuration")
}

export async function updateAIConfiguration(request: {
  base_url: string
  api_path: string
  model: string
  timeout_seconds: number
  api_key?: string | null
}): Promise<AIConfiguration> {
  return apiRequest<AIConfiguration>("/api/v1/ai/configuration", {
    method: "PUT",
    body: JSON.stringify(request),
  })
}

export async function testAIConfiguration(): Promise<AIConnectionTest> {
  return apiPost<AIConnectionTest>("/api/v1/ai/configuration/test", {})
}

export async function fetchInventoryManagement(options: {
  storeId?: number | null
  query?: string
  series?: string
  specification?: string
  size?: string
  stockStatus?: string
  page?: number
  pageSize?: number
} = {}): Promise<InventoryManagementResponse> {
  const params = new URLSearchParams()
  if (options.storeId) params.set("store_id", String(options.storeId))
  if (options.query) params.set("query", options.query)
  if (options.series) params.set("series", options.series)
  if (options.specification) params.set("specification", options.specification)
  if (options.size) params.set("size", options.size)
  if (options.stockStatus) params.set("stock_status", options.stockStatus)
  if (options.page) params.set("page", String(options.page))
  if (options.pageSize) params.set("page_size", String(options.pageSize))
  return apiGet<InventoryManagementResponse>(`/api/v1/inventory/management?${params.toString()}`)
}

export async function fetchInventoryAnalysis(options: {
  storeId?: number | null
  query?: string
  stockStatus?: string
  limit?: number
} = {}): Promise<InventoryAnalysisResponse> {
  const params = new URLSearchParams()
  if (options.storeId) params.set("store_id", String(options.storeId))
  if (options.query) params.set("query", options.query)
  if (options.stockStatus) params.set("stock_status", options.stockStatus)
  if (options.limit) params.set("limit", String(options.limit))
  return apiGet<InventoryAnalysisResponse>(`/api/v1/inventory/analysis?${params.toString()}`)
}

export async function syncInventoryNow(storeId?: number | null): Promise<InventorySyncResponse> {
  return apiPost<InventorySyncResponse>("/api/v1/inventory/sync", { store_id: storeId ?? null })
}

export async function fetchInventorySyncStatus(storeId?: number | null): Promise<InventorySyncStatusResponse> {
  const suffix = storeId ? `?store_id=${encodeURIComponent(String(storeId))}` : ""
  return apiGet<InventorySyncStatusResponse>(`/api/v1/inventory/sync/status${suffix}`)
}

export async function fetchMarketInsights(options: {
  startDate?: string
  endDate?: string
  rankType?: "all" | "shop" | "item" | "content"
  keywordType?: "all" | "core" | "search" | "trend" | "modify"
  query?: string
  limit?: number
} = {}, signal?: AbortSignal): Promise<MarketInsightResponse> {
  const params = new URLSearchParams()
  if (options.startDate) params.set("start_date", options.startDate)
  if (options.endDate) params.set("end_date", options.endDate)
  if (options.rankType && options.rankType !== "all") params.set("rank_type", options.rankType)
  if (options.keywordType && options.keywordType !== "all") params.set("keyword_type", options.keywordType)
  if (options.query) params.set("query", options.query)
  if (options.limit) params.set("limit", String(options.limit))
  return apiGet<MarketInsightResponse>(`/api/v1/analytics/market?${params.toString()}`, signal)
}

async function apiRequest<T>(path: string, options: { method: "PUT" | "PATCH"; body: string }): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: options.body,
    credentials: "include",
  })

  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail || `请求失败：${response.status}`)
  }

  return response.json() as Promise<T>
}

export async function fetchDashboard(
  startDate?: string,
  endDate?: string,
  storeId?: number,
  signal?: AbortSignal,
): Promise<DashboardResponse> {
  const params = new URLSearchParams()
  if (startDate) params.set("start_date", startDate)
  if (endDate) params.set("end_date", endDate)
  if (storeId) params.set("store_id", String(storeId))
  const suffix = params.size ? `?${params.toString()}` : ""
  return normalizeDashboard(await apiGet<DashboardResponse>(`/api/v1/analytics/dashboard${suffix}`, signal))
}

export async function fetchFlashSaleAnalysis(
  startDate?: string,
  endDate?: string,
  storeId?: number,
  signal?: AbortSignal,
): Promise<FlashSaleAnalysisResponse> {
  const params = new URLSearchParams()
  if (startDate) params.set("start_date", startDate)
  if (endDate) params.set("end_date", endDate)
  if (storeId) params.set("store_id", String(storeId))
  const payload = await apiGet<FlashSaleAnalysisResponse>(`/api/v1/analytics/marketing/flash-sale?${params.toString()}`, signal)
  const normalizeSummary = (summary: FlashSaleAnalysisResponse["summary"]) => ({
    ...summary,
    paid_amount: numeric(summary.paid_amount),
    conversion_rate: percent(summary.conversion_rate),
    customer_unit_price: numeric(summary.customer_unit_price),
    burst_coefficient_peak: summary.burst_coefficient_peak === null ? null : numeric(summary.burst_coefficient_peak),
    shop_paid_amount: summary.shop_paid_amount === null ? null : numeric(summary.shop_paid_amount),
    shop_paid_share: summary.shop_paid_share === null ? null : percent(summary.shop_paid_share),
  })
  return {
    ...payload,
    summary: normalizeSummary(payload.summary),
    previous_summary: normalizeSummary(payload.previous_summary),
    comparison: Object.fromEntries(Object.entries(payload.comparison).map(([key, value]) => [key, value === null ? null : numeric(value)])) as FlashSaleAnalysisResponse["comparison"],
    daily_metrics: payload.daily_metrics.map((item) => ({
      ...item,
      paid_amount: item.paid_amount === null ? null : numeric(item.paid_amount),
      burst_coefficient: item.burst_coefficient === null ? null : numeric(item.burst_coefficient),
    })),
  }
}

export async function fetchUtryAnalysis(
  startDate?: string,
  endDate?: string,
  storeId?: number,
  signal?: AbortSignal,
): Promise<UtryAnalysisResponse> {
  const params = new URLSearchParams()
  if (startDate) params.set("start_date", startDate)
  if (endDate) params.set("end_date", endDate)
  if (storeId) params.set("store_id", String(storeId))
  const payload = await apiGet<UtryAnalysisResponse>(`/api/v1/analytics/marketing/utry?${params.toString()}`, signal)
  const normalizeSnapshot = (snapshot: UtryAnalysisResponse["latest_repurchase"]): UtryAnalysisResponse["latest_repurchase"] => ({
    ...snapshot,
    product_count: numeric(snapshot.product_count),
    bound_regular_product_count: numeric(snapshot.bound_regular_product_count),
    configured_coupon_count: numeric(snapshot.configured_coupon_count),
    configured_gift_count: numeric(snapshot.configured_gift_count),
    bound_regular_product_share: snapshot.bound_regular_product_share === null ? null : percent(snapshot.bound_regular_product_share),
    configured_coupon_share: snapshot.configured_coupon_share === null ? null : percent(snapshot.configured_coupon_share),
    configured_gift_share: snapshot.configured_gift_share === null ? null : percent(snapshot.configured_gift_share),
    store_30d_repurchase_uv: numeric(snapshot.store_30d_repurchase_uv),
    store_30d_repurchase_amount: numeric(snapshot.store_30d_repurchase_amount),
    store_90d_repurchase_uv: numeric(snapshot.store_90d_repurchase_uv),
    store_90d_repurchase_amount: numeric(snapshot.store_90d_repurchase_amount),
    store_365d_repurchase_uv: numeric(snapshot.store_365d_repurchase_uv),
    store_365d_repurchase_amount: numeric(snapshot.store_365d_repurchase_amount),
    brand_365d_repurchase_uv: numeric(snapshot.brand_365d_repurchase_uv),
    brand_365d_repurchase_amount: numeric(snapshot.brand_365d_repurchase_amount),
  })
  return {
    ...payload,
    sample_summary: {
      ...payload.sample_summary,
      sample_orders: numeric(payload.sample_summary.sample_orders),
      sample_people: numeric(payload.sample_summary.sample_people),
      sample_gmv: numeric(payload.sample_summary.sample_gmv),
      merchant_new_customers_180d: numeric(payload.sample_summary.merchant_new_customers_180d),
      merchant_new_customers_365d: numeric(payload.sample_summary.merchant_new_customers_365d),
      new_members: numeric(payload.sample_summary.new_members),
      new_followers: numeric(payload.sample_summary.new_followers),
      average_orders_per_person: numeric(payload.sample_summary.average_orders_per_person),
      sample_gmv_per_person: numeric(payload.sample_summary.sample_gmv_per_person),
      merchant_new_customer_rate_180d: payload.sample_summary.merchant_new_customer_rate_180d === null ? null : percent(payload.sample_summary.merchant_new_customer_rate_180d),
      merchant_new_customer_rate_365d: payload.sample_summary.merchant_new_customer_rate_365d === null ? null : percent(payload.sample_summary.merchant_new_customer_rate_365d),
    },
    latest_repurchase: normalizeSnapshot(payload.latest_repurchase),
    previous_repurchase: normalizeSnapshot(payload.previous_repurchase),
    daily_metrics: payload.daily_metrics.map((item) => ({
      ...item,
      sample_people: optionalNumeric(item.sample_people), sample_orders: optionalNumeric(item.sample_orders), sample_gmv: optionalNumeric(item.sample_gmv),
      merchant_new_customers_180d: optionalNumeric(item.merchant_new_customers_180d), merchant_new_customers_365d: optionalNumeric(item.merchant_new_customers_365d),
      new_members: optionalNumeric(item.new_members), new_followers: optionalNumeric(item.new_followers),
      store_30d_repurchase_amount: optionalNumeric(item.store_30d_repurchase_amount), store_90d_repurchase_amount: optionalNumeric(item.store_90d_repurchase_amount), store_365d_repurchase_amount: optionalNumeric(item.store_365d_repurchase_amount),
    })),
    products: payload.products.map((item) => ({
      ...item,
      sample_people: optionalNumeric(item.sample_people), sample_orders: optionalNumeric(item.sample_orders), sample_gmv: optionalNumeric(item.sample_gmv),
      merchant_new_customers_180d: optionalNumeric(item.merchant_new_customers_180d), merchant_new_customers_365d: optionalNumeric(item.merchant_new_customers_365d),
      new_members: optionalNumeric(item.new_members), new_followers: optionalNumeric(item.new_followers),
      store_30d_repurchase_uv: optionalNumeric(item.store_30d_repurchase_uv), store_30d_repurchase_amount: optionalNumeric(item.store_30d_repurchase_amount),
      store_90d_repurchase_uv: optionalNumeric(item.store_90d_repurchase_uv), store_90d_repurchase_amount: optionalNumeric(item.store_90d_repurchase_amount),
      store_365d_repurchase_uv: optionalNumeric(item.store_365d_repurchase_uv), store_365d_repurchase_amount: optionalNumeric(item.store_365d_repurchase_amount),
      brand_365d_repurchase_amount: optionalNumeric(item.brand_365d_repurchase_amount),
    })),
  }
}

async function fetchPromotionProductItems(
  endpoint: string,
  startDate?: string,
  endDate?: string,
  storeId?: number,
  search?: string,
  page = 1,
  pageSize = 50,
  sort = "paid_amount",
  signal?: AbortSignal,
): Promise<PromotionProductListResponse> {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize), sort })
  if (startDate) params.set("start_date", startDate)
  if (endDate) params.set("end_date", endDate)
  if (storeId) params.set("store_id", String(storeId))
  if (search) params.set("search", search)
  const payload = await apiGet<PromotionProductListResponse>(`${endpoint}?${params.toString()}`, signal)
  return {
    ...payload,
    items: payload.items.map((item) => ({
      ...item,
      visitors: optionalNumeric(item.visitors),
      paid_order_count: optionalNumeric(item.paid_order_count),
      paid_items: optionalNumeric(item.paid_items),
      paid_amount: optionalNumeric(item.paid_amount),
      new_customers: optionalNumeric(item.new_customers),
      conversion_rate: optionalNumeric(item.conversion_rate),
    })),
  }
}

export function fetchBybtProductItems(startDate?: string, endDate?: string, storeId?: number, search?: string, page = 1, pageSize = 50, sort = "paid_amount", signal?: AbortSignal): Promise<PromotionProductListResponse> {
  return fetchPromotionProductItems("/api/v1/analytics/marketing/bybt/items", startDate, endDate, storeId, search, page, pageSize, sort, signal)
}

export function fetchFlashSaleProductItems(startDate?: string, endDate?: string, storeId?: number, search?: string, page = 1, pageSize = 50, sort = "paid_amount", signal?: AbortSignal): Promise<PromotionProductListResponse> {
  return fetchPromotionProductItems("/api/v1/analytics/marketing/flash-sale/items", startDate, endDate, storeId, search, page, pageSize, sort, signal)
}

export async function fetchPromotionWorkbench(
  startDate?: string,
  endDate?: string,
  storeId?: number,
  signal?: AbortSignal,
): Promise<PromotionWorkbenchResponse> {
  const params = new URLSearchParams()
  if (startDate) params.set("start_date", startDate)
  if (endDate) params.set("end_date", endDate)
  if (storeId) params.set("store_id", String(storeId))
  const suffix = params.size ? `?${params.toString()}` : ""
  const payload = await apiGet<PromotionWorkbenchResponse>(`/api/v1/analytics/promotions${suffix}`, signal)
  const normalizeMetric = (item: PromotionWorkbenchResponse["campaigns"][number]) => ({
    ...item,
    impressions: numeric(item.impressions), clicks: numeric(item.clicks), spend: numeric(item.spend), paid_amount: numeric(item.paid_amount), direct_paid_amount: numeric(item.direct_paid_amount), indirect_paid_amount: numeric(item.indirect_paid_amount), orders: numeric(item.orders), buyers: numeric(item.buyers), carts: numeric(item.carts), favorites: numeric(item.favorites), new_buyers: numeric(item.new_buyers), member_paid_amount: numeric(item.member_paid_amount), natural_paid_amount: numeric(item.natural_paid_amount),
  })
  return {
    ...payload,
    summary: Object.fromEntries(Object.entries(payload.summary).map(([key, value]) => [key, typeof value === "string" ? numeric(value) : value])) as PromotionWorkbenchResponse["summary"],
    daily_metrics: payload.daily_metrics.map((item) => Object.fromEntries(Object.entries(item).map(([key, value]) => [key, typeof value === "string" && key !== "stat_date" ? numeric(value) : value])) as PromotionWorkbenchResponse["daily_metrics"][number]),
    scenes: payload.scenes.map(normalizeMetric), campaigns: payload.campaigns.map(normalizeMetric), adgroups: payload.adgroups.map(normalizeMetric), audiences: payload.audiences.map(normalizeMetric), keywords: payload.keywords.map(normalizeMetric), items: payload.items.map(normalizeMetric), contents: payload.contents.map(normalizeMetric),
  }
}

export async function fetchCapabilities(): Promise<SystemCapabilities> {
  return apiGet<SystemCapabilities>("/api/v1/system/capabilities")
}

export async function fetchCaptureSummary(): Promise<CaptureSummary> {
  return apiGet<CaptureSummary>("/api/v1/captures/summary")
}

export async function fetchContractSummary(): Promise<ContractSummary> {
  return apiGet<ContractSummary>("/api/v1/contracts/summary")
}

export async function fetchDailyContracts(limit = 40): Promise<ContractCatalog> {
  return apiGet<ContractCatalog>(`/api/v1/contracts/endpoints?daily_only=true&limit=${limit}`)
}

export async function fetchDailyDryRun(day?: string): Promise<DailyDryRunSummary> {
  const suffix = day ? `?day=${encodeURIComponent(day)}` : ""
  return apiGet<DailyDryRunSummary>(`/api/v1/imports/daily-dry-run${suffix}`)
}

export async function fetchImportRuns(limit = 10): Promise<ImportRunList> {
  return apiGet<ImportRunList>(`/api/v1/imports/runs?limit=${limit}`)
}

export async function fetchImportRun(runId: string): Promise<ImportRunDetail> {
  return apiGet<ImportRunDetail>(`/api/v1/imports/runs/${encodeURIComponent(runId)}`)
}

export async function createDryRunImportRun(day?: string): Promise<ImportRunDetail> {
  return apiPost<ImportRunDetail>("/api/v1/imports/runs/dry-run", day ? { day } : {})
}

export async function fetchCrawlRuns(limit = 10): Promise<CrawlRunList> {
  return apiGet<CrawlRunList>(`/api/v1/imports/crawl-runs?limit=${limit}`)
}

export async function fetchCrawlRun(runId: string): Promise<CrawlRunDetail> {
  return apiGet<CrawlRunDetail>(`/api/v1/imports/crawl-runs/${encodeURIComponent(runId)}`)
}

const STORES_CACHE_TTL_MS = 5 * 60 * 1000
let storesCache: { data: StoreRecord[]; expiresAt: number } | null = null
let storesRequest: Promise<StoreRecord[]> | null = null

/** Share the store directory across views while allowing an explicit refresh. */
export async function fetchStores(forceRefresh = false): Promise<StoreRecord[]> {
  const now = Date.now()
  if (!forceRefresh && storesCache && storesCache.expiresAt > now) {
    return storesCache.data
  }
  if (storesRequest) return storesRequest

  storesRequest = apiGet<StoreRecord[]>("/api/v1/warehouse/stores")
    .then((data) => {
      storesCache = { data, expiresAt: Date.now() + STORES_CACHE_TTL_MS }
      return data
    })
    .finally(() => {
      storesRequest = null
    })
  return storesRequest
}

export async function fetchBrandAssetsBrands(): Promise<BrandRecord[]> {
  return apiGet<BrandRecord[]>("/api/v1/brand-assets/brands")
}

export async function fetchBrandAssetSummary(
  brandId?: string,
  startDate?: string,
  endDate?: string,
): Promise<BrandAssetSummary> {
  const query = new URLSearchParams()
  if (brandId) query.set("brand_id", brandId)
  if (startDate) query.set("start_date", startDate)
  if (endDate) query.set("end_date", endDate)
  return apiGet<BrandAssetSummary>(`/api/v1/brand-assets/summary?${query.toString()}`)
}

export async function fetchAnalyticsProducts(
  startDate?: string,
  endDate?: string,
  storeId?: number,
): Promise<ProductMetric[]> {
  const query = new URLSearchParams()
  if (startDate) query.set("start_date", startDate)
  if (endDate) query.set("end_date", endDate)
  if (storeId) query.set("store_id", String(storeId))
  const payload = await apiGet<ProductMetric[]>(`/api/v1/analytics/products?${query.toString()}`)
  return payload.map((item) => ({
    ...item,
    paid_amount: numeric(item.paid_amount),
    buyers: numeric(item.buyers),
    visitors: numeric(item.visitors),
    add_cart_users: numeric(item.add_cart_users),
    favorite_users: numeric(item.favorite_users),
    page_views: numeric(item.page_views),
    search_visitors: numeric(item.search_visitors),
    promotion_spend: numeric(item.promotion_spend),
  }))
}

export async function fetchTrafficTree(
  startDate?: string,
  endDate?: string,
  storeId?: number,
  signal?: AbortSignal,
): Promise<TrafficTreeNode[]> {
  const query = new URLSearchParams()
  if (startDate) query.set("start_date", startDate)
  if (endDate) query.set("end_date", endDate)
  if (storeId) query.set("store_id", String(storeId))
  const normalize = (node: TrafficTreeNode): TrafficTreeNode => ({
    ...node,
    visitors: numeric(node.visitors),
    paid_amount: numeric(node.paid_amount),
    buyers: numeric(node.buyers),
    new_visitors: numeric(node.new_visitors),
    add_cart_users: numeric(node.add_cart_users),
    favorite_users: numeric(node.favorite_users),
    conversion_rate: percent(node.conversion_rate),
    uv_value: numeric(node.uv_value),
    children: (node.children || []).map(normalize),
  })
  return (await apiGet<TrafficTreeNode[]>(`/api/v1/analytics/traffic-tree?${query.toString()}`, signal)).map(normalize)
}

export async function fetchProductAnalysis(
  productId: string,
  startDate?: string,
  endDate?: string,
  storeId?: number,
): Promise<ProductAnalysisResponse> {
  const query = new URLSearchParams()
  if (startDate) query.set("start_date", startDate)
  if (endDate) query.set("end_date", endDate)
  if (storeId) query.set("store_id", String(storeId))
  const payload = await apiGet<ProductAnalysisResponse>(`/api/v1/analytics/products/${encodeURIComponent(productId)}?${query.toString()}`)
  const normalize = (item: ProductMetric): ProductMetric => ({
    ...item,
    paid_amount: numeric(item.paid_amount),
    buyers: numeric(item.buyers),
    visitors: numeric(item.visitors),
    add_cart_users: numeric(item.add_cart_users),
    favorite_users: numeric(item.favorite_users),
    page_views: numeric(item.page_views),
    search_visitors: numeric(item.search_visitors),
    promotion_spend: numeric(item.promotion_spend),
  })
  return {
    ...payload,
    product: payload.product ? normalize(payload.product) : null,
    products: payload.products.map(normalize),
    peers: payload.peers.map(normalize),
    daily_metrics: payload.daily_metrics.map((item) => ({
      ...item,
      paid_amount: numeric(item.paid_amount),
      buyers: numeric(item.buyers),
      visitors: numeric(item.visitors),
      add_cart_users: numeric(item.add_cart_users),
      favorite_users: numeric(item.favorite_users),
      promotion_spend: numeric(item.promotion_spend),
      conversion_rate: percent(item.conversion_rate),
    })),
  }
}

export async function fetchActivityCalendar(
  storeId: number,
  startDate: string,
  endDate: string,
): Promise<StoreActivityCalendarEvent[]> {
  const query = new URLSearchParams({ start_date: startDate, end_date: endDate })
  return apiGet<StoreActivityCalendarEvent[]>(`/api/v1/warehouse/stores/${storeId}/activity-calendar?${query}`)
}

export async function fetchOperationSummary(): Promise<OperationCenterSummary> {
  return apiGet<OperationCenterSummary>("/api/v1/operations/summary")
}

export async function fetchNotificationChannels(): Promise<NotificationChannel[]> {
  return apiGet<NotificationChannel[]>("/api/v1/notifications/channels")
}

export async function createNotificationChannel(request: {
  name: string
  provider: "dingtalk"
  webhook_env: string
  secret_env: string | null
  enabled: boolean
}): Promise<NotificationChannel> {
  return apiPost<NotificationChannel>("/api/v1/notifications/channels", request)
}

export async function updateNotificationChannel(channelId: number, request: {
  name: string
  provider: "dingtalk"
  webhook_env: string
  secret_env: string | null
  enabled: boolean
}): Promise<NotificationChannel> {
  return apiRequest<NotificationChannel>(`/api/v1/notifications/channels/${channelId}`, { method: "PUT", body: JSON.stringify(request) })
}

export async function fetchNotificationDeliveries(page = 1, pageSize = 20): Promise<NotificationDeliveryList> {
  return apiGet<NotificationDeliveryList>(`/api/v1/notifications/deliveries?page=${page}&page_size=${pageSize}`)
}

export async function sendNotification(request: {
  channel_id: number
  message_type: "text" | "markdown"
  title: string
  content: string
  at_all: boolean
  idempotency_key?: string
}): Promise<NotificationDelivery> {
  return apiPost<NotificationDelivery>("/api/v1/notifications/send", request)
}

export async function fetchAuthConfiguration(): Promise<AuthConfiguration> {
  return apiGet<AuthConfiguration>("/api/v1/auth/configuration")
}

export async function fetchCurrentUser(): Promise<AccessUser> {
  return (await apiGet<{ user: AccessUser }>("/api/v1/auth/me")).user
}

export async function login(username: string, password: string): Promise<AccessUser> {
  return (await apiPost<{ user: AccessUser }>("/api/v1/auth/login", { username, password })).user
}

export async function changeCurrentPassword(currentPassword: string, newPassword: string): Promise<void> {
  await apiPost<{ detail: string; relogin_required: boolean }>("/api/v1/auth/change-password", {
    current_password: currentPassword,
    new_password: newPassword,
  })
}

export async function logout(): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1/auth/logout`, {
    method: "POST",
    headers: { Accept: "application/json" },
    credentials: "include",
  })
  if (!response.ok && response.status !== 204) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail || `请求失败：${response.status}`)
  }
}

export async function fetchAccessDirectory(): Promise<AccessDirectory> {
  return apiGet<AccessDirectory>("/api/v1/access/directory")
}

export async function updateRoleAccess(roleCode: string, request: {
  permission_codes: string[]
  menu_codes: string[]
}): Promise<AccessRoleRecord> {
  return apiRequest<AccessRoleRecord>(`/api/v1/access/roles/${encodeURIComponent(roleCode)}/access`, {
    method: "PUT",
    body: JSON.stringify(request),
  })
}

export async function fetchApiPermissions(signal?: AbortSignal): Promise<ApiPermissionRecord[]> {
  return apiGet<ApiPermissionRecord[]>("/api/v1/access/api-permissions", signal)
}

export async function createAccessUser(request: {
  username: string
  display_name: string
  password: string
  role_codes: string[]
  store_ids: number[]
  brand_ids: string[]
}): Promise<AccessUser> {
  return apiPost<AccessUser>("/api/v1/access/users", request)
}

export async function updateAccessUser(userId: number, request: {
  display_name: string
  role_codes: string[]
  store_ids: number[]
  brand_ids: string[]
}): Promise<AccessUser> {
  return apiRequest<AccessUser>(`/api/v1/access/users/${userId}`, {
    method: "PUT",
    body: JSON.stringify(request),
  })
}

export async function updateAccessUserStatus(userId: number, isActive: boolean): Promise<AccessUser> {
  return apiRequest<AccessUser>(`/api/v1/access/users/${userId}/status`, {
    method: "PATCH",
    body: JSON.stringify({ is_active: isActive }),
  })
}

export async function resetAccessUserPassword(userId: number, password: string): Promise<AccessUser> {
  return apiPost<AccessUser>(`/api/v1/access/users/${userId}/reset-password`, { password })
}
export async function fetchCollectionHealth(signal?: AbortSignal): Promise<BrowserHealth> {
  return apiGet<BrowserHealth>("/api/v1/imports/health", signal)
}

export async function startCollectionBrowser(): Promise<BrowserHealth> {
  return apiPost<BrowserHealth>("/api/v1/imports/browser/start", {})
}

export async function fetchCollectionSettings(): Promise<CollectionSettings> {
  return apiGet<CollectionSettings>("/api/v1/imports/settings")
}

export async function updateInventoryCredentials(request: UpdateInventoryCredentialsRequest): Promise<InventoryCredentialStatus> {
  return apiRequest<InventoryCredentialStatus>("/api/v1/imports/settings/inventory-credentials", {
    method: "PUT",
    body: JSON.stringify(request),
  })
}

export async function testInventoryCredentials(): Promise<InventoryCredentialTestResponse> {
  return apiPost<InventoryCredentialTestResponse>("/api/v1/imports/settings/inventory-credentials/test", {})
}

export async function fetchCollectionOverview(day?: string): Promise<CollectionOverview> {
  const suffix = day ? `?day=${encodeURIComponent(day)}` : ""
  return apiGet<CollectionOverview>(`/api/v1/imports/overview${suffix}`)
}

export async function fetchCollectionBatches(limit = 20): Promise<CollectionBatch[]> {
  return apiGet<CollectionBatch[]>(`/api/v1/imports/batches?limit=${limit}`)
}

export async function startDailyCollection(request: {
  day?: string
  datasetNames?: string[]
  sessionSource?: string
  refreshExisting?: boolean
  resumeFromLatest?: boolean
}): Promise<CollectionBatch> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 30_000)
  try {
    return await apiPost<CollectionBatch>("/api/v1/imports/collect", {
      day: request.day,
      dataset_names: request.datasetNames ?? [],
      session_source: request.sessionSource ?? "drissionpage",
      refresh_existing: request.refreshExisting ?? false,
      resume_from_latest: request.resumeFromLatest ?? true,
    }, controller.signal)
  } catch (error) {
    if (error && typeof error === "object" && "name" in error && error.name === "AbortError") {
      throw new Error("采集启动超过 30 秒仍未返回，请检查采集浏览器页面和网络后重试。")
    }
    throw error
  } finally {
    window.clearTimeout(timeout)
  }
}

export async function updateCollectionSchedule(request: {
  enabled: boolean
  runTime: string
  datasetNames: string[]
  sessionSource: string
}): Promise<CollectionSchedule> {
  return apiPost<CollectionSchedule>("/api/v1/imports/schedule", {
    enabled: request.enabled,
    run_time: request.runTime,
    dataset_names: request.datasetNames,
    session_source: request.sessionSource,
  })
}

export async function fetchReviewSummary(): Promise<ReviewCollectionSummary> {
  return apiGet<ReviewCollectionSummary>("/api/v1/reviews/summary")
}

export async function fetchReviewProducts(): Promise<Array<{ item_id: string; item_name: string | null; series: string | null; review_count: number }>> {
  return apiGet("/api/v1/reviews/products")
}

export async function fetchReviewSeries(): Promise<Array<{ series: string; review_count: number; product_count: number }>> {
  return apiGet("/api/v1/reviews/series")
}

export async function fetchReviewAnalysis(options: { productId?: string; series?: string; sentiment?: "positive" | "neutral" | "negative" | "unknown"; startDate?: string; endDate?: string } = {}): Promise<ReviewAnalysis> {
  const params = new URLSearchParams()
  if (options.productId) params.set("product_id", options.productId)
  if (options.series) params.set("series", options.series)
  if (options.sentiment) params.set("sentiment", options.sentiment)
  if (options.startDate) params.set("start_date", options.startDate)
  if (options.endDate) params.set("end_date", options.endDate)
  return apiGet<ReviewAnalysis>(`/api/v1/reviews/analysis?${params.toString()}`)
}

export async function fetchReviews(options: { productId?: string; series?: string; category?: string; sentiment?: "positive" | "neutral" | "negative" | "unknown"; search?: string; startDate?: string; endDate?: string; page?: number; pageSize?: number } = {}): Promise<ReviewListResponse> {
  const params = new URLSearchParams()
  if (options.productId) params.set("product_id", options.productId)
  if (options.series) params.set("series", options.series)
  if (options.category) params.set("category", options.category)
  if (options.sentiment) params.set("sentiment", options.sentiment)
  if (options.search) params.set("search", options.search)
  if (options.startDate) params.set("start_date", options.startDate)
  if (options.endDate) params.set("end_date", options.endDate)
  if (options.page) params.set("page", String(options.page))
  if (options.pageSize) params.set("page_size", String(options.pageSize))
  return apiGet<ReviewListResponse>(`/api/v1/reviews?${params.toString()}`)
}

export async function fetchReviewRuns(limit = 20): Promise<ReviewCollectionRun[]> {
  return apiGet<ReviewCollectionRun[]>(`/api/v1/reviews/runs?limit=${limit}`)
}

export async function collectReviews(mode: "initial" | "incremental" = "incremental", maxPages = 1000): Promise<ReviewCollectionRun> {
  return apiPost<ReviewCollectionRun>("/api/v1/reviews/collect", { mode, max_pages: maxPages, start_date: "2025-01-01" })
}

export async function fetchAskRuns(limit = 20): Promise<ReviewCollectionRun[]> {
  return apiGet<ReviewCollectionRun[]>(`/api/v1/reviews/asks/runs?limit=${limit}`)
}

export async function collectAsks(mode: "initial" | "incremental" = "incremental", maxPages = 500): Promise<ReviewCollectionRun> {
  return apiPost<ReviewCollectionRun>("/api/v1/reviews/asks/collect", { mode, max_pages: maxPages })
}

export async function fetchAskSummary(): Promise<AskSummary> {
  return apiGet<AskSummary>("/api/v1/reviews/asks/summary")
}

export async function fetchAsks(options: { productId?: string; series?: string; category?: string; search?: string; hasAnswer?: boolean; page?: number; pageSize?: number } = {}): Promise<AskListResponse> {
  const params = new URLSearchParams()
  if (options.productId) params.set("product_id", options.productId)
  if (options.series) params.set("series", options.series)
  if (options.category) params.set("category", options.category)
  if (options.search) params.set("search", options.search)
  if (options.hasAnswer !== undefined) params.set("has_answer", String(options.hasAnswer))
  if (options.page) params.set("page", String(options.page))
  if (options.pageSize) params.set("page_size", String(options.pageSize))
  return apiGet<AskListResponse>(`/api/v1/reviews/asks?${params.toString()}`)
}

export async function fetchStoreDataCatalog(storeId: number): Promise<StoreDataCatalog> {
  return apiGet<StoreDataCatalog>("/api/v1/warehouse/store-data/datasets?store_id=" + storeId)
}

export async function fetchStoreDataPreview(options: {
  storeId: number
  dataset: string
  startDate?: string
  endDate?: string
  page?: number
  pageSize?: number
  search?: string
}): Promise<StoreDataPreview> {
  const params = new URLSearchParams({ store_id: String(options.storeId), dataset: options.dataset })
  if (options.startDate) params.set("start_date", options.startDate)
  if (options.endDate) params.set("end_date", options.endDate)
  if (options.page) params.set("page", String(options.page))
  if (options.pageSize) params.set("page_size", String(options.pageSize))
  if (options.search) params.set("search", options.search)
  return apiGet<StoreDataPreview>("/api/v1/warehouse/store-data/preview?" + params.toString())
}

export async function downloadStoreData(options: {
  storeId: number
  dataset: string
  format: "csv" | "xlsx"
  startDate?: string
  endDate?: string
  search?: string
}): Promise<{ blob: Blob; filename: string }> {
  const params = new URLSearchParams({
    store_id: String(options.storeId),
    dataset: options.dataset,
    format: options.format,
  })
  if (options.startDate) params.set("start_date", options.startDate)
  if (options.endDate) params.set("end_date", options.endDate)
  if (options.search) params.set("search", options.search)
  const response = await fetch(API_BASE_URL + "/api/v1/warehouse/store-data/export?" + params.toString(), {
    headers: { Accept: "application/octet-stream" },
    credentials: "include",
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail || "导出失败：" + response.status)
  }
  const disposition = response.headers.get("Content-Disposition") || ""
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  const fallback = disposition.match(/filename=([^;]+)/i)?.[1]?.replace(/^"|"$/g, "")
  return { blob: await response.blob(), filename: encoded ? decodeURIComponent(encoded) : fallback || "店铺数据." + options.format }
}
