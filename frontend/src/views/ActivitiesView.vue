<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue"
import {
  Activity as ActivityIcon,
  AlertTriangle,
  BarChart3,
  CalendarDays,
  CircleDollarSign,
  Eye,
  Layers3,
  LoaderCircle,
  Megaphone,
  PackageSearch,
  RefreshCw,
  ShoppingBag,
  Target,
  TrendingUp,
  Users,
} from "lucide-vue-next"

import BusinessChart from "@/components/BusinessChart.vue"
import EmptyState from "@/components/EmptyState.vue"
import MetricCard from "@/components/MetricCard.vue"
import { fetchActivityCalendar, fetchDashboard, fetchStores } from "@/api"
import { useDashboard } from "@/composables/useDashboard"
import { currency, number, ratio } from "@/lib/format"
import type { DashboardResponse, ProductMetric, StoreActivityCalendarEvent, TrafficMetric } from "@/types"

const { dashboard, loading } = useDashboard()
const activities = ref<StoreActivityCalendarEvent[]>([])
const activityLoading = ref(false)
const activityError = ref("")
const selectedActivityId = ref("")
const analysisLoading = ref(false)
const analysisError = ref("")
const windows = ref<WindowData | null>(null)
const stageMetric = ref<StageMetricKey>("paidAmount")
const activitySelector = ref<HTMLElement>()
let analysisRequestVersion = 0

type StageKey = "before" | "during" | "after"
type StageMetricKey = "paidAmount" | "visitors" | "conversionRate" | "customerUnitPrice" | "refundRate"
type SnapshotMetricKey = "paidAmount" | "visitors" | "buyers" | "conversionRate" | "customerUnitPrice" | "refundAmount" | "refundRate" | "allSiteSpend" | "planSpend" | "attributedPaidAmount" | "attributedRoi"

interface DateRange { start: string; end: string }
interface WindowData {
  before: DashboardResponse | null
  during: DashboardResponse | null
  after: DashboardResponse | null
  beforeRange: DateRange
  duringRange: DateRange
  afterRange: DateRange
  availableEnd: string
}
interface StageSnapshot {
  key: StageKey
  label: string
  range: DateRange
  data: DashboardResponse | null
  expectedDays: number
  coveredDays: number
  averagePaidAmount: number | null
  averageVisitors: number | null
  averageBuyers: number | null
  averagePromotionCost: number | null
  averagePlanSpend: number | null
  averageAttributedPaidAmount: number | null
  paidAmount: number | null
  visitors: number | null
  buyers: number | null
  conversionRate: number | null
  customerUnitPrice: number | null
  refundAmount: number | null
  refundRate: number | null
  allSiteSpend: number | null
  planSpend: number | null
  attributedPaidAmount: number | null
  attributedRoi: number | null
}
interface MetricDefinition { key: SnapshotMetricKey; label: string; format: "money" | "number" | "percent" | "roi" }

const stageDefinitions: Array<{ key: StageKey; label: string }> = [
  { key: "before", label: "活动前" }, { key: "during", label: "活动中" }, { key: "after", label: "活动后" },
]
const stageMetricDefinitions: Array<{ key: StageMetricKey; label: string }> = [
  { key: "paidAmount", label: "日均支付金额" }, { key: "visitors", label: "日均访客数" }, { key: "conversionRate", label: "支付转化率" }, { key: "customerUnitPrice", label: "支付客单价" }, { key: "refundRate", label: "金额退款率" },
]
const metricDefinitions: MetricDefinition[] = [
  { key: "paidAmount", label: "支付金额", format: "money" },
  { key: "visitors", label: "访客数", format: "number" },
  { key: "buyers", label: "支付买家数", format: "number" },
  { key: "conversionRate", label: "支付转化率", format: "percent" },
  { key: "customerUnitPrice", label: "支付客单价", format: "money" },
  { key: "refundAmount", label: "退款金额", format: "money" },
  { key: "refundRate", label: "金额退款率", format: "percent" },
  { key: "allSiteSpend", label: "全站推广场景花费", format: "money" },
  { key: "planSpend", label: "推广计划全场景花费", format: "money" },
  { key: "attributedPaidAmount", label: "推广计划 15 天归因成交", format: "money" },
  { key: "attributedRoi", label: "推广计划归因 ROI", format: "roi" },
]

const dateOnly = (value: string | undefined | null): string => (value || "").slice(0, 10)
const parseDate = (value: string): Date => new Date(`${value}T12:00:00`)

function addDays(value: string, amount: number): string {
  const date = parseDate(value)
  date.setDate(date.getDate() + amount)
  return date.toISOString().slice(0, 10)
}
function dayCount(start: string, end: string): number { return Math.max(1, Math.round((parseDate(end).getTime() - parseDate(start).getTime()) / 86400000) + 1) }
function displayDate(value: string): string { return value ? value.slice(5).replace("-", "月") + "日" : "暂无" }
function activityStart(item: StoreActivityCalendarEvent): string { return dateOnly(item.activity_start_time || item.business_day) }
function activityEnd(item: StoreActivityCalendarEvent): string { return dateOnly(item.activity_end_time || item.activity_start_time || item.business_day) }
function isOverlapping(left: StoreActivityCalendarEvent, right: StoreActivityCalendarEvent): boolean { return activityStart(left) <= activityEnd(right) && activityStart(right) <= activityEnd(left) }
function activityTimeStatus(item: StoreActivityCalendarEvent): string {
  const reference = dashboard.value?.range_end || new Date().toISOString().slice(0, 10)
  if (reference < activityStart(item)) return "未开始"
  if (reference > activityEnd(item)) return "已结束"
  return "进行中"
}
function clampEnd(range: DateRange, availableEnd: string): DateRange | null {
  if (range.start > availableEnd) return null
  return { start: range.start, end: range.end < availableEnd ? range.end : availableEnd }
}
function formatMetric(snapshot: StageSnapshot, metric: MetricDefinition): string {
  const value = snapshot[metric.key]
  if (value === null) return snapshot.key === "after" ? "尚未覆盖" : "暂无"
  if (metric.format === "money") return currency(value)
  if (metric.format === "number") return number(value)
  if (metric.format === "percent") return ratio(value)
  return `${value.toFixed(2)}x`
}

async function loadActivities(): Promise<void> {
  if (!dashboard.value) return
  activityLoading.value = true
  activityError.value = ""
  try {
    const store = (await fetchStores())[0]
    if (!store) { activities.value = []; return }
    const year = dashboard.value.range_start.slice(0, 4)
    activities.value = await fetchActivityCalendar(store.store_id, `${year}-01-01`, `${year}-12-31`)
    if (!selectedActivityId.value || !activities.value.some((item) => item.activity_id === selectedActivityId.value)) {
      const inRange = activities.value.filter((item) => activityStart(item) <= dashboard.value!.range_end && activityEnd(item) >= dashboard.value!.range_start)
      selectedActivityId.value = (inRange[inRange.length - 1] || activities.value[activities.value.length - 1])?.activity_id || ""
    }
  } catch (error) {
    activities.value = []
    activityError.value = error instanceof Error ? error.message : "活动日历暂不可用"
  } finally { activityLoading.value = false }
}

const selectedActivity = computed(() => activities.value.find((item) => item.activity_id === selectedActivityId.value) || null)
const rangeActivities = computed(() => activities.value.filter((item) => activityStart(item) <= (dashboard.value?.range_end || "") && activityEnd(item) >= (dashboard.value?.range_start || "")))
const activityDays = computed(() => new Set(activities.value.flatMap((activity) => {
  const days: string[] = []
  const start = parseDate(activityStart(activity)); const end = parseDate(activityEnd(activity))
  for (const cursor = new Date(start); cursor <= end; cursor.setDate(cursor.getDate() + 1)) days.push(cursor.toISOString().slice(0, 10))
  return days
})))
const dailyRows = computed(() => (dashboard.value?.daily_metrics ?? []).map((item) => ({ ...item, activity: activityDays.value.has(item.stat_date) })))
const activityRows = computed(() => dailyRows.value.filter((item) => item.activity))
const nonActivityRows = computed(() => dailyRows.value.filter((item) => !item.activity))
const average = (items: typeof dailyRows.value) => items.length ? items.reduce((total, item) => total + item.paid_amount, 0) / items.length : 0

const chartOption = computed(() => ({
  color: ["#35a979"],
  tooltip: { trigger: "axis", formatter: (params: Array<{ dataIndex: number; value: number }>) => { const row = dailyRows.value[params[0]?.dataIndex ?? 0]; return `${row?.stat_date || ""}<br/>支付金额 ${currency(Number(params[0]?.value ?? 0))}${row?.activity ? "<br/>活动覆盖日" : ""}` } },
  grid: { left: 62, right: 24, top: 24, bottom: 34 },
  xAxis: { type: "category", data: dailyRows.value.map((item) => item.stat_date.slice(5)) },
  yAxis: { type: "value", axisLabel: { formatter: "¥{value}" }, splitLine: { lineStyle: { color: "#edf1ef" } } },
  series: [{ type: "line", smooth: true, data: dailyRows.value.map((item) => ({ value: item.paid_amount, itemStyle: { color: item.activity ? "#e2a447" : "#35a979" }, symbolSize: item.activity ? 10 : 6 })), markArea: { itemStyle: { color: "rgba(226,164,71,.10)" }, data: rangeActivities.value.slice(0, 8).map((item) => { const start = activityStart(item) < (dashboard.value?.range_start || activityStart(item)) ? (dashboard.value?.range_start || activityStart(item)) : activityStart(item); const end = activityEnd(item) > (dashboard.value?.range_end || activityEnd(item)) ? (dashboard.value?.range_end || activityEnd(item)) : activityEnd(item); return [{ name: item.activity_name, xAxis: start.slice(5) }, { xAxis: end.slice(5) }] }) } }],
}))

async function fetchWindow(range: DateRange, storeId: number, availableEnd: string): Promise<DashboardResponse | null> {
  const effectiveRange = clampEnd(range, availableEnd)
  if (!effectiveRange) return null
  try {
    const data = await fetchDashboard(effectiveRange.start, effectiveRange.end, storeId)
    return data.daily_metrics.length ? data : null
  } catch { return null }
}
async function loadAnalysis(item: StoreActivityCalendarEvent | null): Promise<void> {
  const requestVersion = ++analysisRequestVersion
  if (!item || !dashboard.value) { windows.value = null; return }
  const availableEnd = dashboard.value.range_end
  const start = activityStart(item); const end = activityEnd(item); const duration = dayCount(start, end)
  const beforeRange = { start: addDays(start, -duration), end: addDays(start, -1) }
  const duringRange = { start, end }; const afterRange = { start: addDays(end, 1), end: addDays(end, duration) }
  const store = (await fetchStores())[0]
  if (!store || requestVersion !== analysisRequestVersion) return
  analysisLoading.value = true; analysisError.value = ""; windows.value = null
  const [before, during, after] = await Promise.all([fetchWindow(beforeRange, store.store_id, availableEnd), fetchWindow(duringRange, store.store_id, availableEnd), fetchWindow(afterRange, store.store_id, availableEnd)])
  if (requestVersion !== analysisRequestVersion) return
  windows.value = { before, during, after, beforeRange, duringRange: clampEnd(duringRange, availableEnd) || duringRange, afterRange: clampEnd(afterRange, availableEnd) || afterRange, availableEnd }
  if (!before && !during && !after) analysisError.value = "该活动暂无可用经营数据"
  analysisLoading.value = false
}

watch(() => [dashboard.value?.range_start, dashboard.value?.range_end], async () => { await loadActivities(); await loadAnalysis(selectedActivity.value) }, { immediate: true })
watch(selectedActivity, async (item) => {
  await nextTick()
  const target = activitySelector.value?.querySelector<HTMLElement>(".activity-selector-item.active")
  if (target && activitySelector.value) activitySelector.value.scrollTo({ left: target.offsetLeft - activitySelector.value.clientWidth / 2 + target.clientWidth / 2, behavior: "smooth" })
  void loadAnalysis(item)
})

const snapshots = computed<StageSnapshot[]>(() => stageDefinitions.map(({ key, label }) => {
  const data = windows.value?.[key] || null
  const range = windows.value?.[`${key}Range` as "beforeRange" | "duringRange" | "afterRange"] || { start: "", end: "" }
  const daily = data?.daily_metrics || []
  const expectedDays = range.start && range.end ? dayCount(range.start, range.end) : 0
  const coveredDays = daily.length
  const averageOf = (value: number): number | null => coveredDays ? value / coveredDays : null
  const refundAmount = data ? daily.reduce((total, item) => total + item.refund_amount, 0) : null
  const refundBase = data ? daily.reduce((total, item) => total + item.paid_amount, 0) : 0
  const planSpend = data ? data.promotion_plans.reduce((total, item) => total + item.spend, 0) : null
  const attributedPaidAmount = data ? data.promotion_plans.reduce((total, item) => total + (item.paid_amount || 0), 0) : null
  const paidAmount = data?.summary.paid_amount ?? null
  const visitors = data?.summary.visitors ?? null
  const buyers = data?.summary.buyers ?? null
  const promotionCost = data?.summary.promotion_cost ?? null
  return { key, label, range, data, expectedDays, coveredDays,
    averagePaidAmount: paidAmount === null ? null : averageOf(paidAmount),
    averageVisitors: visitors === null ? null : averageOf(visitors),
    averageBuyers: buyers === null ? null : averageOf(buyers),
    averagePromotionCost: promotionCost === null ? null : averageOf(promotionCost),
    averagePlanSpend: planSpend === null ? null : averageOf(planSpend),
    averageAttributedPaidAmount: attributedPaidAmount === null ? null : averageOf(attributedPaidAmount),
    paidAmount, visitors, buyers, conversionRate: data?.summary.conversion_rate ?? null,
    customerUnitPrice: data?.summary.customer_unit_price ?? null, refundAmount,
    refundRate: data ? (refundBase ? (refundAmount || 0) / refundBase * 100 : 0) : null,
    allSiteSpend: promotionCost, planSpend, attributedPaidAmount,
    attributedRoi: planSpend && attributedPaidAmount !== null ? attributedPaidAmount / planSpend : null }
}))

const selectedStageMetric = computed(() => stageMetricDefinitions.find((item) => item.key === stageMetric.value) || stageMetricDefinitions[0])
const stageMetricValue = (snapshot: StageSnapshot): number | null => {
  if (stageMetric.value === "paidAmount") return snapshot.averagePaidAmount
  if (stageMetric.value === "visitors") return snapshot.averageVisitors
  return snapshot[stageMetric.value]
}
const stageChartOption = computed(() => ({
  color: ["#9ba8a1", "#e2a447", "#35a979"],
  tooltip: { trigger: "axis", valueFormatter: (value: number) => stageMetric.value === "visitors" ? number(value) : stageMetric.value === "paidAmount" || stageMetric.value === "customerUnitPrice" ? currency(value) : ratio(value) },
  grid: { left: 62, right: 24, top: 28, bottom: 34 },
  xAxis: { type: "category", data: snapshots.value.map((item) => item.label) },
  yAxis: { type: "value", axisLabel: { formatter: (value: number) => stageMetric.value === "visitors" ? number(value) : stageMetric.value === "paidAmount" || stageMetric.value === "customerUnitPrice" ? `¥${value}` : `${value}%` }, splitLine: { lineStyle: { color: "#edf1ef" } } },
  series: [{ type: "bar", barMaxWidth: 58, data: snapshots.value.map((item) => stageMetricValue(item)) }],
}))

interface TimelineRow { date: string; stage: StageKey; paidAmount: number; visitors: number; buyers: number; conversionRate: number; customerUnitPrice: number; promotionCost: number }
const timelineRows = computed<TimelineRow[]>(() => {
  if (!windows.value) return []
  const list: TimelineRow[] = []
  for (const [key, data] of [["before", windows.value.before], ["during", windows.value.during], ["after", windows.value.after]] as Array<[StageKey, DashboardResponse | null]>) {
    for (const item of data?.daily_metrics || []) list.push({ date: item.stat_date, stage: key, paidAmount: item.paid_amount, visitors: item.visitors, buyers: item.buyers, conversionRate: item.conversion_rate, customerUnitPrice: item.buyers ? item.paid_amount / item.buyers : 0, promotionCost: item.promotion_cost })
  }
  return list.sort((left, right) => left.date.localeCompare(right.date))
})
const timelineOption = computed(() => ({
  color: ["#35a979", "#5b8def"],
  tooltip: { trigger: "axis", formatter: (params: Array<{ dataIndex: number }>) => { const row = timelineRows.value[params[0]?.dataIndex ?? 0]; return `${row?.date || ""}<br/>支付金额 ${currency(row?.paidAmount)}<br/>访客 ${number(row?.visitors)} · 买家 ${number(row?.buyers)}<br/>转化率 ${ratio(row?.conversionRate || 0)} · 客单价 ${currency(row?.customerUnitPrice)}<br/>全站推广场景花费 ${currency(row?.promotionCost)}` } },
  grid: { left: 62, right: 24, top: 28, bottom: 34 },
  xAxis: { type: "category", data: timelineRows.value.map((item) => item.date.slice(5)) },
  yAxis: [{ type: "value", axisLabel: { formatter: "¥{value}" }, splitLine: { lineStyle: { color: "#edf1ef" } } }, { type: "value", axisLabel: { formatter: "¥{value}" }, splitLine: { show: false } }],
  series: [{ name: "支付金额", type: "line", smooth: true, data: timelineRows.value.map((item) => item.paidAmount), markArea: { itemStyle: { color: "rgba(226,164,71,.12)" }, data: windows.value?.during ? [[{ xAxis: windows.value.duringRange.start.slice(5) }, { xAxis: windows.value.duringRange.end.slice(5) }]] : [] } }, { name: "全站推广场景花费", type: "bar", yAxisIndex: 1, barMaxWidth: 12, data: timelineRows.value.map((item) => item.promotionCost) }],
}))

const duringData = computed(() => windows.value?.during)
const duringSnapshot = computed(() => snapshots.value.find((item) => item.key === "during"))
const duringProducts = computed<ProductMetric[]>(() => (duringData.value?.top_products || []).slice(0, 10))
const beforeProducts = computed(() => new Map((windows.value?.before?.top_products || []).map((item) => [item.product_id, item])))
const afterProducts = computed(() => new Map((windows.value?.after?.top_products || []).map((item) => [item.product_id, item])))
const productConversion = (item: ProductMetric): number => item.visitors ? item.buyers / item.visitors * 100 : 0
const productShare = (item: ProductMetric): number => duringData.value?.summary.paid_amount ? item.paid_amount / duringData.value.summary.paid_amount * 100 : 0
function productChange(current: number, comparison: number | undefined): number | null { return comparison ? (current / comparison - 1) * 100 : null }
function productChangeLabel(value: number | null, unavailableLabel: string): string { return value === null ? unavailableLabel : `${value >= 0 ? "+" : ""}${value.toFixed(2)}%` }
const productDiagnostics = computed(() => {
  const data = duringData.value
  if (!data) return [] as Array<{ kind: string; title: string; detail: string }>
  const avgConversion = data.summary.conversion_rate
  const visitorMedian = [...data.top_products].sort((a, b) => a.visitors - b.visitors)[Math.floor(data.top_products.length / 2)]?.visitors || 0
  const rows: Array<{ kind: string; title: string; detail: string }> = []
  const trafficLowConversion = [...data.top_products].sort((a, b) => b.visitors - a.visitors).find((item) => productConversion(item) < avgConversion * 0.72)
  const conversionLowTraffic = [...data.top_products].sort((a, b) => productConversion(b) - productConversion(a)).find((item) => item.visitors < visitorMedian && productConversion(item) > avgConversion * 1.25)
  const newTop = data.top_products.find((item) => !beforeProducts.value.has(item.product_id))
  if (trafficLowConversion) rows.push({ kind: "warning", title: "高流量低转化", detail: `${trafficLowConversion.product_name} 访客 ${number(trafficLowConversion.visitors)}，转化 ${ratio(productConversion(trafficLowConversion))}，建议检查详情页与活动利益点。` })
  if (conversionLowTraffic) rows.push({ kind: "positive", title: "高转化待放量", detail: `${conversionLowTraffic.product_name} 转化 ${ratio(productConversion(conversionLowTraffic))}，但流量低于中位数，可评估增加精准投放。` })
  if (newTop) rows.push({ kind: "info", title: "活动新进入商品", detail: `${newTop.product_name} 在活动期进入 Top 商品，需结合库存与退款表现判断是否适合继续放大。` })
  return rows
})

const trafficSources = computed<TrafficMetric[]>(() => (duringData.value?.traffic_sources || []).slice(0, 12))
const trafficOption = computed(() => ({
  color: ["#5b8def", "#35a979", "#e2a447"],
  tooltip: { trigger: "item", formatter: (params: { data: [number, number, number, string] }) => `${params.data[3]}<br/>访客 ${number(params.data[0])}<br/>转化 ${ratio(params.data[1])}<br/>归因成交 ${currency(params.data[2])}` },
  grid: { left: 58, right: 24, top: 22, bottom: 42 },
  xAxis: { name: "访客数", type: "value", splitLine: { lineStyle: { color: "#edf1ef" } } },
  yAxis: { name: "转化率", type: "value", axisLabel: { formatter: "{value}%" }, splitLine: { lineStyle: { color: "#edf1ef" } } },
  series: [{ type: "scatter", symbolSize: (value: [number, number, number]) => Math.max(16, Math.min(52, Math.sqrt(Math.max(value[2], 0)) / 8)), data: trafficSources.value.map((item) => [item.visitors, item.conversion_rate, item.paid_amount, item.source_name]) }],
}))

const promotionChartOption = computed(() => ({
  color: ["#5b8def", "#35a979", "#e2a447"],
  tooltip: { trigger: "axis", formatter: (params: Array<{ seriesName: string; value: number | null }>) => params.map((item) => `${item.seriesName} ${item.seriesName === "归因 ROI" ? item.value === null ? "暂无" : `${Number(item.value).toFixed(2)}x` : currency(item.value)}`).join("<br/>") },
  legend: { bottom: 0, itemWidth: 9, itemHeight: 9, textStyle: { color: "#75857c", fontSize: 9 } },
  grid: { left: 52, right: 42, top: 20, bottom: 42 },
  xAxis: { type: "category", data: snapshots.value.map((item) => item.label) },
  yAxis: [{ type: "value", axisLabel: { formatter: (value: number) => `¥${Math.round(value / 10000)}万` }, splitLine: { lineStyle: { color: "#edf1ef" } } }, { type: "value", axisLabel: { formatter: "{value}x" }, splitLine: { show: false } }],
  series: [
    { name: "计划日均花费", type: "bar", barMaxWidth: 20, data: snapshots.value.map((item) => item.averagePlanSpend) },
    { name: "15 天归因日均成交", type: "bar", barMaxWidth: 20, data: snapshots.value.map((item) => item.averageAttributedPaidAmount) },
    { name: "归因 ROI", type: "line", yAxisIndex: 1, smooth: true, data: snapshots.value.map((item) => item.attributedRoi) },
  ],
}))

const overlapActivities = computed(() => selectedActivity.value ? activities.value.filter((item) => item.activity_id !== selectedActivity.value?.activity_id && isOverlapping(item, selectedActivity.value!)) : [])
const conclusion = computed(() => {
  const during = duringSnapshot.value; const before = snapshots.value.find((item) => item.key === "before")
  if (!during?.data) return "活动期暂无覆盖数据，当前只能保留活动排期，不能形成经营复盘结论。"
  const change = before?.averagePaidAmount ? (during.averagePaidAmount! / before.averagePaidAmount - 1) * 100 : null
  const conversionChange = before?.conversionRate !== null && before?.conversionRate !== undefined ? during.conversionRate! - before.conversionRate : null
  const product = duringProducts.value[0]
  const lines = [
    change === null ? "活动期间已有经营数据，但活动前窗口无可比覆盖。" : `按有效统计日归一后，活动期间日均支付金额${change >= 0 ? "较活动前提升" : "较活动前下降"} ${Math.abs(change).toFixed(2)}%，活动前有效 ${before?.coveredDays || 0} 天、活动中有效 ${during.coveredDays} 天；这是同期变化观察，不代表单一活动因果。`,
    conversionChange === null ? "支付转化率暂缺活动前可比数据。" : `支付转化率较活动前${conversionChange >= 0 ? "提升" : "下降"} ${Math.abs(conversionChange).toFixed(2)} 个百分点，活动期客单价 ${currency(during.customerUnitPrice)}。`,
    `全站推广场景花费为 ${currency(during.allSiteSpend)}；推广计划全场景花费为 ${currency(during.planSpend)}，推广计划归因成交 ${during.attributedPaidAmount === null ? "待归因" : currency(during.attributedPaidAmount)}，该成交按平台 15 天归因，不能直接视为活动即时产出。`,
    product ? `活动期成交主力为 ${product.series || "未分类系列"}，Top 商品贡献 ${productShare(product).toFixed(2)}% 支付金额。` : "活动期暂无商品明细。",
  ]
  if (during.refundRate !== null && during.refundRate > 25) lines.push(`活动期金额退款率 ${ratio(during.refundRate)}，售后风险偏高，建议结合活动价、预售/尾款和商品承诺排查。`)
  return lines.join("\n")
})
const hasAnyAnalysis = computed(() => snapshots.value.some((item) => item.data))
</script>

<template>
  <template v-if="dashboard">
    <section class="business-page-heading activity-page-heading">
      <div><p>营销活动 / 日历与复盘</p><h1>活动中心</h1><span>活动排期与活动前、中、后经营指标对比</span></div>
      <span class="data-definition-badge"><CalendarDays :size="13" /> 推广成交统一按平台 15 天归因</span>
    </section>

    <section class="metrics-grid module-metrics">
      <MetricCard label="活动数量" :value="number(activities.length)" detail="全年活动记录" :icon="CalendarDays" tone="blue" scope="区间记录" />
      <MetricCard label="活动覆盖日" :value="number(activityRows.length)" detail="当前筛选区间内" :icon="Layers3" tone="teal" scope="区间记录" />
      <MetricCard label="活动日均支付" :value="activityRows.length ? currency(average(activityRows)) : '无活动日'" detail="活动覆盖日简单日均" :icon="CircleDollarSign" tone="amber" scope="观察指标" />
      <MetricCard label="非活动日均支付" :value="nonActivityRows.length ? currency(average(nonActivityRows)) : '无对照日'" detail="仅供时间相关性对照" :icon="TrendingUp" tone="coral" scope="观察指标" />
    </section>

    <section class="panel activity-selector-panel">
      <div class="panel-heading"><div><p>活动日历入口</p><h2>选择活动开始复盘</h2></div><span class="panel-action">共 {{ activities.length }} 场</span></div>
      <section v-if="activityLoading" class="admin-loading-state"><LoaderCircle :size="22" class="spinning" /><span>正在读取活动日历</span></section>
      <div v-else-if="activities.length" ref="activitySelector" class="activity-selector-list">
        <button v-for="item in activities" :key="item.activity_id" type="button" class="activity-selector-item" :class="{ active: item.activity_id === selectedActivityId }" @click="selectedActivityId = item.activity_id">
          <span class="activity-selector-icon"><ActivityIcon :size="15" /></span>
          <span class="activity-selector-copy"><strong>{{ item.activity_name || '未命名活动' }}</strong><small>{{ displayDate(activityStart(item)) }} 至 {{ displayDate(activityEnd(item)) }} · {{ dayCount(activityStart(item), activityEnd(item)) }} 天</small></span>
          <span class="activity-selector-status">{{ activityTimeStatus(item) }}</span>
        </button>
      </div>
      <EmptyState v-else :title="activityError ? '活动日历读取失败' : '当前范围暂无活动'" :detail="activityError || '没有活动日历记录。'" :icon="CalendarDays" />
    </section>

    <section class="panel decision-wide-chart activity-overview-chart"><div class="panel-heading"><div><p>区间观察</p><h2>活动覆盖与每日支付金额</h2></div><span class="panel-action">橙色节点为活动覆盖日</span></div><BusinessChart :option="chartOption" ariaLabel="活动覆盖与支付金额时间轴" :height="340" /></section>

    <template v-if="selectedActivity">
      <section class="activity-analysis-header">
        <div><p>当前复盘活动</p><h2>{{ selectedActivity.activity_name }}</h2><span>{{ displayDate(activityStart(selectedActivity)) }} 至 {{ displayDate(activityEnd(selectedActivity)) }} · {{ dayCount(activityStart(selectedActivity), activityEnd(selectedActivity)) }} 天 · {{ activityTimeStatus(selectedActivity) }}</span></div>
        <div class="activity-analysis-meta"><span><CalendarDays :size="14" />复盘口径：活动日历活动默认纳入</span><span><Target :size="14" />活动类型：{{ selectedActivity.activity_type || "未标记" }}</span></div>
      </section>
      <div v-if="overlapActivities.length" class="activity-overlap-notice"><AlertTriangle :size="17" /><span>当前活动期间存在 {{ overlapActivities.length }} 个重叠活动，以下结果为经营表现对照，不代表单一活动因果。</span></div>
      <section v-if="analysisLoading" class="panel admin-loading-state activity-analysis-loading"><LoaderCircle :size="22" class="spinning" /><span>正在读取活动前、中、后窗口</span></section>
      <template v-else-if="hasAnyAnalysis && windows">
        <section class="activity-stage-grid">
          <article v-for="item in snapshots" :key="item.key" class="panel activity-stage-card" :class="`activity-stage-card-${item.key}`">
            <div class="activity-stage-card-top"><span>{{ item.label }}</span><strong>{{ item.data ? item.key === 'during' && item.range.end < activityEnd(selectedActivity) ? `${displayDate(item.range.start)} 至 ${displayDate(activityEnd(selectedActivity))}（数据覆盖至 ${displayDate(item.range.end)}）` : `${displayDate(item.range.start)} 至 ${displayDate(item.range.end)}` : item.key === 'after' ? '活动后数据尚未覆盖' : '暂无覆盖数据' }}</strong></div>
            <div class="activity-stage-primary">{{ item.paidAmount === null ? "暂无" : currency(item.paidAmount) }}</div><small>支付金额 · 日均 {{ item.averagePaidAmount === null ? "暂无" : currency(item.averagePaidAmount) }}</small>
            <div class="activity-stage-coverage">有效 {{ item.coveredDays }} / {{ item.expectedDays }} 天</div>
            <div class="activity-stage-mini-grid"><span><b>{{ item.visitors === null ? "暂无" : number(item.visitors) }}</b>访客</span><span><b>{{ item.buyers === null ? "暂无" : number(item.buyers) }}</b>买家</span><span><b>{{ item.conversionRate === null ? "暂无" : ratio(item.conversionRate) }}</b>转化</span><span><b>{{ item.refundRate === null ? "暂无" : ratio(item.refundRate) }}</b>退款率</span></div>
          </article>
        </section>

        <section class="content-grid activity-analysis-grid">
          <article class="panel activity-trend-panel"><div class="panel-heading"><div><p>活动前 / 中 / 后</p><h2>经营表现趋势</h2></div><span class="panel-action">柱形为推广花费</span></div><BusinessChart :option="timelineOption" ariaLabel="活动前中后支付金额与全站推广花费趋势" :height="330" /></article>
          <article class="panel activity-stage-compare-panel"><div class="panel-heading"><div><p>阶段对比</p><h2>按有效统计日归一</h2></div><select v-model="stageMetric" aria-label="选择活动阶段对比指标"><option v-for="item in stageMetricDefinitions" :key="item.key" :value="item.key">{{ item.label }}</option></select></div><BusinessChart :option="stageChartOption" :ariaLabel="`活动阶段${selectedStageMetric.label}对比`" :height="330" /><p class="panel-footnote">金额、访客使用有效统计日日均；转化率、客单价和退款率使用阶段汇总口径。</p></article>
        </section>

        <section class="panel activity-metric-table-panel"><div class="panel-heading"><div><p>核心指标</p><h2>活动复盘指标表</h2></div><span class="panel-action">金额均保留两位小数</span></div><div class="activity-metric-table"><div class="activity-metric-row activity-metric-head"><span>指标</span><span>活动前</span><span>活动中</span><span>活动后</span></div><div v-for="metric in metricDefinitions" :key="metric.key" class="activity-metric-row"><strong>{{ metric.label }}</strong><span v-for="stage in snapshots" :key="stage.key">{{ formatMetric(stage, metric) }}</span></div></div><p class="activity-definition-note">全站推广场景花费来自店铺日概览；推广计划全场景花费包含关键词、人群、短视频、直播等场景。推广计划成交按平台 15 天归因，仅表示归因关系，不代表活动即时成交。</p></section>

        <section class="content-grid activity-detail-grid">
          <article class="panel activity-product-panel"><div class="panel-heading"><div><p>商品复盘</p><h2>活动期成交主力与异常</h2></div><PackageSearch :size="18" /></div><div v-if="duringProducts.length" class="activity-product-table"><div class="activity-product-row activity-product-head"><span>商品 / 系列</span><span>支付金额</span><span>买家</span><span>访客</span><span>转化</span><span>贡献</span><span>较活动前</span><span>活动后变化</span></div><div v-for="item in duringProducts" :key="item.product_id" class="activity-product-row"><div><strong>{{ item.product_name }}</strong><small>{{ item.series || '未分类' }} · {{ item.positioning || '未标记' }}<em v-if="!beforeProducts.has(item.product_id)" class="new-product-tag">活动新进入</em></small></div><span>{{ currency(item.paid_amount) }}</span><span>{{ number(item.buyers) }}</span><span>{{ number(item.visitors) }}</span><span>{{ ratio(productConversion(item)) }}</span><span>{{ productShare(item).toFixed(2) }}%</span><span class="activity-product-change" :class="{ positive: (productChange(item.paid_amount, beforeProducts.get(item.product_id)?.paid_amount) || 0) > 0, negative: (productChange(item.paid_amount, beforeProducts.get(item.product_id)?.paid_amount) || 0) < 0 }">{{ productChangeLabel(productChange(item.paid_amount, beforeProducts.get(item.product_id)?.paid_amount), '新进入') }}</span><span class="activity-product-change" :class="{ positive: (productChange(afterProducts.get(item.product_id)?.paid_amount || 0, item.paid_amount) || 0) > 0, negative: (productChange(afterProducts.get(item.product_id)?.paid_amount || 0, item.paid_amount) || 0) < 0 }">{{ windows.after ? productChangeLabel(productChange(afterProducts.get(item.product_id)?.paid_amount || 0, item.paid_amount), '未进入Top') : '尚未覆盖' }}</span></div></div><EmptyState v-else title="暂无活动期商品数据" detail="活动期没有覆盖商品明细。" :icon="PackageSearch" /></article>
          <article class="panel activity-diagnostic-panel"><div class="panel-heading"><div><p>商品诊断</p><h2>下一场活动优先动作</h2></div><TrendingUp :size="18" /></div><div v-if="productDiagnostics.length" class="activity-diagnostic-list"><div v-for="item in productDiagnostics" :key="item.title" class="activity-diagnostic-item" :class="item.kind"><span>{{ item.title }}</span><strong>{{ item.detail }}</strong></div></div><EmptyState v-else title="暂无明显商品信号" detail="需要更多商品覆盖或对照数据后再判断。" :icon="PackageSearch" /></article>
        </section>

        <section class="content-grid activity-detail-grid">
          <article class="panel activity-traffic-panel"><div class="panel-heading"><div><p>流量复盘</p><h2>来源规模与转化质量</h2></div><Eye :size="18" /></div><BusinessChart v-if="trafficSources.length" :option="trafficOption" ariaLabel="活动期流量来源访客与转化气泡图" :height="300" /><EmptyState v-else title="暂无活动期流量数据" detail="活动期没有可用的流量来源归因。" :icon="Eye" /><p class="activity-definition-note">一级来源可能存在归因重叠，气泡大小代表归因金额，不将来源金额简单求和为店铺支付金额。</p></article>
          <article class="panel activity-promotion-panel"><div class="panel-heading"><div><p>推广投入复盘</p><h2>日均花费与归因成交</h2></div><Megaphone :size="18" /></div><BusinessChart :option="promotionChartOption" ariaLabel="活动前中后推广计划日均花费归因成交与ROI" :height="250" /><div class="activity-promotion-summary"><div><span>推广计划全场景花费</span><strong>{{ currency(duringSnapshot?.planSpend) }}</strong></div><div><span>15 天归因成交</span><strong>{{ currency(duringSnapshot?.attributedPaidAmount) }}</strong></div><div><span>归因 ROI</span><strong>{{ duringSnapshot?.attributedRoi === null || duringSnapshot?.attributedRoi === undefined ? '暂无' : `${duringSnapshot.attributedRoi.toFixed(2)}x` }}</strong></div></div><div class="activity-promotion-warning"><RefreshCw :size="15" />图表按有效统计日日均比较；归因成交可能滞后，不代表活动即时成交。</div></article>
        </section>

        <section class="panel activity-conclusion-panel"><div class="panel-heading"><div><p>活动复盘</p><h2>指标变化</h2></div><BarChart3 :size="18" /></div><div class="activity-conclusion-copy">{{ conclusion }}</div><div class="activity-conclusion-actions"><span><Users :size="14" />流量：高流量低转化来源与商品</span><span><ShoppingBag :size="14" />商品：成交主力与高转化低流量商品</span><span><Megaphone :size="14" />投放：全场景花费与 15 天归因成交</span></div></section>
      </template>
      <section v-else-if="analysisError" class="panel activity-empty-analysis"><EmptyState title="暂无可复盘数据" :detail="analysisError" :icon="BarChart3" /></section>
    </template>
  </template>
  <section v-else-if="loading" class="loading-panel"><LoaderCircle :size="26" class="spinning" /><span>正在读取活动日历</span></section>
</template>
