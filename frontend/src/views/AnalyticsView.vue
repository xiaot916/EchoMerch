<script setup lang="ts">
import { computed, ref, watch } from "vue"
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  CheckCircle2,
  CircleDollarSign,
  MousePointerClick,
  Target,
  UsersRound,
} from "lucide-vue-next"

import AnalyticsTrendChart from "@/components/AnalyticsTrendChart.vue"
import BusinessActionTable from "@/components/BusinessActionTable.vue"
import BusinessChart from "@/components/BusinessChart.vue"
import EmptyState from "@/components/EmptyState.vue"
import SalesGrowthBridge from "@/components/SalesGrowthBridge.vue"
import { useDashboard } from "@/composables/useDashboard"
import { buildSalesGrowthBridge, type BusinessActionRow } from "@/lib/businessDecision"
import { compactRange, currency, number, ratio, shortDate } from "@/lib/format"

type Granularity = "day" | "week" | "month"

const { dashboard, loading } = useDashboard()
const granularity = ref<Granularity>("day")
const granularityOptions: Array<{ key: Granularity; label: string }> = [
  { key: "day", label: "日" },
  { key: "week", label: "周" },
  { key: "month", label: "月" },
]

const summary = computed(() => dashboard.value?.summary)
const comparison = computed(() => dashboard.value?.comparison)
const period = computed(() => dashboard.value?.period)
const primaryCoverage = computed(() => dashboard.value?.coverage.find((item) => item.dataset === "店铺日概览"))
const latestStoreDate = computed(() => dashboard.value?.freshness.find((item) => item.dataset === "店铺日概览")?.latest_date || dashboard.value?.range_end || "")
const coverageIsComplete = computed(() => Boolean(primaryCoverage.value && primaryCoverage.value.status === "complete"))
const comparisonAvailable = computed(() => coverageIsComplete.value)
const missingDateLabel = computed(() => period.value?.missing_dates.map(shortDate).join("、") ?? "")

const kpis = computed(() => {
  if (!summary.value || !comparison.value) return []
  return [
    { label: "支付金额", value: currency(summary.value.paid_amount), detail: `日均 ${currency(summary.value.average_daily_paid_amount)}`, change: comparison.value.paid_amount.change_percent, icon: CircleDollarSign, tone: "brand" },
    { label: "支付转化率", value: ratio(summary.value.conversion_rate), detail: `${number(summary.value.buyers)} 位支付买家 / ${number(summary.value.visitors)} 位访客`, change: comparison.value.conversion_rate.change_percent, icon: MousePointerClick, tone: "success" },
    { label: "支付客单价", value: currency(summary.value.customer_unit_price), detail: "支付金额 / 支付买家", change: null, icon: UsersRound, tone: "neutral" },
    { label: "全站推广花费", value: currency(summary.value.promotion_cost), detail: "店铺日报口径；计划花费见推广分析", change: comparison.value.promotion_cost.change_percent, icon: Target, tone: "efficiency" },
  ]
})

function requestedDates(start: string, end: string): string[] {
  const rows: string[] = []
  const cursor = new Date(`${start}T12:00:00Z`)
  const last = new Date(`${end}T12:00:00Z`)
  while (cursor <= last) {
    rows.push(cursor.toISOString().slice(0, 10))
    cursor.setUTCDate(cursor.getUTCDate() + 1)
  }
  return rows
}

const requestedDayRows = computed(() => {
  if (!period.value) return []
  const metrics = new Map((dashboard.value?.daily_metrics || []).map((item) => [item.stat_date, item]))
  return requestedDates(period.value.requested_start, period.value.requested_end).map((date) => ({ date, metric: metrics.get(date) }))
})
const trendPoints = computed(() => requestedDayRows.value.map((item) => ({ date: item.date, value: item.metric?.paid_amount ?? null })))

function weekStart(value: string): string {
  const date = new Date(`${value}T12:00:00`)
  const weekday = date.getDay() || 7
  date.setDate(date.getDate() - weekday + 1)
  return date.toISOString().slice(0, 10)
}

const groupedTrendPoints = computed(() => {
  if (granularity.value === "day") return trendPoints.value
  const buckets = new Map<string, number>()
  for (const point of trendPoints.value) {
    if (point.value === null) continue
    const key = granularity.value === "week" ? weekStart(point.date) : point.date.slice(0, 7)
    buckets.set(key, (buckets.get(key) || 0) + point.value)
  }
  return [...buckets].map(([date, value]) => ({ date, value }))
})
const isSingleDay = computed(() => period.value?.expected_days === 1)
const singleDayPaidOption = computed(() => ({
  color: ["#16845b", "#b8c6bf"],
  tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (value: number) => currency(Number(value)) },
  grid: { left: 68, right: 26, top: 28, bottom: 42 },
  xAxis: { type: "category", data: ["当前日", "上一周期"], axisTick: { show: false }, axisLine: { lineStyle: { color: "#d9e1dc" } } },
  yAxis: { type: "value", axisLabel: { formatter: (value: number) => `¥${Math.round(value).toLocaleString("zh-CN")}` }, splitLine: { lineStyle: { color: "#edf1ef", type: "dashed" } } },
  series: [{
    name: "支付金额",
    type: "bar",
    colorBy: "data",
    barMaxWidth: 72,
    label: { show: true, position: "top", color: "#405449", formatter: (params: { value: number }) => currency(Number(params.value)) },
    data: [summary.value?.paid_amount || 0, comparison.value?.paid_amount.previous || 0],
  }],
}))

const recentDays = computed(() => requestedDayRows.value.slice().reverse())
const detailPage = ref(1)
const detailPageSize = ref(10)
const detailPageCount = computed(() => Math.max(1, Math.ceil(recentDays.value.length / detailPageSize.value)))
const pagedRecentDays = computed(() => {
  const start = (detailPage.value - 1) * detailPageSize.value
  return recentDays.value.slice(start, start + detailPageSize.value)
})
const detailPageStart = computed(() => recentDays.value.length ? (detailPage.value - 1) * detailPageSize.value + 1 : 0)
const detailPageEnd = computed(() => Math.min(detailPage.value * detailPageSize.value, recentDays.value.length))
watch(detailPageSize, () => { detailPage.value = 1 })
watch(detailPageCount, (pageCount) => { if (detailPage.value > pageCount) detailPage.value = pageCount })
watch(() => [period.value?.requested_start, period.value?.requested_end], () => { detailPage.value = 1 })
const refundTotal = computed(() => (dashboard.value?.daily_metrics || []).reduce((total, item) => total + item.refund_amount, 0))
const refundRate = computed(() => {
  const paid = summary.value?.paid_amount || 0
  return paid > 0 ? (refundTotal.value / paid) * 100 : 0
})
const refundOption = computed(() => ({
  color: ["#c2765b", "#e2a447"],
  tooltip: { trigger: "axis", formatter: (params: Array<{ axisValue: string; seriesName: string; value: number }>) => {
    if (!params.length) return ""
    return `<strong>${params[0].axisValue}</strong><br/>${params.map((item) => `${item.seriesName}：${item.seriesName.includes("率") ? `${Number(item.value).toFixed(2)}%` : currency(Number(item.value))}`).join("<br/>")}`
  } },
  legend: { bottom: 0, data: ["退款金额", "金额退款率"] },
  grid: { left: 56, right: 58, top: 24, bottom: 52 },
  xAxis: { type: "category", data: requestedDayRows.value.map((item) => item.date.slice(5)) },
  yAxis: [{ type: "value", axisLabel: { formatter: (value: number) => `¥${Math.round(value).toLocaleString("zh-CN")}` }, splitLine: { lineStyle: { color: "#edf1ef" } } }, { type: "value", min: 0, axisLabel: { formatter: "{value}%" } }],
  series: [
    { name: "退款金额", type: "bar", barMaxWidth: 18, data: requestedDayRows.value.map((item) => item.metric?.refund_amount ?? null) },
    { name: "金额退款率", type: "line", yAxisIndex: 1, smooth: true, connectNulls: false, data: requestedDayRows.value.map((item) => item.metric?.refund_rate ?? null) },
  ],
}))

const currentSalesBridgeInput = computed(() => ({
  paidAmount: summary.value?.paid_amount ?? 0,
  visitors: summary.value?.visitors ?? 0,
  buyers: summary.value?.buyers ?? 0,
  conversionRate: summary.value?.conversion_rate ?? 0,
}))
const previousSalesBridgeInput = computed(() => ({
  paidAmount: comparison.value?.paid_amount.previous ?? 0,
  visitors: comparison.value?.visitors.previous ?? 0,
  buyers: comparison.value?.buyers.previous ?? 0,
  conversionRate: comparison.value?.conversion_rate.previous ?? 0,
}))
const salesBridge = computed(() => buildSalesGrowthBridge(currentSalesBridgeInput.value, previousSalesBridgeInput.value))
const transactionActions = computed<BusinessActionRow[]>(() => {
  const rows: BusinessActionRow[] = []
  if (!coverageIsComplete.value) {
    rows.push({ id: "coverage", priority: "P0", object: "店铺日报", issue: "统计区间存在缺失日", evidence: missingDateLabel.value || "日报覆盖不完整", impact: `${period.value?.missing_dates.length ?? 0} 个缺失日`, action: "先补采缺失日期，再确认环比和金额贡献是否成立。", validation: "日报覆盖天数 = 应覆盖天数", window: "补采后即时", tone: "risk" })
  }
  const negativeDriver = salesBridge.value.drivers.slice().sort((left, right) => left.contribution - right.contribution)[0]
  if (salesBridge.value.delta < 0 && negativeDriver?.contribution < 0) {
    rows.push({ id: `driver-${negativeDriver.key}`, priority: "P0", object: negativeDriver.label, issue: "本周期支付下降的首要金额拖累", evidence: negativeDriver.explanation, impact: currency(negativeDriver.contribution), action: negativeDriver.key === "traffic" ? "下钻流量页定位下降渠道与入口。" : negativeDriver.key === "conversion" ? "检查高流量低转化渠道、商品和详情承接。" : "核对正装/MINI结构、关联销售和低客单商品占比。", validation: "支付金额、该驱动贡献与支付买家", window: "3-7 天", tone: "risk" })
  }
  const highRefundDay = requestedDayRows.value.filter((item) => item.metric && item.metric.refund_amount > 0).sort((left, right) => (right.metric?.refund_rate ?? 0) - (left.metric?.refund_rate ?? 0))[0]
  if (highRefundDay?.metric) {
    rows.push({ id: `refund-${highRefundDay.date}`, priority: highRefundDay.metric.refund_rate >= refundRate.value * 1.25 ? "P0" : "P1", object: highRefundDay.date, issue: "区间内金额退款率最高日期", evidence: `退款率 ${ratio(highRefundDay.metric.refund_rate)}，支付 ${currency(highRefundDay.metric.paid_amount)}`, impact: currency(highRefundDay.metric.refund_amount), action: "下钻当日退款商品、活动承诺和客服问题，区分集中退款与日常波动。", validation: "退款金额、退款率、净支付", window: "1-3 天", tone: "warning" })
  }
  const averageVisitors = requestedDayRows.value.length ? (summary.value?.visitors ?? 0) / requestedDayRows.value.filter((item) => item.metric).length : 0
  const lowConversionDay = requestedDayRows.value.filter((item) => item.metric && item.metric.visitors >= averageVisitors * .7 && item.metric.conversion_rate < (summary.value?.conversion_rate ?? 0) * .75).sort((left, right) => (right.metric?.visitors ?? 0) - (left.metric?.visitors ?? 0))[0]
  if (lowConversionDay?.metric) {
    rows.push({ id: `conversion-${lowConversionDay.date}`, priority: "P1", object: lowConversionDay.date, issue: "有流量但支付转化明显低于区间水平", evidence: `${number(lowConversionDay.metric.visitors)} 访客，转化 ${ratio(lowConversionDay.metric.conversion_rate)}`, impact: currency(lowConversionDay.metric.paid_amount), action: "核对当日主要渠道、商品库存、价格权益和详情页承接。", validation: "转化率、加购率、支付买家", window: "3-7 天", tone: "warning" })
  }
  return rows.slice(0, 4)
})

function changeLabel(change: number | null): string {
  if (change === null || Number.isNaN(change)) return "暂无对比"
  return `${change >= 0 ? "+" : ""}${change.toFixed(2)}%`
}

function changeClass(change: number | null): string {
  if (change === null || change === 0) return "neutral"
  return change > 0 ? "up" : "down"
}

</script>

<template>
  <section v-if="dashboard && summary && period" class="analytics-overview">
    <header class="overview-heading">
      <div>
        <h1>交易分析</h1>
        <p class="overview-subtitle">对比前一同长度周期 {{ compactRange(period.previous_start, period.previous_end) }}</p>
      </div>
      <div class="overview-heading-meta">
        <span class="latest-status" :class="{ warning: !coverageIsComplete }"><CheckCircle2 v-if="coverageIsComplete" :size="15" /><AlertTriangle v-else :size="15" />{{ coverageIsComplete ? "数据完整" : `日报缺失 ${missingDateLabel}` }}</span>
        <span>最新 {{ shortDate(latestStoreDate) }}</span>
      </div>
    </header>

    <section class="overview-kpi-grid" aria-label="核心经营指标">
      <article v-for="item in kpis" :key="item.label" class="overview-kpi" :class="`kpi-${item.tone}`">
        <div class="overview-kpi-top"><span>{{ item.label }}</span><component :is="item.icon" :size="17" /></div>
        <strong>{{ item.value }}</strong>
        <small>{{ item.detail }}</small>
        <em v-if="item.change !== null && comparisonAvailable" :class="changeClass(item.change)"><ArrowUpRight v-if="item.change > 0" :size="13" /><ArrowDownRight v-else :size="13" />{{ changeLabel(item.change) }} 环比</em>
      </article>
    </section>

    <section class="overview-primary-grid">
      <article class="overview-panel trend-overview-panel">
        <div class="overview-panel-heading"><div><h2>{{ isSingleDay ? "支付金额对比" : "支付金额趋势" }}</h2></div><div v-if="!isSingleDay" class="overview-segmented"><button v-for="option in granularityOptions" :key="option.key" :class="{ active: granularity === option.key }" @click="granularity = option.key">{{ option.label }}</button></div></div>
        <BusinessChart v-if="isSingleDay" :option="singleDayPaidOption" ariaLabel="当前日与上一周期支付金额对比图" :height="295" />
        <AnalyticsTrendChart v-else-if="groupedTrendPoints.length" :points="groupedTrendPoints" label="支付金额" kind="currency" color="#16845b" theme="light" />
        <EmptyState v-else title="暂无支付趋势" detail="当前范围没有店铺日概览记录。" />
      </article>

      <article class="overview-panel driver-panel">
        <div class="overview-panel-heading"><div><h2>支付金额增长贡献</h2></div><span class="range-note">访客 × 转化率 × 客单价</span></div>
        <SalesGrowthBridge :current="currentSalesBridgeInput" :previous="previousSalesBridgeInput" :comparable="comparisonAvailable" :height="250" />
      </article>
    </section>

    <section class="overview-panel analytics-refund-panel">
      <div class="overview-panel-heading"><div><h2>退款金额与金额退款率</h2></div><span class="range-note">累计退款 {{ currency(refundTotal) }} · 加权退款率 {{ ratio(refundRate) }}</span></div>
      <BusinessChart v-if="dashboard.daily_metrics.length" :option="refundOption" ariaLabel="退款金额和金额退款率趋势图" :height="300" />
      <EmptyState v-else title="暂无退款趋势" detail="当前范围没有店铺日概览退款字段。" />
    </section>

    <BusinessActionTable :rows="transactionActions" eyebrow="交易诊断" title="优先排查对象" note="金额贡献、退款与转化异常" />

    <section class="overview-panel daily-overview-panel">
      <div class="overview-panel-heading"><div><h2>交易明细</h2></div><span class="range-note">{{ recentDays.length }} 个统计日</span></div>
      <div v-if="recentDays.length" class="compact-table daily-table"><div class="compact-table-row compact-table-head"><span>日期</span><span>支付金额</span><span>访客</span><span>买家</span><span>转化率</span><span>全站推广花费</span></div><div v-for="item in pagedRecentDays" :key="item.date" class="compact-table-row" :class="{ 'is-missing': !item.metric }"><strong>{{ item.date }}</strong><span>{{ item.metric ? currency(item.metric.paid_amount) : "--" }}</span><span>{{ item.metric ? number(item.metric.visitors) : "--" }}</span><span>{{ item.metric ? number(item.metric.buyers) : "--" }}</span><span>{{ item.metric ? ratio(item.metric.conversion_rate) : "--" }}</span><span>{{ item.metric ? currency(item.metric.promotion_cost) : "--" }}</span></div></div><footer v-if="recentDays.length" class="daily-pagination"><div><span>显示 {{ detailPageStart }}–{{ detailPageEnd }} / {{ recentDays.length }} 天</span><label>每页<select v-model.number="detailPageSize"><option :value="10">10</option><option :value="20">20</option><option :value="30">30</option></select></label></div><div><button type="button" :disabled="detailPage <= 1" @click="detailPage -= 1">上一页</button><span>第 {{ detailPage }} / {{ detailPageCount }} 页</span><button type="button" :disabled="detailPage >= detailPageCount" @click="detailPage += 1">下一页</button></div></footer><EmptyState v-else title="暂无日报" detail="当前区间没有有效统计日。" />
    </section>
  </section>
  <section v-else-if="!loading" class="analytics-empty"><EmptyState title="暂无经营数据" detail="当前日期范围没有可展示的店铺日概览。" /></section>
</template>
