<script setup lang="ts">
import { computed, ref } from "vue"
import { ArrowLeft, ArrowRight, BarChart3, CircleDollarSign, Gauge, LoaderCircle, RefreshCw, Search, ShoppingBag, Timer, TrendingUp, UserPlus, Users, Zap } from "lucide-vue-next"

import BusinessChart from "@/components/BusinessChart.vue"
import EmptyState from "@/components/EmptyState.vue"
import MetricCard from "@/components/MetricCard.vue"
import { fetchFlashSaleAnalysis, fetchFlashSaleProductItems, fetchStores } from "@/api"
import { currency, number, ratio } from "@/lib/format"
import type { FlashSaleAnalysisResponse, FlashSaleDailyMetric, PromotionProductMetric } from "@/types"

const analysis = ref<FlashSaleAnalysisResponse | null>(null)
const loading = ref(false)
const error = ref("")
const selectedStoreId = ref<number | null>(null)
const flashSaleItems = ref<PromotionProductMetric[]>([])
const flashSaleItemsLoading = ref(false)
const flashSaleItemsError = ref("")
const flashSaleSearch = ref("")
const flashSaleSort = ref<"paid_amount" | "paid_order_count" | "visitors">("paid_amount")
const flashSalePage = ref(1)
const flashSalePageSize = ref(50)
const dailyPage = ref(1)
const dailyPageSize = ref(10)

async function loadFlashSaleItems(response: FlashSaleAnalysisResponse | null = analysis.value): Promise<void> {
  if (!response || !selectedStoreId.value) return
  flashSaleItemsLoading.value = true
  flashSaleItemsError.value = ""
  try {
    const rows: PromotionProductMetric[] = []
    let page = 1
    while (true) {
      const payload = await fetchFlashSaleProductItems(
        response.range_start,
        response.range_end,
        selectedStoreId.value,
        undefined,
        page,
        100,
        "paid_amount",
      )
      rows.push(...payload.items)
      if (rows.length >= payload.total || payload.items.length < payload.page_size) break
      page += 1
    }
    flashSaleItems.value = rows
    flashSalePage.value = 1
  } catch (requestError) {
    flashSaleItems.value = []
    flashSaleItemsError.value = requestError instanceof Error ? requestError.message : "秒杀商品明细读取失败"
  } finally {
    flashSaleItemsLoading.value = false
  }
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ""
  try {
    const store = (await fetchStores())[0]
    selectedStoreId.value = store?.store_id ?? null
    const response = store ? await fetchFlashSaleAnalysis(undefined, undefined, store.store_id) : null
    analysis.value = response
    dailyPage.value = 1
    await loadFlashSaleItems(response)
  } catch (requestError) {
    analysis.value = null
    error.value = requestError instanceof Error ? requestError.message : "淘宝秒杀分析暂不可用"
  } finally {
    loading.value = false
  }
}
void load()

const summary = computed(() => analysis.value?.summary)
const daily = computed(() => analysis.value?.daily_metrics ?? [])
const orderedDaily = computed(() => [...daily.value].reverse())
const dailyPageCount = computed(() => Math.max(1, Math.ceil(orderedDaily.value.length / dailyPageSize.value)))
const pagedDaily = computed(() => orderedDaily.value.slice((dailyPage.value - 1) * dailyPageSize.value, dailyPage.value * dailyPageSize.value))
const dailyPageStart = computed(() => orderedDaily.value.length ? (dailyPage.value - 1) * dailyPageSize.value + 1 : 0)
const dailyPageEnd = computed(() => Math.min(dailyPage.value * dailyPageSize.value, orderedDaily.value.length))
const completeDaily = computed(() => daily.value.filter((item) => item.record_status === "complete"))
const emptyDaily = computed(() => daily.value.filter((item) => item.record_status === "empty"))
const missingDaily = computed(() => daily.value.filter((item) => item.record_status === "missing"))
const burstPeak = computed(() => completeDaily.value.reduce<FlashSaleDailyMetric | null>((peak, item) => !peak || (item.burst_coefficient || 0) > (peak.burst_coefficient || 0) ? item : peak, null))
const newCustomerRate = computed(() => summary.value?.paid_order_count ? (summary.value.new_customers / summary.value.paid_order_count) * 100 : 0)
const searchedFlashSaleItems = computed(() => {
  const term = flashSaleSearch.value.trim().toLowerCase()
  const rows = term
    ? flashSaleItems.value.filter((item) => `${item.product_id} ${item.product_name} ${item.activity_id} ${item.activity_name}`.toLowerCase().includes(term))
    : flashSaleItems.value
  return [...rows].sort((left, right) => (Number(right[flashSaleSort.value] ?? 0) - Number(left[flashSaleSort.value] ?? 0)) || left.product_id.localeCompare(right.product_id))
})
const flashSalePageCount = computed(() => Math.max(1, Math.ceil(searchedFlashSaleItems.value.length / flashSalePageSize.value)))
const pagedFlashSaleItems = computed(() => searchedFlashSaleItems.value.slice((flashSalePage.value - 1) * flashSalePageSize.value, flashSalePage.value * flashSalePageSize.value))
const flashSaleAmountTotal = computed(() => flashSaleItems.value.reduce((total, item) => total + (item.paid_amount ?? 0), 0))
const flashSaleReconcileRate = computed(() => summary.value?.paid_amount ? flashSaleAmountTotal.value / summary.value.paid_amount * 100 : null)
const flashSaleActivities = computed(() => {
  const grouped = new Map<string, { label: string; amount: number }>()
  for (const item of flashSaleItems.value) {
    const id = item.activity_id || "无活动 ID"
    const key = `${id}|${item.activity_name}`
    const current = grouped.get(key)
    grouped.set(key, {
      label: item.activity_name ? `${item.activity_name} · ${id}` : id,
      amount: (current?.amount ?? 0) + (item.paid_amount ?? 0),
    })
  }
  return [...grouped.values()]
    .map((item) => ({ ...item, share: flashSaleAmountTotal.value ? item.amount / flashSaleAmountTotal.value * 100 : 0 }))
    .sort((left, right) => right.amount - left.amount)
    .slice(0, 8)
})

function changeFlashSalePage(page: number): void {
  flashSalePage.value = Math.min(Math.max(page, 1), flashSalePageCount.value)
}
function changeFlashSalePageSize(): void { flashSalePage.value = 1 }
function changeDailyPage(page: number): void {
  dailyPage.value = Math.min(Math.max(page, 1), dailyPageCount.value)
}
function changeDailyPageSize(): void { dailyPage.value = 1 }
function flashSaleMetric(valueToFormat: number | null): string { return valueToFormat === null ? "暂无" : number(valueToFormat) }
function flashSaleMoney(valueToFormat: number | null): string { return valueToFormat === null ? "暂无" : currency(valueToFormat) }

function changeText(value: number | null | undefined): string {
  if (value === null || value === undefined) return "暂无同期基准"
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`
}
function changeClass(value: number | null | undefined): string {
  return value === null || value === undefined ? "neutral" : value >= 0 ? "positive" : "negative"
}
function dayLabel(value: string): string { return value.slice(5) }
function dailyMoney(value: number | null): string { return value === null ? "暂无" : currency(value) }
function dailyNumber(value: number | null): string { return value === null ? "暂无" : number(value) }
function decimalNumber(value: number): string {
  return new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value)
}
function statusLabel(item: FlashSaleDailyMetric): string {
  return item.record_status === "complete" ? "有秒杀指标" : item.record_status === "empty" ? "接口返回空" : "未采集"
}

const trendOption = computed(() => ({
  color: ["#16845b", "#5b8def", "#e2a447"],
  tooltip: { trigger: "axis", formatter: (params: Array<{ dataIndex: number }>) => { const row = daily.value[params[0]?.dataIndex ?? 0]; if (!row) return ""; return `${row.stat_date}<br/>秒杀成交金额：${dailyMoney(row.paid_amount)}<br/>活动商品 IPVUV：${dailyNumber(row.ipv_uv)}<br/>成交笔数：${dailyNumber(row.paid_order_count)}<br/>爆发系数：${row.burst_coefficient === null ? "暂无" : row.burst_coefficient.toFixed(2)}<br/>状态：${statusLabel(row)}` } },
  legend: { bottom: 0, data: ["秒杀成交金额", "活动商品 IPVUV", "成交笔数"] },
  grid: { left: 62, right: 58, top: 24, bottom: 58 },
  xAxis: { type: "category", data: daily.value.map((item) => dayLabel(item.stat_date)) },
  yAxis: [{ type: "value", axisLabel: { formatter: "¥{value}" }, splitLine: { lineStyle: { color: "#edf1ef" } } }, { type: "value", axisLabel: { formatter: "{value}" }, splitLine: { show: false } }],
  series: [
    { name: "秒杀成交金额", type: "bar", barMaxWidth: 24, data: daily.value.map((item) => item.paid_amount) },
    { name: "活动商品 IPVUV", type: "line", yAxisIndex: 1, smooth: true, data: daily.value.map((item) => item.ipv_uv) },
    { name: "成交笔数", type: "line", yAxisIndex: 1, smooth: true, data: daily.value.map((item) => item.paid_order_count), lineStyle: { type: "dashed" } },
  ],
}))

const funnelOption = computed(() => ({
  color: ["#5b8def", "#35a979", "#e2a447", "#cf7660"],
  tooltip: { trigger: "item", formatter: "{b}<br/>{c}" },
  series: [{
    type: "funnel",
    top: 18,
    bottom: 18,
    left: "8%",
    width: "84%",
    minSize: "18%",
    maxSize: "100%",
    gap: 3,
    label: { color: "#40564a", formatter: "{b}  {c}" },
    labelLine: { lineStyle: { color: "#b9c8c0" } },
    itemStyle: { borderColor: "#fff", borderWidth: 2 },
    data: [
      { name: "活动商品 IPV", value: summary.value?.ipv ?? 0 },
      { name: "活动商品 IPVUV", value: summary.value?.ipv_uv ?? 0 },
      { name: "活动商品成交笔数", value: summary.value?.paid_order_count ?? 0 },
      { name: "引导店铺新客", value: summary.value?.new_customers ?? 0 },
    ],
  }],
}))

const burstOption = computed(() => ({
  color: ["#d5a24d", "#5b8def"],
  tooltip: { trigger: "axis" },
  legend: { bottom: 0, data: ["活动商品量级", "爆发系数"] },
  grid: { left: 52, right: 52, top: 25, bottom: 54 },
  xAxis: { type: "category", data: daily.value.map((item) => dayLabel(item.stat_date)) },
  yAxis: [
    { type: "value", name: "爆发系数", splitLine: { lineStyle: { color: "#edf1ef" } } },
    { type: "value", name: "商品数", minInterval: 1, splitLine: { show: false } },
  ],
  series: [
    { name: "活动商品量级", type: "bar", yAxisIndex: 1, barMaxWidth: 20, data: daily.value.map((item) => item.item_count) },
    { name: "爆发系数", type: "line", smooth: true, symbolSize: 5, data: daily.value.map((item) => item.burst_coefficient) },
  ],
}))

const comparisonRows = computed(() => {
  const current = summary.value
  const previous = analysis.value?.previous_summary
  if (!current || !previous) return []
  return [
    { label: "日均秒杀成交金额", current: current.active_days ? current.paid_amount / current.active_days : 0, previous: previous.active_days ? previous.paid_amount / previous.active_days : 0, change: analysis.value?.comparison.paid_amount_change_percent, format: "money" },
    { label: "日均成交笔数", current: current.active_days ? current.paid_order_count / current.active_days : 0, previous: previous.active_days ? previous.paid_order_count / previous.active_days : 0, change: analysis.value?.comparison.paid_order_count_change_percent, format: "number" },
    { label: "日均 IPVUV", current: current.active_days ? current.ipv_uv / current.active_days : 0, previous: previous.active_days ? previous.ipv_uv / previous.active_days : 0, change: analysis.value?.comparison.ipv_uv_change_percent, format: "number" },
    { label: "日均引导新客", current: current.active_days ? current.new_customers / current.active_days : 0, previous: previous.active_days ? previous.new_customers / previous.active_days : 0, change: analysis.value?.comparison.new_customers_change_percent, format: "number" },
  ]
})
const comparisonOption = computed(() => {
  const changes = comparisonRows.value.map((item) => item.change ?? null)
  return {
    color: ["#35a979", "#cf7660"],
    tooltip: { trigger: "axis", valueFormatter: (value: number | null) => value === null ? "暂无同期基准" : `${value.toFixed(2)}%` },
    legend: { bottom: 0, data: ["提升", "下降"] },
    grid: { left: 112, right: 48, top: 20, bottom: 45 },
    xAxis: { type: "value", axisLabel: { formatter: "{value}%" }, splitLine: { lineStyle: { color: "#edf1ef" } } },
    yAxis: { type: "category", data: ["成交金额", "成交笔数", "IPVUV", "引导新客"] },
    series: [
      { name: "提升", type: "bar", stack: "change", barMaxWidth: 20, label: { show: true, position: "right", formatter: "{c}%" }, data: changes.map((value) => value !== null && value >= 0 ? Number(value.toFixed(2)) : null) },
      { name: "下降", type: "bar", stack: "change", barMaxWidth: 20, label: { show: true, position: "left", formatter: "{c}%" }, data: changes.map((value) => value !== null && value < 0 ? Number(value.toFixed(2)) : null) },
    ],
  }
})

function comparisonValue(value: number, format: string): string { return format === "money" ? currency(value) : decimalNumber(value) }
</script>

<template>
  <template v-if="analysis && summary">
    <section class="business-page-heading flash-sale-heading">
      <div><p>营销活动 / 淘宝秒杀</p><h1>淘宝秒杀</h1><span>观察秒杀活动商品规模、流量承接、成交效率、新客获取和爆发峰值。秒杀数据按独立日报口径统计，不与普通活动日历混为一体。</span></div>
      <div class="flash-sale-heading-meta"><span><Timer :size="14" />秒杀数据独立覆盖至 {{ analysis.latest_available_date || "暂无" }}</span><button type="button" class="icon-button" :disabled="loading" title="刷新淘宝秒杀数据" @click="load"><RefreshCw :size="15" :class="{ spinning: loading }" /></button></div>
    </section>

    <section v-if="emptyDaily.length || missingDaily.length" class="flash-sale-coverage-warning"><TrendingUp :size="17" /><div><strong>当前范围有 {{ completeDaily.length }} 天秒杀指标有效</strong><span v-if="emptyDaily.length">{{ emptyDaily.map((item) => dayLabel(item.stat_date)).join("、") }}：日报存在，但平台没有返回秒杀指标，不计入汇总。</span><span v-if="missingDaily.length">{{ missingDaily.map((item) => dayLabel(item.stat_date)).join("、") }}：没有采集到秒杀日报。</span></div></section>

    <section class="metrics-grid module-metrics flash-sale-metrics">
      <MetricCard label="秒杀成交金额" :value="currency(summary.paid_amount)" :detail="`${number(summary.paid_order_count)} 笔成交 · ${changeText(analysis.comparison.paid_amount_change_percent)} 日均变化`" :icon="CircleDollarSign" tone="teal" scope="有效日累计" />
      <MetricCard label="活动商品 IPVUV" :value="number(summary.ipv_uv)" :detail="`秒杀流量转化 ${ratio(summary.conversion_rate)}`" :icon="Users" tone="blue" scope="有效日累计" />
      <MetricCard label="引导店铺新客" :value="number(summary.new_customers)" :detail="`新客占秒杀成交 ${ratio(newCustomerRate)}`" :icon="UserPlus" tone="amber" scope="有效日累计" />
      <MetricCard label="商品量级峰值" :value="summary.item_count_peak === null ? '暂无' : number(summary.item_count_peak)" detail="单日活动中商品量级最高值" :icon="Gauge" tone="coral" scope="单日峰值" />
      <MetricCard label="最高爆发系数" :value="summary.burst_coefficient_peak === null ? '暂无' : summary.burst_coefficient_peak.toFixed(2)" :detail="burstPeak ? `${burstPeak.stat_date} 达到峰值` : '暂无有效峰值'" :icon="BarChart3" tone="blue" scope="单日峰值" />
    </section>

    <section class="decision-chart-grid flash-sale-chart-grid">
      <article class="panel"><div class="panel-heading"><div><p>秒杀趋势</p><h2>成交金额、流量与笔数</h2></div><TrendingUp :size="18" /></div><BusinessChart :option="trendOption" ariaLabel="淘宝秒杀成交金额流量与成交笔数趋势图" :height="350" /></article>
      <article class="panel"><div class="panel-heading"><div><p>转化链路</p><h2>流量、成交与新客漏斗</h2></div><Gauge :size="18" /></div><BusinessChart :option="funnelOption" ariaLabel="淘宝秒杀流量成交和新客漏斗图" :height="350" /></article>
      <article class="panel"><div class="panel-heading"><div><p>爆发复盘</p><h2>商品规模与爆发系数</h2></div><Zap :size="18" /></div><BusinessChart :option="burstOption" ariaLabel="淘宝秒杀商品规模与爆发系数趋势图" :height="320" /></article>
      <article class="panel"><div class="panel-heading"><div><p>同期变化</p><h2>日均核心指标变化率</h2></div><BarChart3 :size="18" /></div><BusinessChart :option="comparisonOption" ariaLabel="淘宝秒杀当前窗口对比前一窗口变化图" :height="320" /></article>
    </section>

    <section class="content-grid flash-sale-insight-grid">
      <article class="panel"><div class="panel-heading"><div><p>同期对照</p><h2>同长度窗口日均变化</h2></div><span class="panel-action">相同天数窗口</span></div><div class="flash-sale-comparison-table"><div class="flash-sale-comparison-row flash-sale-comparison-head"><span>指标</span><span>当前窗口</span><span>前一窗口</span><span>变化</span></div><div v-for="item in comparisonRows" :key="item.label" class="flash-sale-comparison-row"><strong>{{ item.label }}</strong><span>{{ comparisonValue(item.current, item.format) }}</span><span>{{ comparisonValue(item.previous, item.format) }}</span><em :class="changeClass(item.change)">{{ changeText(item.change) }}</em></div></div><p class="flash-sale-note">对照为相同天数的前一时间窗口；秒杀指标只在有有效返回的日期参与日均计算。</p></article>
      <article class="panel"><div class="panel-heading"><div><p>经营解读</p><h2>秒杀是否形成有效增量</h2></div><BarChart3 :size="18" /></div><div class="marketing-reading-list"><div><span>秒杀成交占店铺支付</span><strong>{{ summary.shop_paid_share === null ? '暂无' : ratio(summary.shop_paid_share) }}</strong><small>秒杀成交金额 / 店铺支付金额，仅作贡献观察</small></div><div><span>秒杀支付客单</span><strong>{{ currency(summary.customer_unit_price) }}</strong><small>秒杀成交金额 / 活动商品成交笔数</small></div><div><span>最高爆发日</span><strong>{{ burstPeak ? burstPeak.stat_date : '暂无' }}</strong><small>{{ burstPeak ? `爆发系数 ${burstPeak.burst_coefficient?.toFixed(2)}` : '没有有效爆发峰值' }}</small></div></div></article>
    </section>

    <section class="panel marketing-product-panel flash-sale-product-panel">
      <div class="panel-heading"><div><p>商品结构</p><h2>秒杀商品与活动贡献</h2></div><div class="marketing-product-heading-actions"><span class="panel-action">{{ flashSaleItems.length }} 个商品 / 活动组合</span><button type="button" class="icon-button" title="刷新秒杀商品明细" :disabled="flashSaleItemsLoading" @click="loadFlashSaleItems()"><RefreshCw :size="15" :class="{ spinning: flashSaleItemsLoading }" /></button></div></div>
      <div v-if="flashSaleItemsError" class="marketing-product-error">{{ flashSaleItemsError }}</div>
      <template v-else>
        <div class="marketing-product-summary"><div><span>商品明细成交金额</span><strong>{{ currency(flashSaleAmountTotal) }}</strong><small>当前区间按商品明细全量汇总</small></div><div><span>日报对账率</span><strong>{{ flashSaleReconcileRate === null ? '暂无' : `${flashSaleReconcileRate.toFixed(2)}%` }}</strong><small>商品明细金额 / 秒杀日报金额</small></div><div><span>有效组合数</span><strong>{{ number(flashSaleItems.length) }}</strong><small>按商品 ID 与活动 ID 聚合</small></div></div>
        <div v-if="flashSaleActivities.length" class="marketing-category-list flash-sale-activity-list"><div v-for="item in flashSaleActivities" :key="item.label" class="marketing-category-row"><div><span>{{ item.label }}</span><strong>{{ currency(item.amount) }}</strong></div><i><b :style="{ width: `${Math.min(item.share, 100)}%` }"></b></i><em>{{ item.share.toFixed(1) }}%</em></div></div>
        <div class="marketing-product-toolbar"><label><Search :size="14" /><input v-model="flashSaleSearch" type="search" placeholder="搜索商品 ID、名称、活动名称或活动 ID" @input="flashSalePage = 1" /></label><select v-model="flashSaleSort" aria-label="秒杀商品排序" @change="flashSalePage = 1"><option value="paid_amount">按成交金额</option><option value="paid_order_count">按成交笔数</option><option value="visitors">按 IPVUV</option></select><label class="marketing-product-page-size"><span>每页</span><select v-model.number="flashSalePageSize" @change="changeFlashSalePageSize"><option :value="20">20</option><option :value="50">50</option><option :value="100">100</option></select></label></div>
        <div v-if="flashSaleItemsLoading && !flashSaleItems.length" class="marketing-product-loading">正在读取秒杀商品明细</div>
        <div v-else-if="pagedFlashSaleItems.length" class="marketing-product-table-wrap"><table class="marketing-product-table flash-sale-product-table"><thead><tr><th>商品</th><th>活动</th><th>IPVUV</th><th>成交笔数</th><th>成交金额</th><th>引导新客</th><th>转化率</th><th>活动天数</th></tr></thead><tbody><tr v-for="item in pagedFlashSaleItems" :key="`${item.product_id}-${item.activity_id}`"><td><strong>{{ item.product_name || '未命名商品' }}</strong><small>{{ item.product_id }}</small></td><td><strong>{{ item.activity_name || '未命名活动' }}</strong><small>{{ item.activity_id || '无活动 ID' }}{{ item.activity_status ? ` · ${item.activity_status}` : '' }}</small></td><td>{{ flashSaleMetric(item.visitors) }}</td><td>{{ flashSaleMetric(item.paid_order_count) }}</td><td class="marketing-product-money">{{ flashSaleMoney(item.paid_amount) }}</td><td>{{ flashSaleMetric(item.new_customers) }}</td><td>{{ item.conversion_rate === null ? '暂无' : ratio(item.conversion_rate) }}</td><td>{{ item.active_days }}</td></tr></tbody></table></div><EmptyState v-else title="当前范围暂无秒杀商品" detail="平台在当前区间没有返回秒杀商品明细；已确认空响应不会视为采集失败。" :icon="ShoppingBag" />
        <div class="marketing-product-pagination"><span>显示 {{ searchedFlashSaleItems.length ? (flashSalePage - 1) * flashSalePageSize + 1 : 0 }}–{{ Math.min(flashSalePage * flashSalePageSize, searchedFlashSaleItems.length) }} / {{ number(searchedFlashSaleItems.length) }} 个组合</span><button type="button" class="icon-button" title="上一页" :disabled="flashSalePage <= 1" @click="changeFlashSalePage(flashSalePage - 1)"><ArrowLeft :size="14" /></button><span>第 {{ flashSalePage }} / {{ flashSalePageCount }} 页</span><button type="button" class="icon-button" title="下一页" :disabled="flashSalePage >= flashSalePageCount" @click="changeFlashSalePage(flashSalePage + 1)"><ArrowRight :size="14" /></button></div>
        <p class="flash-sale-note">活动金额占比使用当前区间全部商品明细作为分母。秒杀商品明细按业务日期每日批量采集并留存；接口确认无商品的日期保留为“无数据”，不按未采集处理。当前仍缺少券后价、库存、完整成本和时段明细，因此这里只展示归因贡献与成交效率，不计算利润或因果增量。</p>
      </template>
    </section>

    <section class="panel flash-sale-daily-panel"><div class="panel-heading"><div><p>日级复盘</p><h2>淘宝秒杀每日明细</h2></div><span class="panel-action">{{ daily.length }} 个统计日</span></div><div class="flash-sale-daily-table"><div class="flash-sale-daily-row flash-sale-daily-head"><span>日期</span><span>商品量级</span><span>IPV</span><span>IPVUV</span><span>成交笔数</span><span>成交金额</span><span>引导新客</span><span>爆发系数</span><span>状态</span></div><div v-for="item in pagedDaily" :key="item.stat_date" class="flash-sale-daily-row"><strong>{{ item.stat_date }}</strong><span>{{ dailyNumber(item.item_count) }}</span><span>{{ dailyNumber(item.ipv) }}</span><span>{{ dailyNumber(item.ipv_uv) }}</span><span>{{ dailyNumber(item.paid_order_count) }}</span><span>{{ dailyMoney(item.paid_amount) }}</span><span>{{ dailyNumber(item.new_customers) }}</span><span>{{ item.burst_coefficient === null ? '暂无' : item.burst_coefficient.toFixed(2) }}</span><em :class="`flash-sale-status-${item.record_status}`">{{ statusLabel(item) }}</em></div></div><footer class="daily-pagination"><div><span>显示 {{ number(dailyPageStart) }}–{{ number(dailyPageEnd) }} / {{ number(orderedDaily.length) }} 天</span><label>每页<select v-model.number="dailyPageSize" @change="changeDailyPageSize"><option :value="10">10</option><option :value="20">20</option><option :value="30">30</option></select></label></div><div><button type="button" :disabled="dailyPage <= 1" @click="changeDailyPage(dailyPage - 1)"><ArrowLeft :size="14" />上一页</button><span>第 {{ dailyPage }} / {{ dailyPageCount }} 页</span><button type="button" :disabled="dailyPage >= dailyPageCount" @click="changeDailyPage(dailyPage + 1)">下一页<ArrowRight :size="14" /></button></div></footer><p class="flash-sale-note">日报总览与按日商品明细分开核对：平台确认空响应表示当天没有秒杀商品，不代表采集失败；未采集日期不会按 0 参与汇总。</p></section>
  </template>
  <section v-else-if="loading" class="loading-panel"><LoaderCircle :size="26" class="spinning" /><span>正在读取淘宝秒杀分析</span></section>
  <section v-else-if="error" class="error-panel flash-sale-error"><strong>淘宝秒杀分析暂不可用</strong><p>{{ error }}</p><button type="button" @click="load">重试</button></section>
  <EmptyState v-else title="暂无淘宝秒杀数据" detail="当前店铺没有可展示的秒杀日报记录。" :icon="Timer" />
</template>
