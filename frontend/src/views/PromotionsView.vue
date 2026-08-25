<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import {
  Activity,
  ArrowDown,
  ArrowDownRight,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  ArrowUpRight,
  BadgeDollarSign,
  BarChart3,
  Boxes,
  CircleDollarSign,
  Clapperboard,
  Filter,
  Gauge,
  Hash,
  Layers3,
  Megaphone,
  MousePointerClick,
  PackageSearch,
  Radar,
  RefreshCw,
  Search,
  Target,
  Trophy,
  UsersRound,
} from "lucide-vue-next"

import BusinessChart from "@/components/BusinessChart.vue"
import EmptyState from "@/components/EmptyState.vue"
import { fetchPromotionWorkbench, fetchStores } from "@/api"
import type { PromotionDimensionMetric, PromotionWorkbenchResponse } from "@/types"
import { useDashboard } from "@/composables/useDashboard"
import { currency, number, ratio } from "@/lib/format"

type LayerKey = "campaigns" | "adgroups" | "audiences" | "keywords" | "items" | "contents"
type FocusKey = "all" | "risk" | "scale" | "new" | "traffic"
type SortKey = "spend" | "paid_amount" | "roi" | "clicks" | "new_buyers" | "cpa"
type RankKey = "paid" | "spend" | "roi"

interface DerivedMetric extends PromotionDimensionMetric {
  roi: number
  ctr: number
  cvr: number
  cpc: number
  cpa: number | null
  newShare: number | null
  spendShare: number
  paidShare: number
  action: "放量" | "稳投" | "降本" | "观察"
}

interface RankedPlan extends DerivedMetric {
  rank: number
  cumulativePaidShare: number
}

const { dashboard } = useDashboard()
const workbench = ref<PromotionWorkbenchResponse | null>(null)
const previousWorkbench = ref<PromotionWorkbenchResponse | null>(null)
const loading = ref(false)
const error = ref("")
const activeLayer = ref<LayerKey>("campaigns")
const activeScene = ref("all")
const focus = ref<FocusKey>("all")
const sortKey = ref<SortKey>("spend")
const sortDescending = ref(true)
const rankKey = ref<RankKey>("paid")
const search = ref("")
const minimumSpend = ref(0)
const page = ref(1)
const pageSize = ref(20)
const dailyPage = ref(1)
const dailyPageSize = ref(10)

const layerOptions = [
  { key: "campaigns" as const, label: "计划", icon: Megaphone },
  { key: "adgroups" as const, label: "单元", icon: Boxes },
  { key: "audiences" as const, label: "人群", icon: UsersRound },
  { key: "keywords" as const, label: "关键词", icon: Hash },
  { key: "items" as const, label: "商品", icon: PackageSearch },
  { key: "contents" as const, label: "内容", icon: Clapperboard },
]
const focusOptions = [
  { key: "all" as const, label: "全部对象" },
  { key: "risk" as const, label: "ROI < 1" },
  { key: "scale" as const, label: "可放量" },
  { key: "new" as const, label: "高新客" },
  { key: "traffic" as const, label: "高点击低转化" },
]

function safeDivide(numerator: number, denominator: number): number {
  return denominator ? numerator / denominator : 0
}

function percentageChange(current: number, previous: number | undefined): number | null {
  if (previous === undefined || previous === 0) return null
  return (current - previous) / Math.abs(previous) * 100
}

function changeLabel(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "暂无同周期"
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`
}

function changeClass(value: number | null): string {
  if (value === null || value === 0) return "neutral"
  return value > 0 ? "up" : "down"
}

function actionFor(roi: number): DerivedMetric["action"] {
  if (roi >= 4) return "放量"
  if (roi >= 2) return "稳投"
  if (roi < 1) return "降本"
  return "观察"
}

function actionClass(action: DerivedMetric["action"]): string {
  return `promotion-action-${action === "放量" ? "up" : action === "降本" ? "down" : action === "稳投" ? "steady" : "observe"}`
}

function actionLabel(action: DerivedMetric["action"]): string {
  if (action === "放量") return "高效"
  if (action === "稳投") return "稳定"
  if (action === "降本") return "低效"
  return "观察"
}

function derive(item: PromotionDimensionMetric): DerivedMetric {
  const totalSpend = workbench.value?.summary.spend ?? 0
  const totalPaid = workbench.value?.summary.paid_amount ?? 0
  const roi = safeDivide(item.paid_amount, item.spend)
  return {
    ...item,
    roi,
    ctr: safeDivide(item.clicks, item.impressions) * 100,
    cvr: safeDivide(item.buyers, item.clicks) * 100,
    cpc: safeDivide(item.spend, item.clicks),
    cpa: item.buyers ? item.spend / item.buyers : null,
    newShare: item.buyers && item.new_buyers ? item.new_buyers / item.buyers * 100 : null,
    spendShare: safeDivide(item.spend, totalSpend) * 100,
    paidShare: safeDivide(item.paid_amount, totalPaid) * 100,
    action: actionFor(roi),
  }
}

function compactNumber(value: number): string {
  return new Intl.NumberFormat("zh-CN", { notation: "compact", maximumFractionDigits: 1 }).format(value)
}

function getPreviousRange(start: string, end: string): { start: string; end: string } {
  const oneDay = 86_400_000
  const startTime = Date.parse(`${start}T00:00:00Z`)
  const endTime = Date.parse(`${end}T00:00:00Z`)
  const days = Math.round((endTime - startTime) / oneDay) + 1
  const previousEnd = new Date(startTime - oneDay)
  const previousStart = new Date(previousEnd.getTime() - (days - 1) * oneDay)
  return { start: previousStart.toISOString().slice(0, 10), end: previousEnd.toISOString().slice(0, 10) }
}

async function loadWorkbench(): Promise<void> {
  if (!dashboard.value) return
  loading.value = true
  error.value = ""
  try {
    const stores = await fetchStores()
    const storeId = stores[0]?.store_id
    workbench.value = await fetchPromotionWorkbench(dashboard.value.range_start, dashboard.value.range_end, storeId)
    const previous = getPreviousRange(dashboard.value.range_start, dashboard.value.range_end)
    try {
      previousWorkbench.value = await fetchPromotionWorkbench(previous.start, previous.end, storeId)
    } catch {
      previousWorkbench.value = null
    }
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : "推广分析暂不可用"
  } finally {
    loading.value = false
  }
}

onMounted(() => { void loadWorkbench() })
watch(() => [dashboard.value?.range_start, dashboard.value?.range_end], () => { void loadWorkbench() })

const summary = computed(() => workbench.value?.summary)
const previousSummary = computed(() => previousWorkbench.value?.summary)
const campaignMetrics = computed(() => (workbench.value?.campaigns ?? []).map(derive))
const sceneRows = computed(() => (workbench.value?.scenes ?? []).map(derive).sort((left, right) => right.spend - left.spend))
const riskPlans = computed(() => campaignMetrics.value.filter((item) => item.roi < 1).sort((left, right) => right.spend - left.spend))
const scalePlans = computed(() => campaignMetrics.value.filter((item) => item.roi >= 4 && item.spend >= 500).sort((left, right) => right.paid_amount - left.paid_amount))
const riskSpend = computed(() => riskPlans.value.reduce((sum, item) => sum + item.spend, 0))
const riskSpendShare = computed(() => safeDivide(riskSpend.value, summary.value?.spend ?? 0) * 100)

const rankedPlans = computed<RankedPlan[]>(() => {
  const sorted = campaignMetrics.value.slice().sort((left, right) => {
    if (rankKey.value === "spend") return right.spend - left.spend
    if (rankKey.value === "roi") return right.roi - left.roi
    return right.paid_amount - left.paid_amount
  })
  let cumulative = 0
  return sorted.map((item, index) => {
    cumulative += item.paidShare
    return { ...item, rank: index + 1, cumulativePaidShare: cumulative }
  })
})

const core80Count = computed(() => rankedPlans.value.filter((item) => item.cumulativePaidShare - item.paidShare < 80).length)
const core80Share = computed(() => rankedPlans.value.find((item) => item.rank === core80Count.value)?.cumulativePaidShare ?? 0)

const metricCards = computed(() => {
  if (!summary.value) return []
  const previous = previousSummary.value
  const feeRatio = dashboard.value?.summary.promotion_fee_ratio ?? 0
  const previousFeeRatio = dashboard.value?.comparison.paid_amount.previous
    ? safeDivide(previous?.spend ?? 0, dashboard.value.comparison.paid_amount.previous) * 100
    : undefined
  return [
    { label: "全量推广花费", value: currency(summary.value.spend), detail: `${number(summary.value.campaign_count)} 个计划 · ${number(workbench.value?.daily_metrics.length ?? 0)} 天`, change: percentageChange(summary.value.spend, previous?.spend), icon: CircleDollarSign, tone: "spend" },
    { label: "推广归因成交", value: currency(summary.value.paid_amount), detail: `${number(summary.value.orders)} 笔订单 · ${number(summary.value.buyers)} 位买家`, change: percentageChange(summary.value.paid_amount, previous?.paid_amount), icon: BarChart3, tone: "result" },
    { label: "推广 ROI", value: `${summary.value.roi.toFixed(2)}x`, detail: "归因成交 / 全量推广花费", change: percentageChange(summary.value.roi, previous?.roi), icon: Target, tone: "efficiency" },
    { label: "推广费比", value: ratio(feeRatio), detail: "全量推广花费 / 全店支付", change: percentageChange(feeRatio, previousFeeRatio), icon: Gauge, tone: "pressure" },
    { label: "点击率 CTR", value: ratio(summary.value.click_rate), detail: `${number(summary.value.clicks)} 点击 / ${number(summary.value.impressions)} 展现`, change: percentageChange(summary.value.click_rate, previous?.click_rate), icon: MousePointerClick, tone: "traffic" },
    { label: "平均点击成本", value: currency(summary.value.average_click_cost), detail: "花费 / 点击量", change: percentageChange(summary.value.average_click_cost, previous?.average_click_cost), icon: BadgeDollarSign, tone: "cost" },
    { label: "点击成交转化", value: ratio(summary.value.click_conversion_rate), detail: `获客成本 ${currency(summary.value.buyer_acquisition_cost)}`, change: percentageChange(summary.value.click_conversion_rate, previous?.click_conversion_rate), icon: Activity, tone: "conversion" },
    { label: "成交新客占比", value: ratio(summary.value.new_buyer_share), detail: `${number(summary.value.new_buyers)} 位新客 · ${number(summary.value.buyers)} 位买家`, change: percentageChange(summary.value.new_buyer_share, previous?.new_buyer_share), icon: UsersRound, tone: "new" },
  ]
})

const dailyResultOption = computed(() => {
  const rows = workbench.value?.daily_metrics ?? []
  return {
    color: ["#557ed6", "#2c9b70", "#d19435"],
    tooltip: { trigger: "axis", formatter: (params: Array<{ dataIndex: number }>) => {
      const row = rows[params[0]?.dataIndex ?? 0]
      if (!row) return ""
      return `${row.stat_date}<br/>花费 ${currency(row.spend)}<br/>归因成交 ${currency(row.paid_amount)}<br/>ROI ${safeDivide(row.paid_amount, row.spend).toFixed(2)}x<br/>成交买家 ${number(row.buyers)}`
    } },
    legend: { bottom: 0, data: ["推广花费", "归因成交", "ROI"], textStyle: { color: "#718179", fontSize: 10 } },
    grid: { left: 64, right: 56, top: 24, bottom: 48 },
    xAxis: { type: "category", data: rows.map((item) => item.stat_date.slice(5)), axisLabel: { color: "#84928a" } },
    yAxis: [
      { type: "value", axisLabel: { formatter: (value: number) => `¥${compactNumber(value)}` }, splitLine: { lineStyle: { color: "#edf2ef" } } },
      { type: "value", axisLabel: { formatter: (value: number) => `${value.toFixed(1)}x` }, splitLine: { show: false } },
    ],
    series: [
      { name: "推广花费", type: "bar", barMaxWidth: 18, data: rows.map((item) => item.spend) },
      { name: "归因成交", type: "line", smooth: true, symbol: "circle", symbolSize: 6, lineStyle: { width: 2.4 }, data: rows.map((item) => item.paid_amount) },
      { name: "ROI", type: "line", yAxisIndex: 1, smooth: true, symbol: "none", lineStyle: { width: 2, type: "dashed" }, data: rows.map((item) => safeDivide(item.paid_amount, item.spend)) },
    ],
  }
})

const dailyEfficiencyOption = computed(() => {
  const rows = workbench.value?.daily_metrics ?? []
  return {
    color: ["#4e79c7", "#26946a", "#8d6cba", "#d19435"],
    tooltip: { trigger: "axis", formatter: (params: Array<{ dataIndex: number }>) => {
      const row = rows[params[0]?.dataIndex ?? 0]
      if (!row) return ""
      return `${row.stat_date}<br/>CTR ${ratio(safeDivide(row.clicks, row.impressions) * 100)}<br/>点击成交 ${ratio(safeDivide(row.buyers, row.clicks) * 100)}<br/>新客占比 ${ratio(safeDivide(row.new_buyers, row.buyers) * 100)}<br/>获客成本 ${currency(safeDivide(row.spend, row.buyers))}`
    } },
    legend: { bottom: 0, data: ["CTR", "点击成交", "新客占比", "获客成本"], textStyle: { color: "#718179", fontSize: 10 } },
    grid: { left: 52, right: 58, top: 24, bottom: 48 },
    xAxis: { type: "category", data: rows.map((item) => item.stat_date.slice(5)), axisLabel: { color: "#84928a" } },
    yAxis: [
      { type: "value", axisLabel: { formatter: (value: number) => `${value}%` }, splitLine: { lineStyle: { color: "#edf2ef" } } },
      { type: "value", axisLabel: { formatter: (value: number) => `¥${value}` }, splitLine: { show: false } },
    ],
    series: [
      { name: "CTR", type: "line", smooth: true, symbol: "none", data: rows.map((item) => safeDivide(item.clicks, item.impressions) * 100) },
      { name: "点击成交", type: "line", smooth: true, symbol: "none", data: rows.map((item) => safeDivide(item.buyers, item.clicks) * 100) },
      { name: "新客占比", type: "line", smooth: true, symbol: "none", data: rows.map((item) => safeDivide(item.new_buyers, item.buyers) * 100) },
      { name: "获客成本", type: "bar", yAxisIndex: 1, barMaxWidth: 13, data: rows.map((item) => safeDivide(item.spend, item.buyers)) },
    ],
  }
})

const sceneMatrixOption = computed(() => {
  const rows = sceneRows.value
  const averageSpend = rows.length ? rows.reduce((sum, item) => sum + item.spend, 0) / rows.length : 0
  return {
    tooltip: { formatter: (params: { data: { name: string; value: number[] } }) => `${params.data.name}<br/>花费 ${currency(params.data.value[0])}<br/>ROI ${params.data.value[1].toFixed(2)}x<br/>归因成交 ${currency(params.data.value[2])}` },
    grid: { left: 66, right: 34, top: 34, bottom: 48 },
    xAxis: { type: "value", name: "花费", axisLabel: { formatter: (value: number) => `¥${compactNumber(value)}` }, splitLine: { lineStyle: { color: "#edf2ef" } } },
    yAxis: { type: "value", name: "ROI", axisLabel: { formatter: (value: number) => `${value.toFixed(1)}x` }, splitLine: { lineStyle: { color: "#edf2ef" } } },
    series: [{
      type: "scatter",
      data: rows.map((item) => ({ name: item.dimension_name, value: [item.spend, item.roi, item.paid_amount], itemStyle: { color: item.action === "放量" ? "#27956b" : item.action === "降本" ? "#c36555" : item.action === "稳投" ? "#5279c4" : "#d29a3e" } })),
      symbolSize: (value: number[]) => Math.max(24, Math.min(62, Math.sqrt(value[2] || 0) / 8)),
      label: { show: true, formatter: "{b}", position: "top", color: "#53655b", fontSize: 9 },
      markLine: { silent: true, symbol: "none", label: { color: "#87958e", fontSize: 8 }, lineStyle: { color: "#bcc8c1", type: "dashed" }, data: [{ xAxis: averageSpend, name: "场景均值" }, { yAxis: summary.value?.roi ?? 0, name: "整体 ROI" }] },
    }],
  }
})

const layerSource = computed<PromotionDimensionMetric[]>(() => workbench.value?.[activeLayer.value] ?? [])
const layerLabel = computed(() => layerOptions.find((item) => item.key === activeLayer.value)?.label ?? "对象")
const filteredItems = computed(() => {
  const query = search.value.trim().toLocaleLowerCase("zh-CN")
  const rows = layerSource.value
    .map(derive)
    .filter((item) => activeScene.value === "all" || item.scene_name === activeScene.value)
    .filter((item) => item.spend >= Math.max(0, minimumSpend.value || 0))
    .filter((item) => !query || [item.dimension_id, item.dimension_name, item.parent_id, item.parent_name, item.subject_id, item.subject_name, item.scene_name].some((value) => value.toLocaleLowerCase("zh-CN").includes(query)))
    .filter((item) => {
      if (focus.value === "risk") return item.roi < 1
      if (focus.value === "scale") return item.roi >= 4 && item.spend >= 100
      if (focus.value === "new") return item.newShare !== null && item.newShare >= 35
      if (focus.value === "traffic") return item.clicks >= 100 && item.cvr < 1
      return true
    })
  const value = (item: DerivedMetric) => {
    if (sortKey.value === "roi") return item.roi
    if (sortKey.value === "cpa") return item.cpa ?? -1
    return item[sortKey.value]
  }
  return rows.sort((left, right) => (value(right) - value(left)) * (sortDescending.value ? 1 : -1))
})

const totalPages = computed(() => Math.max(1, Math.ceil(filteredItems.value.length / pageSize.value)))
const pageItems = computed(() => filteredItems.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))
const pageStart = computed(() => filteredItems.value.length ? (page.value - 1) * pageSize.value + 1 : 0)
const pageEnd = computed(() => Math.min(page.value * pageSize.value, filteredItems.value.length))
const layerTotals = computed(() => filteredItems.value.reduce((totals, item) => ({ spend: totals.spend + item.spend, paid: totals.paid + item.paid_amount, clicks: totals.clicks + item.clicks, buyers: totals.buyers + item.buyers, newBuyers: totals.newBuyers + item.new_buyers }), { spend: 0, paid: 0, clicks: 0, buyers: 0, newBuyers: 0 }))

watch([activeLayer, activeScene, focus, sortKey, sortDescending, search, minimumSpend, pageSize], () => { page.value = 1 })
watch(totalPages, (value) => { if (page.value > value) page.value = value })

const dailyRows = computed(() => (workbench.value?.daily_metrics ?? []).slice().reverse().map((item) => ({ ...item, roi: safeDivide(item.paid_amount, item.spend), ctr: safeDivide(item.clicks, item.impressions) * 100, cvr: safeDivide(item.buyers, item.clicks) * 100, newShare: safeDivide(item.new_buyers, item.buyers) * 100, cpa: safeDivide(item.spend, item.buyers) })))
const dailyPageCount = computed(() => Math.max(1, Math.ceil(dailyRows.value.length / dailyPageSize.value)))
const pagedDailyRows = computed(() => dailyRows.value.slice((dailyPage.value - 1) * dailyPageSize.value, dailyPage.value * dailyPageSize.value))
const dailyPageStart = computed(() => dailyRows.value.length ? (dailyPage.value - 1) * dailyPageSize.value + 1 : 0)
const dailyPageEnd = computed(() => Math.min(dailyPage.value * dailyPageSize.value, dailyRows.value.length))
watch(dailyPageSize, () => { dailyPage.value = 1 })
watch(dailyPageCount, (value) => { if (dailyPage.value > value) dailyPage.value = value })
watch(() => [dashboard.value?.range_start, dashboard.value?.range_end], () => { dailyPage.value = 1 })

function inspectScene(sceneName: string): void {
  activeScene.value = sceneName
  activeLayer.value = "campaigns"
  focus.value = "all"
  search.value = ""
  requestAnimationFrame(() => document.querySelector(".promotion-workbench-drill")?.scrollIntoView({ behavior: "smooth", block: "start" }))
}

function inspectPlan(item: DerivedMetric): void {
  activeLayer.value = "campaigns"
  activeScene.value = "all"
  focus.value = "all"
  search.value = item.dimension_id
  requestAnimationFrame(() => document.querySelector(".promotion-workbench-drill")?.scrollIntoView({ behavior: "smooth", block: "start" }))
}
</script>

<template>
  <main v-if="dashboard && workbench && summary" class="promotion-workbench">
    <header class="business-page-heading promotion-heading">
      <div><h1>推广分析</h1><span>计划、单元、人群、关键词、商品与内容</span></div>
      <div class="promotion-heading-actions"><span class="data-definition-badge"><Radar :size="15" />6 层明细 · {{ number(workbench.daily_metrics.length) }} 天</span><button type="button" :disabled="loading" @click="loadWorkbench"><RefreshCw :size="14" :class="{ spinning: loading }" />刷新</button></div>
    </header>

    <section class="promotion-workbench-kpis" aria-label="推广核心指标">
      <article v-for="item in metricCards" :key="item.label" :class="`promotion-workbench-kpi kpi-${item.tone}`"><div><span>{{ item.label }}</span><component :is="item.icon" :size="16" /></div><strong>{{ item.value }}</strong><small>{{ item.detail }}</small><em :class="changeClass(item.change)"><ArrowUpRight v-if="item.change !== null && item.change > 0" :size="12" /><ArrowDownRight v-else-if="item.change !== null && item.change < 0" :size="12" />{{ changeLabel(item.change) }} 同周期</em></article>
    </section>

    <section class="promotion-workbench-decisions" aria-label="预算决策摘要">
      <article class="decision-primary"><span>核心成交计划</span><strong>{{ core80Count }} 个计划贡献 {{ core80Share.toFixed(1) }}% 归因成交</strong><small>按归因成交降序累计至 80%</small></article>
      <article class="decision-risk"><span>ROI 低于 1 的花费</span><strong>{{ currency(riskSpend) }}</strong><small>{{ riskPlans.length }} 个计划，占全量花费 {{ ratio(riskSpendShare) }}</small></article>
      <article class="decision-scale"><span>ROI ≥ 4 的计划</span><strong>{{ number(scalePlans.length) }} 个</strong><small>筛选条件：ROI ≥ 4 且花费 ≥ ¥500</small></article>
      <article class="decision-quality"><span>成交归因结构</span><strong>{{ ratio(safeDivide(summary.direct_paid_amount, summary.paid_amount) * 100) }} 直接成交</strong><small>直接 {{ currency(summary.direct_paid_amount) }} · 间接 {{ currency(summary.indirect_paid_amount) }}</small></article>
    </section>

    <section class="promotion-workbench-chart-grid">
      <article class="panel"><div class="panel-heading"><div><p>每日结果</p><h2>花费、归因成交与 ROI</h2></div><BarChart3 :size="18" /></div><BusinessChart v-if="workbench.daily_metrics.length" :option="dailyResultOption" ariaLabel="每日推广花费归因成交和ROI趋势" :height="330" /><EmptyState v-else title="暂无每日推广数据" detail="当前区间没有推广计划日数据。" /></article>
      <article class="panel"><div class="panel-heading"><div><p>每日效率</p><h2>流量、转化、新客与获客成本</h2></div><Activity :size="18" /></div><BusinessChart v-if="workbench.daily_metrics.length" :option="dailyEfficiencyOption" ariaLabel="每日推广点击转化新客和获客成本趋势" :height="330" /><EmptyState v-else title="暂无每日效率数据" detail="当前区间没有可计算的日效率数据。" /></article>
    </section>

    <section class="promotion-workbench-scene-grid">
      <article class="panel"><div class="panel-heading"><div><p>场景效率</p><h2>花费与 ROI</h2></div><Layers3 :size="18" /></div><BusinessChart v-if="sceneRows.length" :option="sceneMatrixOption" ariaLabel="推广场景花费与ROI效率矩阵" :height="350" /><EmptyState v-else title="暂无推广场景" detail="当前范围没有可用场景数据。" /></article>
      <article class="panel promotion-workbench-scene-panel"><div class="panel-heading"><div><p>场景明细</p><h2>预算与转化</h2></div><span class="panel-action">点击查看计划</span></div><div class="promotion-workbench-scene-table"><div class="promotion-scene-row promotion-scene-head"><span>场景</span><span>花费 / 占比</span><span>成交 / ROI</span><span>CTR / 转化</span><span>新客</span><span>效率分层</span></div><button v-for="item in sceneRows" :key="item.dimension_id" class="promotion-scene-row" type="button" @click="inspectScene(item.scene_name)"><strong><span>{{ item.dimension_name }}</span><small>{{ number(item.buyers) }} 买家 · CPA {{ item.cpa === null ? "--" : currency(item.cpa) }}</small></strong><span>{{ currency(item.spend) }}<small>{{ ratio(item.spendShare) }}</small></span><span>{{ currency(item.paid_amount) }}<small>{{ item.roi.toFixed(2) }}x</small></span><span>{{ ratio(item.ctr) }}<small>{{ ratio(item.cvr) }}</small></span><span>{{ item.newShare === null ? "--" : ratio(item.newShare) }}<small>{{ number(item.new_buyers) }} 人</small></span><em :class="actionClass(item.action)">{{ actionLabel(item.action) }}</em></button></div></article>
    </section>

    <section class="panel promotion-contribution-panel">
      <div class="panel-heading promotion-contribution-heading"><div><p>计划排名</p><h2>成交贡献与预算占比</h2></div><div class="promotion-rank-switch"><button :class="{ active: rankKey === 'paid' }" @click="rankKey = 'paid'">按成交贡献</button><button :class="{ active: rankKey === 'spend' }" @click="rankKey = 'spend'">按花费</button><button :class="{ active: rankKey === 'roi' }" @click="rankKey = 'roi'">按 ROI</button></div></div>
      <div class="promotion-contribution-summary"><Trophy :size="20" /><div><strong>前 {{ core80Count }} 个计划构成 80% 成交核心盘</strong><span>绿色为成交贡献，灰色为预算占比；点击任一计划可直接定位到下方明细。</span></div></div>
      <div class="promotion-contribution-list">
        <article v-for="item in rankedPlans.slice(0, 15)" :key="item.dimension_id" role="button" tabindex="0" @click="inspectPlan(item)" @keydown.enter="inspectPlan(item)" @keydown.space.prevent="inspectPlan(item)">
          <i :class="{ medal: item.rank <= 3 }">{{ String(item.rank).padStart(2, "0") }}</i>
          <div class="promotion-contribution-name"><strong>{{ item.dimension_name }}</strong><small>{{ item.scene_name }} · ID {{ item.dimension_id }}</small></div>
          <div class="promotion-contribution-bars"><div><span>成交贡献</span><b><i :style="{ width: `${Math.min(100, item.paidShare * 4)}%` }"></i></b><em>{{ ratio(item.paidShare) }}</em></div><div><span>预算占比</span><b class="spend-bar"><i :style="{ width: `${Math.min(100, item.spendShare * 4)}%` }"></i></b><em>{{ ratio(item.spendShare) }}</em></div></div>
          <div class="promotion-contribution-values"><span>花费<strong>{{ currency(item.spend) }}</strong></span><span>成交<strong>{{ currency(item.paid_amount) }}</strong></span><span>ROI<strong>{{ item.roi.toFixed(2) }}x</strong></span></div>
          <em :class="actionClass(item.action)">{{ actionLabel(item.action) }}</em>
        </article>
      </div>
      <p class="panel-footnote">展示前 15 个计划；核心盘、汇总、筛选与排序均使用全部 {{ number(rankedPlans.length) }} 个有花费计划。</p>
    </section>

    <section class="promotion-workbench-budget-grid">
      <article class="panel"><div class="panel-heading"><div><p>高效计划</p><h2>ROI ≥ 4</h2></div><ArrowUpRight :size="18" /></div><div v-if="scalePlans.length" class="promotion-workbench-action-list"><div v-for="(item, index) in scalePlans.slice(0, 6)" :key="item.dimension_id"><i>{{ String(index + 1).padStart(2, "0") }}</i><strong><span>{{ item.dimension_name }}</span><small>{{ item.scene_name }} · 花费 {{ currency(item.spend) }}</small></strong><div><b>{{ item.roi.toFixed(2) }}x</b><small>成交 {{ currency(item.paid_amount) }}</small></div></div></div><EmptyState v-else title="暂无高效计划" detail="当前没有 ROI ≥ 4 且花费 ≥ ¥500 的计划。" /><p class="panel-footnote">按归因成交降序，最多显示 6 个计划。</p></article>
      <article class="panel"><div class="panel-heading"><div><p>低效计划</p><h2>ROI 低于 1</h2></div><ArrowDownRight :size="18" /></div><div v-if="riskPlans.length" class="promotion-workbench-action-list action-list-risk"><div v-for="(item, index) in riskPlans.slice(0, 6)" :key="item.dimension_id"><i>{{ String(index + 1).padStart(2, "0") }}</i><strong><span>{{ item.dimension_name }}</span><small>{{ item.scene_name }} · 花费 {{ currency(item.spend) }}</small></strong><div><b>{{ item.roi.toFixed(2) }}x</b><small>成交 {{ currency(item.paid_amount) }}</small></div></div></div><EmptyState v-else title="暂无低效计划" detail="当前有花费计划的推广 ROI 均不低于 1。" /><p class="panel-footnote">按花费降序，最多显示 6 个计划。</p></article>
    </section>

    <section class="panel promotion-workbench-drill">
      <div class="panel-heading promotion-workbench-drill-heading"><div><p>层级明细</p><h2>推广对象明细</h2></div><div class="promotion-layer-tabs"><button v-for="option in layerOptions" :key="option.key" :class="{ active: activeLayer === option.key }" type="button" @click="activeLayer = option.key"><component :is="option.icon" :size="14" />{{ option.label }}</button></div></div>
      <div class="promotion-workbench-filters">
        <label class="promotion-workbench-search"><Search :size="15" /><input v-model="search" :placeholder="`搜索${layerLabel}名称、ID、上级计划或商品`" /></label>
        <label><span>推广场景</span><select v-model="activeScene"><option value="all">全部场景</option><option v-for="item in sceneRows" :key="item.dimension_id" :value="item.scene_name">{{ item.dimension_name }}</option></select></label>
        <label><span>最低花费</span><input v-model.number="minimumSpend" type="number" min="0" step="100" placeholder="0" /></label>
        <label><span>排序</span><select v-model="sortKey"><option value="spend">花费</option><option value="paid_amount">成交</option><option value="roi">ROI</option><option value="clicks">点击</option><option value="new_buyers">新客</option><option value="cpa">获客成本</option></select></label>
        <button class="promotion-sort-direction" type="button" @click="sortDescending = !sortDescending"><ArrowDown v-if="sortDescending" :size="14" /><ArrowUp v-else :size="14" />{{ sortDescending ? "降序" : "升序" }}</button>
      </div>
      <div class="promotion-workbench-focus"><button v-for="item in focusOptions" :key="item.key" :class="{ active: focus === item.key }" type="button" @click="focus = item.key"><Filter v-if="item.key !== 'all'" :size="12" />{{ item.label }}</button></div>
      <div class="promotion-workbench-layer-summary"><span>匹配 {{ number(filteredItems.length) }} 条</span><span>花费 {{ currency(layerTotals.spend) }}</span><span>成交 {{ currency(layerTotals.paid) }}</span><span>ROI {{ safeDivide(layerTotals.paid, layerTotals.spend).toFixed(2) }}x</span><span>点击 {{ number(layerTotals.clicks) }}</span><span>买家 {{ number(layerTotals.buyers) }}</span><span>新客 {{ number(layerTotals.newBuyers) }}</span></div>
      <div v-if="pageItems.length" class="promotion-workbench-drill-table"><div class="promotion-workbench-drill-row promotion-workbench-drill-head"><span>{{ layerLabel }} / 场景</span><span>上级 / 主体</span><span>展现</span><span>点击 / CTR</span><span>花费</span><span>归因成交</span><span>买家 / 转化</span><span>新客</span><span>ROI / CPA</span><span>效率分层</span></div><div v-for="item in pageItems" :key="`${item.dimension_id}-${item.parent_id}-${item.subject_id}`" class="promotion-workbench-drill-row"><strong><component :is="layerOptions.find((option) => option.key === activeLayer)?.icon" :size="15" /><span>{{ item.dimension_name }}<small>ID {{ item.dimension_id || "--" }} · {{ item.scene_name }}</small></span></strong><span class="promotion-workbench-parent"><b>{{ item.parent_name || item.subject_name || "--" }}</b><small>{{ item.subject_name && item.parent_name ? item.subject_name : item.parent_id || item.subject_id || "" }}</small></span><span>{{ number(item.impressions) }}</span><span>{{ number(item.clicks) }}<small>{{ ratio(item.ctr) }}</small></span><span>{{ currency(item.spend) }}<small>{{ ratio(item.spendShare) }} 全量占比</small></span><span>{{ currency(item.paid_amount) }}</span><span>{{ item.buyers ? number(item.buyers) : "--" }}<small>{{ item.clicks && item.buyers ? ratio(item.cvr) : "--" }}</small></span><span>{{ item.new_buyers ? number(item.new_buyers) : "--" }}<small>{{ item.newShare === null ? "--" : ratio(item.newShare) }}</small></span><span><b>{{ item.roi.toFixed(2) }}x</b><small>{{ item.cpa === null ? "CPA --" : `CPA ${currency(item.cpa)}` }}</small></span><em :class="actionClass(item.action)">{{ actionLabel(item.action) }}</em></div></div>
      <EmptyState v-else title="当前筛选没有推广对象" detail="可以清空搜索、切换场景或调整效率筛选。" :icon="Search" />
      <footer class="promotion-pagination"><div><span>显示 {{ number(pageStart) }}–{{ number(pageEnd) }} / {{ number(filteredItems.length) }} 条</span><label>每页<select v-model.number="pageSize"><option :value="20">20</option><option :value="50">50</option><option :value="100">100</option></select></label></div><div><button type="button" :disabled="page <= 1" @click="page -= 1"><ArrowLeft :size="14" />上一页</button><span>第 {{ page }} / {{ totalPages }} 页</span><button type="button" :disabled="page >= totalPages" @click="page += 1">下一页<ArrowRight :size="14" /></button></div></footer>
    </section>

    <section class="panel promotion-workbench-daily-panel"><div class="panel-heading"><div><p>推广日报</p><h2>每日投放数据</h2></div><span class="panel-action">{{ number(dailyRows.length) }} 个统计日</span></div><div class="promotion-workbench-daily-table"><div class="promotion-workbench-daily-row promotion-workbench-daily-head"><span>日期</span><span>花费</span><span>归因成交</span><span>ROI</span><span>展现</span><span>点击</span><span>CTR</span><span>买家</span><span>点击成交</span><span>新客</span><span>新客占比</span><span>获客成本</span></div><div v-for="item in pagedDailyRows" :key="item.stat_date" class="promotion-workbench-daily-row"><strong>{{ item.stat_date }}</strong><span>{{ currency(item.spend) }}</span><span>{{ currency(item.paid_amount) }}</span><span>{{ item.roi.toFixed(2) }}x</span><span>{{ number(item.impressions) }}</span><span>{{ number(item.clicks) }}</span><span>{{ ratio(item.ctr) }}</span><span>{{ number(item.buyers) }}</span><span>{{ ratio(item.cvr) }}</span><span>{{ number(item.new_buyers) }}</span><span>{{ ratio(item.newShare) }}</span><span>{{ currency(item.cpa) }}</span></div></div><footer class="daily-pagination"><div><span>显示 {{ number(dailyPageStart) }}–{{ number(dailyPageEnd) }} / {{ number(dailyRows.length) }} 天</span><label>每页<select v-model.number="dailyPageSize"><option :value="10">10</option><option :value="20">20</option><option :value="30">30</option></select></label></div><div><button type="button" :disabled="dailyPage <= 1" @click="dailyPage -= 1"><ArrowLeft :size="14" />上一页</button><span>第 {{ dailyPage }} / {{ dailyPageCount }} 页</span><button type="button" :disabled="dailyPage >= dailyPageCount" @click="dailyPage += 1">下一页<ArrowRight :size="14" /></button></div></footer></section>

    <section class="promotion-coverage-strip" aria-label="推广数据层覆盖"><div v-for="layer in workbench.coverage" :key="layer.key"><component :is="layerOptions.find((option) => option.key === layer.key)?.icon || Radar" :size="17" /><span>{{ layer.label }}</span><strong>{{ number(layer.entity_count) }}</strong><small>{{ number(layer.row_count) }} 行 · {{ layer.covered_days }} 天</small></div></section>
  </main>
  <section v-else-if="loading" class="loading-panel"><span>正在读取全量推广层级数据</span></section>
  <section v-else-if="error" class="error-panel"><strong>推广分析暂不可用</strong><p>{{ error }}</p><button type="button" @click="loadWorkbench">重试</button></section>
</template>

<style scoped>
.promotion-workbench { display: grid; gap: 16px; padding-bottom: 28px; }
.promotion-heading-actions { display: flex; align-items: center; gap: 8px; }
.promotion-heading-actions > button { display: inline-flex; min-height: 32px; align-items: center; gap: 5px; border: 1px solid #d5e3db; border-radius: 5px; padding: 0 10px; color: #39705a; background: #fff; font-size: 10px; }
.promotion-workbench-kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); overflow: hidden; border: 1px solid #dfe7e2; border-radius: 7px; background: #dfe7e2; gap: 1px; }
.promotion-workbench-kpi { position: relative; display: grid; min-width: 0; min-height: 142px; align-content: start; gap: 7px; padding: 15px 16px; background: #fff; }
.promotion-workbench-kpi::before { position: absolute; top: 0; right: 0; left: 0; height: 2px; background: #399a72; content: ""; }.promotion-workbench-kpi.kpi-pressure::before,.promotion-workbench-kpi.kpi-cost::before { background: #d39a3d; }.promotion-workbench-kpi.kpi-traffic::before,.promotion-workbench-kpi.kpi-result::before { background: #5a7fc8; }.promotion-workbench-kpi.kpi-new::before { background: #8068b3; }
.promotion-workbench-kpi > div { display: flex; align-items: center; justify-content: space-between; color: #74837b; font-size: 10px; }.promotion-workbench-kpi > div svg { color: #48866b; }
.promotion-workbench-kpi > strong { overflow: hidden; color: #283f33; font-size: 23px; line-height: 1.2; text-overflow: ellipsis; white-space: nowrap; }.promotion-workbench-kpi > small { min-height: 16px; color: #87958e; font-size: 9px; }.promotion-workbench-kpi > em { display: inline-flex; width: max-content; align-items: center; gap: 3px; border-radius: 9px; padding: 3px 6px; font-size: 9px; font-style: normal; }.promotion-workbench-kpi > em.up { color: #147451; background: #ecf8f1; }.promotion-workbench-kpi > em.down { color: #b45c4d; background: #fff1ee; }.promotion-workbench-kpi > em.neutral { color: #7b8981; background: #f1f4f2; }
.promotion-workbench-decisions { display: grid; grid-template-columns: 1.25fr repeat(3, minmax(0, .75fr)); overflow: hidden; border: 1px solid #dfe8e3; border-radius: 7px; background: #dfe8e3; gap: 1px; }.promotion-workbench-decisions article { display: grid; min-width: 0; min-height: 108px; align-content: center; gap: 6px; padding: 15px 17px; background: #fff; }.promotion-workbench-decisions article:first-child { border-left: 3px solid #238b64; }.promotion-workbench-decisions span { color: #7d8c84; font-size: 9px; }.promotion-workbench-decisions strong { color: #2d4639; font-size: 14px; line-height: 1.45; }.promotion-workbench-decisions small { color: #89978f; font-size: 9px; line-height: 1.55; }.promotion-workbench-decisions .decision-risk strong { color: #b06b32; }.promotion-workbench-decisions .decision-scale strong { color: #237a58; }
.promotion-workbench-chart-grid,.promotion-workbench-scene-grid,.promotion-workbench-budget-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }.promotion-workbench-chart-grid > .panel,.promotion-workbench-scene-grid > .panel,.promotion-workbench-budget-grid > .panel { min-width: 0; overflow: hidden; }
.promotion-workbench-scene-table { margin-top: 12px; overflow-x: auto; }.promotion-scene-row { display: grid; grid-template-columns: minmax(165px,1.5fr) minmax(110px,.9fr) minmax(110px,.9fr) minmax(90px,.7fr) minmax(80px,.65fr) 58px; min-width: 720px; min-height: 58px; align-items: center; gap: 12px; width: 100%; border: 0; border-bottom: 1px solid #edf2ef; padding: 0 8px; color: #687970; background: #fff; font-size: 9px; text-align: right; }.promotion-scene-row:not(.promotion-scene-head):hover { background: #f7fbf9; }.promotion-scene-row > :first-child { text-align: left; }.promotion-scene-row strong,.promotion-scene-row > span { display: grid; gap: 4px; }.promotion-scene-row strong span { color: #385044; font-size: 11px; }.promotion-scene-row small { color: #91a098; font-size: 8px; }.promotion-scene-head { min-height: 34px; color: #94a099; background: #f7faf8; }
.promotion-contribution-panel { overflow: hidden; }.promotion-contribution-heading { flex-wrap: wrap; }.promotion-rank-switch,.promotion-layer-tabs { display: flex; overflow: hidden; border: 1px solid #dce6e0; border-radius: 5px; }.promotion-rank-switch button,.promotion-layer-tabs button { display: inline-flex; min-height: 29px; align-items: center; justify-content: center; gap: 5px; border: 0; border-right: 1px solid #e3ebe6; padding: 0 10px; color: #6e7e75; background: #fff; font-size: 9px; }.promotion-rank-switch button:last-child,.promotion-layer-tabs button:last-child { border-right: 0; }.promotion-rank-switch button.active,.promotion-layer-tabs button.active { color: #fff; background: #16845b; }
.promotion-contribution-summary { display: flex; align-items: center; gap: 11px; margin-top: 12px; border: 1px solid #dce9e2; border-radius: 5px; padding: 11px 13px; color: #20825e; background: #f3faf6; }.promotion-contribution-summary div { display: grid; gap: 3px; }.promotion-contribution-summary strong { color: #315044; font-size: 11px; }.promotion-contribution-summary span { color: #809087; font-size: 9px; }
.promotion-contribution-list { display: grid; margin-top: 8px; }.promotion-contribution-list > article { display: grid; grid-template-columns: 32px minmax(170px,1.2fr) minmax(300px,1.8fr) minmax(260px,1.2fr) 58px; min-width: 940px; min-height: 70px; align-items: center; gap: 14px; border-bottom: 1px solid #edf2ef; cursor: pointer; }.promotion-contribution-list > article:hover { background: #f7fbf9; }.promotion-contribution-list > article:focus-visible { outline: 2px solid #68ad8d; outline-offset: -2px; }.promotion-contribution-list > article > i { color: #8b9b92; font-size: 10px; font-style: normal; font-weight: 700; }.promotion-contribution-list > article > i.medal { color: #bc7b1e; }.promotion-contribution-name { display: grid; min-width: 0; gap: 4px; }.promotion-contribution-name strong,.promotion-contribution-name small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.promotion-contribution-name strong { color: #365044; font-size: 11px; }.promotion-contribution-name small { color: #92a098; font-size: 8px; }
.promotion-contribution-bars { display: grid; gap: 7px; }.promotion-contribution-bars > div { display: grid; grid-template-columns: 52px minmax(0,1fr) 46px; align-items: center; gap: 8px; color: #84938b; font-size: 8px; }.promotion-contribution-bars b { display: block; height: 7px; overflow: hidden; border-radius: 5px; background: #edf2ef; }.promotion-contribution-bars b i { display: block; height: 100%; border-radius: inherit; background: #38a176; }.promotion-contribution-bars b.spend-bar i { background: #9aabbf; }.promotion-contribution-bars em { text-align: right; font-style: normal; }
.promotion-contribution-values { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 8px; }.promotion-contribution-values span { display: grid; gap: 3px; color: #91a098; font-size: 8px; }.promotion-contribution-values strong { color: #40574a; font-size: 10px; }
.promotion-workbench-action-list { display: grid; margin-top: 8px; }.promotion-workbench-action-list > div { display: grid; grid-template-columns: 28px minmax(0,1fr) auto; min-height: 62px; align-items: center; gap: 10px; border-bottom: 1px solid #edf2ef; }.promotion-workbench-action-list i { color: #83a093; font-size: 9px; font-style: normal; }.promotion-workbench-action-list > div > strong,.promotion-workbench-action-list > div > div { display: grid; gap: 4px; }.promotion-workbench-action-list span { color: #3a5145; font-size: 11px; }.promotion-workbench-action-list small { color: #91a098; font-size: 8px; }.promotion-workbench-action-list b { color: #16845b; font-size: 13px; text-align: right; }.action-list-risk b { color: #bd614e; }
.promotion-workbench-drill { overflow: hidden; scroll-margin-top: 20px; }.promotion-workbench-drill-heading { flex-wrap: wrap; }.promotion-workbench-filters { display: grid; grid-template-columns: minmax(260px,1fr) 155px 125px 125px auto; gap: 9px; margin-top: 13px; align-items: end; }.promotion-workbench-filters label { display: grid; min-width: 0; gap: 5px; }.promotion-workbench-filters label > span { color: #84938b; font-size: 8px; }.promotion-workbench-filters select,.promotion-workbench-filters input { width: 100%; min-width: 0; height: 32px; border: 1px solid #d8e3dd; border-radius: 4px; padding: 0 8px; color: #43564b; background: #fff; font-size: 9px; }.promotion-workbench-search { display: flex !important; height: 32px; align-items: center; gap: 7px !important; border: 1px solid #d8e3dd; border-radius: 4px; padding: 0 9px; color: #87968e; }.promotion-workbench-search input { height: 28px; border: 0; padding: 0; outline: 0; }.promotion-sort-direction { display: inline-flex; min-height: 32px; align-items: center; gap: 5px; border: 1px solid #d8e3dd; border-radius: 4px; padding: 0 9px; color: #61756a; background: #fff; font-size: 9px; }
.promotion-workbench-focus { display: flex; gap: 6px; margin-top: 9px; overflow-x: auto; }.promotion-workbench-focus button { display: inline-flex; min-height: 28px; flex: 0 0 auto; align-items: center; gap: 4px; border: 1px solid #dce6e0; border-radius: 12px; padding: 0 9px; color: #718178; background: #fff; font-size: 8px; }.promotion-workbench-focus button.active { border-color: #9fcdb7; color: #176f4e; background: #edf8f2; }
.promotion-workbench-layer-summary { display: flex; gap: 1px; margin-top: 10px; overflow-x: auto; background: #e4ece7; }.promotion-workbench-layer-summary span { min-width: 110px; flex: 1; padding: 9px 10px; color: #66796e; background: #f8fbf9; font-size: 8px; text-align: center; white-space: nowrap; }
.promotion-workbench-drill-table { margin-top: 11px; overflow-x: auto; border: 1px solid #e5ece8; border-radius: 5px; }.promotion-workbench-drill-row { display: grid; grid-template-columns: minmax(230px,1.7fr) minmax(190px,1.35fr) 85px 95px 115px 115px 100px 85px 100px 55px; min-width: 1190px; min-height: 60px; align-items: center; gap: 14px; border-bottom: 1px solid #edf2ef; padding: 0 13px; color: #66776e; font-size: 9px; font-variant-numeric: tabular-nums; text-align: right; }.promotion-workbench-drill-row:last-child { border-bottom: 0; }.promotion-workbench-drill-row > :first-child,.promotion-workbench-drill-row > :nth-child(2) { text-align: left; }.promotion-workbench-drill-row > strong { display: grid; grid-template-columns: 18px minmax(0,1fr); align-items: center; gap: 6px; min-width: 0; color: #3c5548; }.promotion-workbench-drill-row > strong > span,.promotion-workbench-parent { display: grid; min-width: 0; gap: 4px; }.promotion-workbench-drill-row small,.promotion-workbench-parent b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.promotion-workbench-drill-row small { display: block; color: #93a098; font-size: 8px; font-weight: 400; }.promotion-workbench-parent b { color: #5c7065; font-size: 9px; }.promotion-workbench-drill-head { position: sticky; top: 0; z-index: 1; min-height: 36px; color: #8b9991; background: #f7faf8; font-size: 8px; font-weight: 650; }
.promotion-pagination { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 12px; border-top: 1px solid #e8eeea; padding-top: 11px; color: #7b8b82; font-size: 9px; }.promotion-pagination > div { display: flex; align-items: center; gap: 8px; }.promotion-pagination label { display: flex; align-items: center; gap: 5px; }.promotion-pagination select { height: 28px; border: 1px solid #dce6e0; border-radius: 4px; background: #fff; font-size: 9px; }.promotion-pagination button { display: inline-flex; min-height: 29px; align-items: center; gap: 4px; border: 1px solid #dce6e0; border-radius: 4px; padding: 0 8px; color: #536b5e; background: #fff; font-size: 9px; }.promotion-pagination button:disabled { opacity: .45; }
.promotion-workbench-daily-panel { overflow: hidden; }.promotion-workbench-daily-table { margin-top: 11px; overflow-x: auto; }.promotion-workbench-daily-row { display: grid; grid-template-columns: 95px repeat(11, minmax(90px,1fr)); min-width: 1190px; min-height: 48px; align-items: center; gap: 10px; border-bottom: 1px solid #edf2ef; color: #66776e; font-size: 9px; text-align: right; }.promotion-workbench-daily-row > :first-child { text-align: left; }.promotion-workbench-daily-head { min-height: 32px; color: #91a098; background: #f8faf9; }
.promotion-coverage-strip > div { grid-template-columns: auto 1fr; align-items: center; }.promotion-coverage-strip > div svg { grid-row: span 3; color: #4b8b6d; }.promotion-coverage-strip > div strong,.promotion-coverage-strip > div small { grid-column: 2; }
@media (max-width: 1100px) { .promotion-workbench-kpis { grid-template-columns: repeat(2,minmax(0,1fr)); }.promotion-workbench-decisions { grid-template-columns: repeat(2,minmax(0,1fr)); }.promotion-workbench-chart-grid,.promotion-workbench-scene-grid,.promotion-workbench-budget-grid { grid-template-columns: 1fr; }.promotion-workbench-filters { grid-template-columns: minmax(250px,1fr) repeat(2,minmax(120px,.5fr)); }.promotion-sort-direction { min-width: 90px; }.promotion-contribution-list { overflow-x: auto; } }
@media (max-width: 680px) { .promotion-heading-actions { width: 100%; align-items: stretch; flex-direction: column; }.promotion-heading-actions > button { justify-content: center; }.promotion-workbench-kpis,.promotion-workbench-decisions { grid-template-columns: 1fr; }.promotion-workbench-kpi { min-height: 126px; }.promotion-rank-switch,.promotion-layer-tabs { width: 100%; overflow-x: auto; }.promotion-rank-switch button,.promotion-layer-tabs button { flex: 1; min-width: max-content; }.promotion-workbench-filters { grid-template-columns: 1fr 1fr; }.promotion-workbench-search { grid-column: 1 / -1; }.promotion-sort-direction { align-self: end; justify-content: center; }.promotion-pagination { align-items: stretch; flex-direction: column; }.promotion-pagination > div { justify-content: space-between; }.promotion-workbench-scene-panel,.promotion-contribution-panel { overflow: hidden; } }
</style>
