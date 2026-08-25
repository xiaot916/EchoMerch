<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { Activity, ArrowDownRight, ArrowUpRight, CircleDollarSign, Gauge, Megaphone, MousePointerClick, PackageCheck, ReceiptText, ShoppingBag, Target, UsersRound, Video } from "lucide-vue-next"

import { fetchAnalyticsProducts, fetchFlashSaleAnalysis, fetchStores } from "@/api"
import BusinessChart from "@/components/BusinessChart.vue"
import EmptyState from "@/components/EmptyState.vue"
import { useDashboard } from "@/composables/useDashboard"
import { compactRange, currency, number, ratio, shortDate } from "@/lib/format"
import type { FlashSaleAnalysisResponse, ProductMetric } from "@/types"

const { dashboard } = useDashboard()
const products = ref<ProductMetric[]>([])
const flashSale = ref<FlashSaleAnalysisResponse>()
const supportingLoading = ref(false)
const supportingErrors = ref<string[]>([])

const summary = computed(() => dashboard.value?.summary)
const comparison = computed(() => dashboard.value?.comparison)
const promotionCoverage = computed(() => dashboard.value?.coverage.find((item) => item.dataset === "推广计划"))
const refundRate = computed(() => summary.value?.paid_amount ? summary.value.refund_amount / summary.value.paid_amount * 100 : 0)
const missingDates = computed(() => dashboard.value?.period.missing_dates ?? [])
const coverageComplete = computed(() => missingDates.value.length === 0)
const latestStoreDate = computed(() => dashboard.value?.coverage.find((item) => item.dataset === "店铺日概览")?.latest_date || dashboard.value?.range_end || "")
const analysis = computed(() => dashboard.value?.analysis)

type PositioningBucket = "正装" | "MINI装" | "试用装" | "其他"
const POSITIONING_ORDER: PositioningBucket[] = ["正装", "MINI装", "试用装", "其他"]
const POSITIONING_COLORS: Record<PositioningBucket, string> = {
  正装: "#258d69",
  MINI装: "#4f7fd1",
  试用装: "#d0933b",
  其他: "#8b9b93",
}
const SERIES_COLORS = ["#258d69", "#4f7fd1", "#d0933b", "#c76d59", "#886bb4", "#4b9a9c", "#78945e", "#a78662", "#8b9b93"]
function normalizePositioning(value: string): PositioningBucket {
  const normalized = (value || "").trim()
  if (normalized.includes("正装")) return "正装"
  if (/mini/i.test(normalized)) return "MINI装"
  if (normalized.includes("试用")) return "试用装"
  return "其他"
}

const channelContributions = computed(() => {
  const total = summary.value?.paid_amount ?? 0
  const rows = [
    { label: "会员成交", amount: analysis.value?.member.paid_amount ?? 0, note: "会员身份归因" },
    { label: "CPS", amount: analysis.value?.cps.paid_amount ?? 0, note: "付款口径" },
    { label: "直播", amount: analysis.value?.live.paid_amount ?? 0, note: "店播 + 达播" },
    { label: "百亿补贴", amount: analysis.value?.bybt.paid_amount ?? 0, note: "百补频道" },
    { label: "内容种草", amount: analysis.value?.content.paid_amount ?? 0, note: "内容归因" },
    { label: "淘宝秒杀", amount: flashSale.value?.summary.paid_amount ?? 0, note: `${flashSale.value?.summary.active_days ?? 0} 个有效日` },
  ]
  return rows.filter((item) => item.amount > 0).map((item) => ({ ...item, share: total ? item.amount / total * 100 : 0 })).sort((left, right) => right.share - left.share)
})
const channelContributionOption = computed(() => ({
  color: ["#3d8f70"],
  tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, formatter: (params: Array<{ dataIndex: number }>) => {
    const item = channelContributions.value[params[0]?.dataIndex ?? 0]
    return item ? `${item.label}<br/>归因成交 ${currency(item.amount)}<br/>占全店支付 ${ratio(item.share)}<br/>${item.note}` : ""
  } },
  grid: { left: 88, right: 48, top: 18, bottom: 30 },
  xAxis: { type: "value", max: (value: { max: number }) => Math.max(10, Math.ceil(value.max / 10) * 10), axisLabel: { formatter: "{value}%", color: "#849188" }, splitLine: { lineStyle: { color: "#edf1ef" } } },
  yAxis: { type: "category", data: channelContributions.value.map((item) => item.label), axisLabel: { color: "#56675d" } },
  series: [{ type: "bar", barMaxWidth: 18, label: { show: true, position: "right", formatter: (params: { value: number }) => `${Number(params.value).toFixed(1)}%`, color: "#54645b", fontSize: 10 }, data: channelContributions.value.map((item) => Number(item.share.toFixed(2))) }],
}))
const liveStructure = computed(() => {
  const live = analysis.value?.live
  const rows = [
    { label: "店播", amount: live?.shop_paid_amount ?? 0, color: "#26946d" },
    { label: "达播", amount: live?.talent_paid_amount ?? 0, color: "#557ed3" },
  ]
  const total = rows.reduce((sum, item) => sum + item.amount, 0)
  return rows.map((item) => ({ ...item, share: total ? item.amount / total * 100 : 0 }))
})
const customerStructure = computed(() => {
  const rows = analysis.value?.customer.segments ?? []
  const total = rows.reduce((sum, item) => sum + item.paid_amount, 0)
  const colors = ["#4f83d1", "#d39a3e", "#2b9670"]
  return rows.map((item, index) => ({ ...item, share: total ? item.paid_amount / total * 100 : 0, color: colors[index] ?? "#81918a" }))
})
const customerCoverage = computed(() => {
  const dates = (analysis.value?.customer.daily_metrics ?? []).map((item) => item.stat_date).sort()
  return { days: dates.length, start: dates[0], end: dates.length ? dates[dates.length - 1] : undefined }
})
const productPositioningStructure = computed(() => {
  const total = products.value.reduce((sum, item) => sum + item.paid_amount, 0)
  return POSITIONING_ORDER.map((name) => {
    const items = products.value.filter((item) => normalizePositioning(item.positioning) === name)
    const amount = items.reduce((sum, item) => sum + item.paid_amount, 0)
    return { label: name, amount, count: items.length, share: total ? amount / total * 100 : 0, color: POSITIONING_COLORS[name] }
  })
})

const selectedPositioning = ref<PositioningBucket>("正装")
const selectedPositioningNode = computed(() => productPositioningStructure.value.find((item) => item.label === selectedPositioning.value))
watch(productPositioningStructure, (rows) => {
  if ((selectedPositioningNode.value?.amount ?? 0) > 0) return
  const firstAvailable = rows.find((item) => item.amount > 0)
  if (firstAvailable) selectedPositioning.value = firstAvailable.label
}, { immediate: true })
const selectedSeriesStructure = computed(() => {
  const scoped = products.value.filter((item) => normalizePositioning(item.positioning) === selectedPositioning.value)
  const total = scoped.reduce((sum, item) => sum + item.paid_amount, 0)
  const grouped = new Map<string, number>()
  for (const item of scoped) {
    const label = item.series || "未分类系列"
    grouped.set(label, (grouped.get(label) ?? 0) + item.paid_amount)
  }
  const sorted = [...grouped.entries()].sort((left, right) => right[1] - left[1])
  const visible = sorted.slice(0, 8)
  const remainder = sorted.slice(8).reduce((sum, [, amount]) => sum + amount, 0)
  if (remainder > 0) visible.push(["其他系列", remainder])
  return visible.map(([label, amount], index) => ({ label, amount, share: total ? amount / total * 100 : 0, color: SERIES_COLORS[index] ?? SERIES_COLORS[SERIES_COLORS.length - 1] }))
})
const productPositioningPieOption = computed(() => ({
  color: productPositioningStructure.value.map((item) => item.color),
  tooltip: {
    trigger: "item",
    formatter: (params: { name: string; value: number; percent: number }) => `${params.name}<br/>支付金额 ${currency(params.value)}<br/>占全店支付 ${params.percent.toFixed(1)}%`,
  },
  series: [{
    type: "pie",
    radius: ["42%", "72%"],
    center: ["50%", "48%"],
    avoidLabelOverlap: true,
    label: { color: "#506158", fontSize: 10, formatter: (params: { name: string; percent: number }) => `${params.name} ${params.percent.toFixed(1)}%` },
    labelLine: { length: 8, length2: 8, lineStyle: { color: "#bcc9c1" } },
    data: productPositioningStructure.value.filter((item) => item.amount > 0).map((item) => ({ name: item.label, value: item.amount, itemStyle: { color: item.color } })),
  }],
}))
const selectedSeriesPieOption = computed(() => ({
  color: selectedSeriesStructure.value.map((item) => item.color),
  tooltip: {
    trigger: "item",
    formatter: (params: { name: string; value: number; percent: number }) => `${params.name}<br/>支付金额 ${currency(params.value)}<br/>占${selectedPositioning.value}支付 ${params.percent.toFixed(1)}%`,
  },
  series: [{
    type: "pie",
    radius: ["42%", "72%"],
    center: ["50%", "48%"],
    avoidLabelOverlap: true,
    label: { color: "#506158", fontSize: 10, formatter: (params: { name: string; percent: number }) => `${params.name} ${params.percent.toFixed(1)}%` },
    labelLine: { length: 8, length2: 8, lineStyle: { color: "#bcc9c1" } },
    data: selectedSeriesStructure.value.map((item) => ({ name: item.label, value: item.amount, itemStyle: { color: item.color } })),
  }],
}))

async function loadSupportingData(): Promise<void> {
  if (!dashboard.value) return
  supportingLoading.value = true
  supportingErrors.value = []
  const start = dashboard.value.range_start
  const end = dashboard.value.range_end
  try {
    const stores = await fetchStores()
    const storeId = stores[0]?.store_id
    const [productResult, flashResult] = await Promise.allSettled([
      fetchAnalyticsProducts(start, end, storeId),
      fetchFlashSaleAnalysis(start, end, storeId),
    ])
    if (productResult.status === "fulfilled") products.value = productResult.value
    else { products.value = []; supportingErrors.value.push("商品结构读取失败") }
    if (flashResult.status === "fulfilled") flashSale.value = flashResult.value
    else { flashSale.value = undefined; supportingErrors.value.push("秒杀贡献读取失败") }
  } catch {
    products.value = []
    flashSale.value = undefined
    supportingErrors.value = ["经营结构数据读取失败"]
  } finally {
    supportingLoading.value = false
  }
}

watch(() => [dashboard.value?.range_start, dashboard.value?.range_end], () => { void loadSupportingData() }, { immediate: true })
const operatingDays = computed(() => {
  const storeRows = new Map((dashboard.value?.daily_metrics || []).map((item) => [item.stat_date, item]))
  const promotionRows = new Map((dashboard.value?.promotion_daily_metrics || []).map((item) => [item.stat_date, item]))
  if (!dashboard.value) return []
  const dates: string[] = []
  const cursor = new Date(`${dashboard.value.range_start}T12:00:00Z`)
  const last = new Date(`${dashboard.value.range_end}T12:00:00Z`)
  while (cursor <= last) {
    dates.push(cursor.toISOString().slice(0, 10))
    cursor.setUTCDate(cursor.getUTCDate() + 1)
  }
  return dates.map((statDate) => ({
    statDate,
    store: storeRows.get(statDate),
    promotion: promotionRows.get(statDate),
  }))
})
const dailyRows = computed(() => {
  if (!dashboard.value) return []
  const rows = new Map(operatingDays.value.map((item) => [item.statDate, item]))
  const result: Array<{ statDate: string; store: typeof operatingDays.value[number]["store"]; promotion: typeof operatingDays.value[number]["promotion"] }> = []
  const cursor = new Date(`${dashboard.value.range_start}T12:00:00Z`)
  const last = new Date(`${dashboard.value.range_end}T12:00:00Z`)
  while (cursor <= last) {
    const statDate = cursor.toISOString().slice(0, 10)
    result.push(rows.get(statDate) ?? { statDate, store: undefined, promotion: undefined })
    cursor.setUTCDate(cursor.getUTCDate() + 1)
  }
  return result.reverse()
})
const dailyPage = ref(1)
const dailyPageSize = ref(10)
const dailyPageCount = computed(() => Math.max(1, Math.ceil(dailyRows.value.length / dailyPageSize.value)))
const pagedDailyRows = computed(() => {
  const start = (dailyPage.value - 1) * dailyPageSize.value
  return dailyRows.value.slice(start, start + dailyPageSize.value)
})
const dailyPageStart = computed(() => dailyRows.value.length ? (dailyPage.value - 1) * dailyPageSize.value + 1 : 0)
const dailyPageEnd = computed(() => Math.min(dailyPage.value * dailyPageSize.value, dailyRows.value.length))
watch(dailyPageSize, () => { dailyPage.value = 1 })
watch(dailyPageCount, (pageCount) => { if (dailyPage.value > pageCount) dailyPage.value = pageCount })
watch(() => [dashboard.value?.range_start, dashboard.value?.range_end], () => { dailyPage.value = 1 })

function changeLabel(change: number | null | undefined): string {
  if (change === null || change === undefined || Number.isNaN(change)) return "暂无环比"
  return `${change >= 0 ? "+" : ""}${change.toFixed(2)}%`
}

function changeClass(change: number | null | undefined): string {
  if (!change) return "neutral"
  return change > 0 ? "up" : "down"
}

const coreMetrics = computed(() => {
  if (!summary.value || !comparison.value) return []
  return [
    { label: "支付金额", value: currency(summary.value.paid_amount), detail: `日均 ${currency(summary.value.average_daily_paid_amount)}`, change: comparison.value.paid_amount.change_percent, icon: CircleDollarSign, tone: "result" },
    { label: "净支付", value: currency(summary.value.net_paid_amount), detail: `退款 ${currency(summary.value.refund_amount)} · ${ratio(refundRate.value)}`, change: null, icon: ReceiptText, tone: "risk" },
    { label: "全量推广花费", value: currency(summary.value.promotion_plan_spend), detail: `推广归因成交 ${currency(summary.value.promotion_attributed_paid_amount)}`, change: null, icon: Megaphone, tone: "spend" },
    { label: "推广费比", value: ratio(summary.value.promotion_fee_ratio), detail: "推广计划花费 / 支付金额", change: null, icon: Gauge, tone: "efficiency" },
    { label: "推广 ROI", value: `${summary.value.promotion_roi.toFixed(2)}x`, detail: "归因成交 / 推广计划花费", change: null, icon: Target, tone: "efficiency" },
    { label: "支付转化率", value: ratio(summary.value.conversion_rate), detail: `${number(summary.value.buyers)} 买家 / ${number(summary.value.visitors)} 访客`, change: comparison.value.conversion_rate.change_percent, icon: MousePointerClick, tone: "traffic" },
    { label: "支付客单价", value: currency(summary.value.customer_unit_price), detail: "支付金额 / 支付买家", change: null, icon: ShoppingBag, tone: "traffic" },
    { label: "支付买家", value: number(summary.value.buyers), detail: `${number(summary.value.visitors)} 位访客`, change: comparison.value.buyers.change_percent, icon: UsersRound, tone: "traffic" },
  ]
})

const resultTrendOption = computed(() => {
  const rows = operatingDays.value
  return {
    color: ["#1b9a70", "#e09a3e"],
    tooltip: { trigger: "axis", formatter: (params: Array<{ dataIndex: number }>) => {
      const row = rows[params[0]?.dataIndex ?? 0]?.store
      return row ? `${row.stat_date}<br/>支付金额 ${currency(row.paid_amount)}<br/>退款金额 ${currency(row.refund_amount)}<br/>净支付 ${currency(row.paid_amount - row.refund_amount)}` : "该日暂无店铺日报"
    } },
    legend: { bottom: 0, data: ["支付金额", "退款金额"], textStyle: { color: "#718179", fontSize: 11 } },
    grid: { left: 62, right: 24, top: 22, bottom: 48 },
    xAxis: { type: "category", data: rows.map((item) => item.statDate.slice(5)), axisLabel: { color: "#8491a3" } },
    yAxis: { type: "value", axisLabel: { formatter: (value: number) => `${Math.round(value / 10000)}万` }, splitLine: { lineStyle: { color: "#edf1ef" } } },
    series: [
      { name: "支付金额", type: "line", smooth: true, symbol: "none", connectNulls: false, lineStyle: { width: 2.5 }, areaStyle: { color: "rgba(27,154,112,.10)" }, data: rows.map((item) => item.store?.paid_amount ?? null) },
      { name: "退款金额", type: "bar", barMaxWidth: 15, data: rows.map((item) => item.store?.refund_amount ?? null) },
    ],
  }
})

const spendTrendOption = computed(() => {
  const rows = operatingDays.value
  return {
    color: ["#4e77d4", "#32a875"],
    tooltip: { trigger: "axis", formatter: (params: Array<{ dataIndex: number }>) => {
      const row = rows[params[0]?.dataIndex ?? 0]?.promotion
      if (!row) return ""
      const roiValue = row.spend ? row.paid_amount / row.spend : 0
      return `${row.stat_date}<br/>推广花费 ${currency(row.spend)}<br/>推广归因成交 ${currency(row.paid_amount)}<br/>推广 ROI ${roiValue.toFixed(2)}x`
    } },
    legend: { bottom: 0, data: ["全量推广花费", "推广归因成交"], textStyle: { color: "#718179", fontSize: 11 } },
    grid: { left: 62, right: 24, top: 22, bottom: 48 },
    xAxis: { type: "category", data: rows.map((item) => item.statDate.slice(5)), axisLabel: { color: "#8491a3" } },
    yAxis: { type: "value", axisLabel: { formatter: (value: number) => `${Math.round(value / 10000)}万` }, splitLine: { lineStyle: { color: "#edf1ef" } } },
    series: [
      { name: "全量推广花费", type: "bar", barMaxWidth: 16, data: rows.map((item) => item.promotion?.spend ?? null) },
      { name: "推广归因成交", type: "line", smooth: true, symbol: "none", connectNulls: false, lineStyle: { width: 2.3 }, data: rows.map((item) => item.promotion?.paid_amount ?? null) },
    ],
  }
})

const businessDrivers = computed(() => {
  if (!summary.value || !comparison.value) return []
  return [
    { label: "访客数", value: number(summary.value.visitors), change: comparison.value.visitors.change_percent, note: "流量规模" },
    { label: "支付买家", value: number(summary.value.buyers), change: comparison.value.buyers.change_percent, note: "成交人数" },
    { label: "支付转化率", value: ratio(summary.value.conversion_rate), change: comparison.value.conversion_rate.change_percent, note: "买家 / 访客" },
    { label: "支付客单价", value: currency(summary.value.customer_unit_price), change: null, note: "金额 / 买家" },
    { label: "全量推广花费", value: currency(summary.value.promotion_plan_spend), change: null, note: "推广计划全场景" },
    { label: "推广费比", value: ratio(summary.value.promotion_fee_ratio), change: null, note: "花费 / 全店支付" },
  ]
})
</script>

<template>
  <section v-if="dashboard && summary && comparison" class="store-overview-page">
    <header class="store-overview-heading">
      <div><h1>经营概览</h1><span>支付、退款、推广与转化</span></div>
      <div class="store-overview-status" :class="{ warning: !coverageComplete }"><Activity :size="16" /><div><strong>{{ coverageComplete ? "数据完整" : `日报缺失 ${missingDates.map(shortDate).join('、')}` }}</strong><small>{{ dashboard.daily_metrics.length }}/{{ dashboard.period.expected_days }} 天 · 最新 {{ shortDate(latestStoreDate) }}</small></div></div>
    </header>

    <section class="store-kpi-grid store-kpi-grid-primary" aria-label="全店核心经营指标"><article v-for="item in coreMetrics.slice(0, 4)" :key="item.label" class="store-kpi" :class="`store-kpi-${item.tone}`"><div class="store-kpi-label"><span>{{ item.label }}</span><component :is="item.icon" :size="17" /></div><strong>{{ item.value }}</strong><small>{{ item.detail }}</small><em v-if="item.change !== null" :class="changeClass(item.change)"><ArrowUpRight v-if="item.change && item.change > 0" :size="13" /><ArrowDownRight v-else-if="item.change && item.change < 0" :size="13" />{{ changeLabel(item.change) }} 环比</em></article></section>

    <section class="store-kpi-grid store-kpi-grid-secondary" aria-label="全店补充经营指标"><article v-for="item in coreMetrics.slice(4)" :key="item.label" class="store-kpi" :class="`store-kpi-${item.tone}`"><div class="store-kpi-label"><span>{{ item.label }}</span><component :is="item.icon" :size="17" /></div><strong>{{ item.value }}</strong><small>{{ item.detail }}</small><em v-if="item.change !== null" :class="changeClass(item.change)"><ArrowUpRight v-if="item.change && item.change > 0" :size="13" /><ArrowDownRight v-else-if="item.change && item.change < 0" :size="13" />{{ changeLabel(item.change) }} 环比</em></article></section>
    <section class="store-overview-grid"><article class="store-overview-panel store-result-panel"><header><div><h2>支付与退款</h2></div><span>净支付 {{ currency(summary.net_paid_amount) }}</span></header><BusinessChart v-if="dashboard.daily_metrics.length" :option="resultTrendOption" ariaLabel="全店支付金额退款金额趋势" :height="320" /><EmptyState v-else title="暂无支付数据" detail="当前区间没有店铺日报。" /></article><article class="store-overview-panel"><header><div><h2>流量与成交</h2></div><Gauge :size="18" /></header><div class="store-driver-list"><div v-for="item in businessDrivers" :key="item.label"><div><strong>{{ item.label }}</strong><small>{{ item.note }}</small></div><div><strong>{{ item.value }}</strong><em v-if="item.change !== null" :class="changeClass(item.change)">{{ changeLabel(item.change) }}</em><small v-else>当前区间</small></div></div></div></article></section>

    <section class="store-overview-grid store-overview-grid-lower"><article class="store-overview-panel"><header><div><h2>推广花费与归因成交</h2></div><span>{{ number(promotionCoverage?.covered_days || 0) }} 天</span></header><BusinessChart v-if="dashboard.promotion_daily_metrics.some((item) => item.spend > 0)" :option="spendTrendOption" ariaLabel="全量推广花费和推广归因成交趋势" :height="300" /><EmptyState v-else title="暂无推广数据" detail="当前区间没有推广日报。" /></article><article class="store-overview-panel store-efficiency-panel"><header><div><h2>推广与退款</h2></div><Target :size="18" /></header><div class="store-efficiency-main"><span>推广费比</span><strong>{{ ratio(summary.promotion_fee_ratio) }}</strong><small>全量推广花费 / 支付金额</small></div><div class="store-efficiency-pairs"><div><span>推广 ROI</span><strong>{{ summary.promotion_roi.toFixed(2) }}x</strong></div><div><span>归因成交</span><strong>{{ currency(summary.promotion_attributed_paid_amount) }}</strong></div><div><span>退款率</span><strong>{{ ratio(refundRate) }}</strong></div><div><span>净支付率</span><strong>{{ ratio(summary.paid_amount ? summary.net_paid_amount / summary.paid_amount * 100 : 0) }}</strong></div></div><p>推广费比 = 全量推广花费 / 支付金额；推广 ROI = 归因成交 / 全量推广花费。</p></article></section>

    <section class="store-overview-panel overview-structure-panel">
      <header><div><p>经营结构</p><h2>渠道贡献、直播结构与客户结构</h2></div><span>{{ supportingLoading ? "正在汇总结构数据" : "金额口径" }}</span></header>
      <div class="overview-structure-grid">
        <article class="overview-structure-block overview-channel-block"><div class="overview-block-heading"><div><strong>渠道贡献率</strong><small>各渠道归因成交 / 全店支付</small></div><Megaphone :size="17" /></div><BusinessChart v-if="channelContributions.length" :option="channelContributionOption" ariaLabel="各渠道归因成交占全店支付贡献率" :height="278" /><EmptyState v-else title="暂无渠道归因" detail="当前范围没有可用渠道成交数据。" /><p class="overview-structure-note">会员、CPS、直播、百补、内容和秒杀归因可能重叠，百分比不可相加；直播内部结构单独按 100% 计算。</p></article>
        <article class="overview-structure-block"><div class="overview-block-heading"><div><strong>直播内部结构</strong><small>店播 / 达播占直播成交</small></div><Video :size="17" /></div><div v-if="liveStructure.some((item) => item.amount > 0)" class="overview-share-stack"><div v-for="item in liveStructure" :key="item.label" class="overview-share-row"><div><span>{{ item.label }}</span><strong>{{ currency(item.amount) }}</strong></div><i><b :style="{ width: `${Math.min(item.share, 100)}%`, background: item.color }"></b></i><em>{{ item.share.toFixed(1) }}%</em></div><footer>直播合计 {{ currency(analysis?.live.paid_amount ?? 0) }}</footer></div><EmptyState v-else title="暂无直播成交" detail="当前范围没有直播成交归因。" /></article>
        <article class="overview-structure-block"><div class="overview-block-heading"><div><strong>客户成交结构</strong><small>新访 / 未购回访 / 已购回访</small></div><UsersRound :size="17" /></div><div v-if="customerStructure.length" class="overview-share-stack"><div v-for="item in customerStructure" :key="item.key" class="overview-share-row"><div><span>{{ item.label }}</span><strong>{{ currency(item.paid_amount) }}</strong></div><i><b :style="{ width: `${Math.min(item.share, 100)}%`, background: item.color }"></b></i><em>{{ item.share.toFixed(1) }}%</em></div><footer>客户分析有效 {{ customerCoverage.days }} 天<span v-if="customerCoverage.start">（{{ shortDate(customerCoverage.start) }}–{{ shortDate(customerCoverage.end || customerCoverage.start) }}）</span></footer></div><EmptyState v-else title="暂无客户结构" detail="客户日报未覆盖当前范围。" /></article>
      </div>
    </section>

    <section class="store-overview-panel overview-product-structure-panel">
      <header><div><p>商品结构</p><h2>装型与系列销售占比</h2></div><span><PackageCheck :size="14" /> {{ products.length ? `${products.length} 个商品` : "读取中" }}</span></header>
      <div class="overview-product-structure">
        <div class="overview-product-structure-column overview-positioning-column">
          <div class="overview-block-heading"><div><strong>装型销售占比</strong><small>全店商品支付金额为 100%</small></div></div>
          <BusinessChart v-if="productPositioningStructure.some((item) => item.amount > 0)" :option="productPositioningPieOption" ariaLabel="装型销售占比饼图" :height="238" />
          <EmptyState v-else title="暂无商品结构" detail="当前区间没有商品支付明细。" />
          <div class="overview-positioning-list"><button v-for="item in productPositioningStructure" :key="item.label" type="button" class="overview-positioning-row" :class="{ active: item.label === selectedPositioning }" @click="selectedPositioning = item.label"><span class="overview-positioning-label"><i :style="{ background: item.color }"></i><strong>{{ item.label }}</strong><small>{{ number(item.count) }} 商品 · {{ currency(item.amount) }}</small></span><em>{{ item.share.toFixed(1) }}%</em></button></div>
        </div>
        <div class="overview-product-structure-column overview-series-column">
          <div class="overview-block-heading"><div><strong>{{ selectedPositioning }} · 系列销售结构</strong><small>系列占比以{{ selectedPositioning }}支付金额为 100% · 当前 {{ currency(selectedPositioningNode?.amount ?? 0) }}</small></div></div>
          <BusinessChart v-if="selectedSeriesStructure.length" :option="selectedSeriesPieOption" :ariaLabel="`${selectedPositioning}系列销售结构饼图`" :height="238" />
          <EmptyState v-else title="暂无系列销售" :detail="`${selectedPositioning}当前区间没有商品支付明细。`" />
          <div v-if="selectedSeriesStructure.length" class="overview-series-legend"><div v-for="item in selectedSeriesStructure" :key="item.label"><span><i :style="{ background: item.color }"></i>{{ item.label }}</span><strong>{{ currency(item.amount) }} · {{ item.share.toFixed(1) }}%</strong></div></div>
          <p class="overview-structure-note">点击左侧装型可切换系列分布；低金额系列合并为“其他系列”，占比仍以当前装型全部支付金额计算。</p>
        </div>
      </div>
    </section>

    <section class="store-overview-panel store-daily-panel"><header><div><h2>每日经营数据</h2></div><span>{{ dailyRows.length }} 个统计日</span></header><div v-if="dailyRows.length" class="store-daily-table"><div class="store-daily-row store-daily-head"><span>日期</span><span>支付金额</span><span>退款</span><span>净支付</span><span>访客</span><span>转化率</span><span>推广花费</span><span>费比</span><span>推广 ROI</span></div><div v-for="item in pagedDailyRows" :key="item.statDate" class="store-daily-row" :class="{ 'is-missing': !item.store }"><strong>{{ item.statDate }}</strong><span>{{ item.store ? currency(item.store.paid_amount) : "--" }}</span><span>{{ item.store ? currency(item.store.refund_amount) : "--" }}</span><span>{{ item.store ? currency(item.store.paid_amount - item.store.refund_amount) : "--" }}</span><span>{{ item.store ? number(item.store.visitors) : "--" }}</span><span>{{ item.store ? ratio(item.store.conversion_rate) : "--" }}</span><span>{{ item.promotion ? currency(item.promotion.spend) : "--" }}</span><span>{{ item.store && item.promotion && item.store.paid_amount ? ratio(item.promotion.spend / item.store.paid_amount * 100) : "--" }}</span><span>{{ item.promotion?.spend ? `${(item.promotion.paid_amount / item.promotion.spend).toFixed(2)}x` : "--" }}</span></div></div><footer v-if="dailyRows.length" class="daily-pagination"><div><span>显示 {{ dailyPageStart }}–{{ dailyPageEnd }} / {{ dailyRows.length }} 天</span><label>每页<select v-model.number="dailyPageSize"><option :value="10">10</option><option :value="20">20</option><option :value="30">30</option></select></label></div><div><button type="button" :disabled="dailyPage <= 1" @click="dailyPage -= 1">上一页</button><span>第 {{ dailyPage }} / {{ dailyPageCount }} 页</span><button type="button" :disabled="dailyPage >= dailyPageCount" @click="dailyPage += 1">下一页</button></div></footer><EmptyState v-else title="暂无日报" detail="当前区间没有有效统计日。" /></section>
  </section>
</template>
