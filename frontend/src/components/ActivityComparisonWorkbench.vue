<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { CalendarRange, GitCompareArrows, LoaderCircle, RefreshCw, Scale } from "lucide-vue-next"

import { fetchDashboard } from "@/api"
import BusinessChart from "@/components/BusinessChart.vue"
import EmptyState from "@/components/EmptyState.vue"
import { currency, number, ratio } from "@/lib/format"
import type { DashboardResponse, StoreActivityCalendarEvent } from "@/types"

const props = defineProps<{
  activities: StoreActivityCalendarEvent[]
  storeId: number | null
  primaryActivityId: string
  availableEnd: string
}>()

type ComparisonMode = "activity" | "custom"
type MetricFormat = "money" | "count" | "percent" | "ratio" | "seconds"
type MetricDirection = "up" | "down" | "context"

interface DateRange { start: string; end: string }
interface ComparisonPeriod { label: string; range: DateRange }
interface ComparisonMetric {
  key: string
  group: string
  label: string
  format: MetricFormat
  direction: MetricDirection
  left: number | null
  right: number | null
  note: string
}

const mode = ref<ComparisonMode>("activity")
const leftActivityId = ref("")
const rightActivityId = ref("")
const leftCustom = ref<DateRange>({ start: "", end: "" })
const rightCustom = ref<DateRange>({ start: "", end: "" })
const loading = ref(false)
const error = ref("")
const leftData = ref<DashboardResponse | null>(null)
const rightData = ref<DashboardResponse | null>(null)
const comparedPeriods = ref<{ left: ComparisonPeriod; right: ComparisonPeriod } | null>(null)
const selectedMetricKey = ref("paid_daily")
let requestVersion = 0
let abortController: AbortController | null = null

const dateOnly = (value: string | undefined | null): string => (value || "").slice(0, 10)
const activityStart = (item: StoreActivityCalendarEvent): string => dateOnly(item.activity_start_time || item.business_day)
const activityEnd = (item: StoreActivityCalendarEvent): string => dateOnly(item.activity_end_time || item.activity_start_time || item.business_day)
const parseDate = (value: string): Date => new Date(`${value}T12:00:00`)
const dayCount = (range: DateRange): number => range.start && range.end ? Math.max(1, Math.round((parseDate(range.end).getTime() - parseDate(range.start).getTime()) / 86400000) + 1) : 0
const periodLabel = (item: StoreActivityCalendarEvent): string => `${item.activity_name || "未命名活动"} (${activityStart(item)} 至 ${activityEnd(item)})`
const normalizedActivityName = (value: string): string => value.toLowerCase().replace(/20\d{2}年?/g, "").replace(/(^|\D)\d{2}年/g, "$1").replace(/\d{1,2}月/g, "").replace(/[\s·&]/g, "")

function matchingPreviousActivity(activityId: string): StoreActivityCalendarEvent | null {
  const current = props.activities.find((item) => item.activity_id === activityId)
  if (!current) return null
  const currentYear = Number(activityStart(current).slice(0, 4))
  const normalized = normalizedActivityName(current.activity_name)
  const candidates = props.activities.filter((item) => item.activity_id !== current.activity_id && activityStart(item).slice(0, 4) < String(currentYear))
  return candidates
    .map((item) => ({
      item,
      score: (normalizedActivityName(item.activity_name) === normalized ? 100 : normalized.includes(normalizedActivityName(item.activity_name)) || normalizedActivityName(item.activity_name).includes(normalized) ? 70 : 0)
        + (Number(activityStart(item).slice(0, 4)) === currentYear - 1 ? 20 : 0),
    }))
    .sort((left, right) => right.score - left.score || activityStart(right.item).localeCompare(activityStart(left.item)))[0]?.item || null
}

function activityPeriod(activityId: string, fallback: string): ComparisonPeriod | null {
  const item = props.activities.find((activity) => activity.activity_id === activityId)
  if (!item) return null
  return { label: item.activity_name || fallback, range: { start: activityStart(item), end: activityEnd(item) } }
}

function selectedPeriods(): { left: ComparisonPeriod; right: ComparisonPeriod } | null {
  if (mode.value === "activity") {
    const left = activityPeriod(leftActivityId.value, "活动 A")
    const right = activityPeriod(rightActivityId.value, "活动 B")
    return left && right ? { left, right } : null
  }
  if (!leftCustom.value.start || !leftCustom.value.end || !rightCustom.value.start || !rightCustom.value.end) return null
  if (leftCustom.value.end < leftCustom.value.start || rightCustom.value.end < rightCustom.value.start) return null
  return {
    left: { label: "自定义区间 A", range: { ...leftCustom.value } },
    right: { label: "自定义区间 B", range: { ...rightCustom.value } },
  }
}

async function runComparison(): Promise<void> {
  const periods = selectedPeriods()
  if (!props.storeId || !periods) {
    error.value = mode.value === "activity" ? "请选择两个活动。" : "请填写两个有效日期区间。"
    return
  }
  const version = ++requestVersion
  abortController?.abort()
  abortController = new AbortController()
  loading.value = true
  error.value = ""
  try {
    const effectiveRange = (period: ComparisonPeriod): DateRange => {
      if (period.range.start > props.availableEnd) throw new Error(`${period.label} 尚未进入经营数据覆盖期。`)
      return { start: period.range.start, end: period.range.end < props.availableEnd ? period.range.end : props.availableEnd }
    }
    const leftRange = effectiveRange(periods.left)
    const rightRange = effectiveRange(periods.right)
    const [left, right] = await Promise.all([
      fetchDashboard(leftRange.start, leftRange.end, props.storeId, abortController.signal),
      fetchDashboard(rightRange.start, rightRange.end, props.storeId, abortController.signal),
    ])
    if (version !== requestVersion) return
    leftData.value = left
    rightData.value = right
    comparedPeriods.value = periods
  } catch (reason) {
    if (version !== requestVersion || (reason instanceof DOMException && reason.name === "AbortError")) return
    leftData.value = null
    rightData.value = null
    comparedPeriods.value = null
    error.value = reason instanceof Error ? reason.message : "活动对比数据读取失败"
  } finally {
    if (version === requestVersion) loading.value = false
  }
}

function safeAverage(value: number, coveredDays: number): number | null {
  return coveredDays ? value / coveredDays : null
}
function refundRate(data: DashboardResponse, coveredDays: number): number | null {
  return coveredDays && data.summary.paid_amount ? data.summary.refund_amount / data.summary.paid_amount * 100 : coveredDays ? 0 : null
}

const metrics = computed<ComparisonMetric[]>(() => {
  if (!leftData.value || !rightData.value) return []
  const left = leftData.value
  const right = rightData.value
  const leftDays = left.daily_metrics.length
  const rightDays = right.daily_metrics.length
  const leftPromotionDays = left.promotion_daily_metrics.length || (left.promotion_plans.length ? leftDays : 0)
  const rightPromotionDays = right.promotion_daily_metrics.length || (right.promotion_plans.length ? rightDays : 0)
  const leftMemberDays = left.analysis?.member.daily_metrics.length || 0
  const rightMemberDays = right.analysis?.member.daily_metrics.length || 0
  const leftServiceDays = left.analysis?.customer_service_daily.length || 0
  const rightServiceDays = right.analysis?.customer_service_daily.length || 0
  const metric = (key: string, group: string, label: string, format: MetricFormat, direction: MetricDirection, leftValue: number | null, rightValue: number | null, note: string): ComparisonMetric => ({ key, group, label, format, direction, left: leftValue, right: rightValue, note })
  return [
    metric("paid_total", "经营结果", "支付金额", "money", "up", leftDays ? left.summary.paid_amount : null, rightDays ? right.summary.paid_amount : null, "区间总额；活动天数不同时优先看日均"),
    metric("paid_daily", "经营结果", "日均支付金额", "money", "up", safeAverage(left.summary.paid_amount, leftDays), safeAverage(right.summary.paid_amount, rightDays), "按店铺经营数据有效日归一"),
    metric("visitors_daily", "经营结果", "日均访客数", "count", "up", safeAverage(left.summary.visitors, leftDays), safeAverage(right.summary.visitors, rightDays), "按店铺经营数据有效日归一"),
    metric("conversion", "经营结果", "支付转化率", "percent", "up", leftDays ? left.summary.conversion_rate : null, rightDays ? right.summary.conversion_rate : null, "支付买家数 / 访客数"),
    metric("unit_price", "经营结果", "支付客单价", "money", "context", leftDays ? left.summary.customer_unit_price : null, rightDays ? right.summary.customer_unit_price : null, "支付金额 / 支付买家数"),
    metric("refund_rate", "经营结果", "金额退款率", "percent", "down", refundRate(left, leftDays), refundRate(right, rightDays), "退款金额 / 支付金额"),
    metric("promotion_spend_daily", "推广与费比", "推广计划日均花费", "money", "context", safeAverage(left.summary.promotion_plan_spend, leftPromotionDays), safeAverage(right.summary.promotion_plan_spend, rightPromotionDays), "推广计划全场景花费按有效日归一"),
    metric("promotion_fee_ratio", "推广与费比", "推广费比", "percent", "down", leftPromotionDays ? left.summary.promotion_fee_ratio : null, rightPromotionDays ? right.summary.promotion_fee_ratio : null, "推广计划花费 / 店铺支付金额"),
    metric("promotion_paid_daily", "推广与费比", "15 天归因日均成交", "money", "up", safeAverage(left.summary.promotion_attributed_paid_amount, leftPromotionDays), safeAverage(right.summary.promotion_attributed_paid_amount, rightPromotionDays), "平台归因成交按有效日归一，不等于活动即时增量"),
    metric("promotion_roi", "推广与费比", "推广归因 ROI", "ratio", "up", leftPromotionDays ? left.summary.promotion_roi : null, rightPromotionDays ? right.summary.promotion_roi : null, "15 天归因成交 / 推广计划花费"),
    metric("member_paid_daily", "会员", "会员日均成交金额", "money", "up", left.analysis ? safeAverage(left.analysis.member.paid_amount, leftMemberDays) : null, right.analysis ? safeAverage(right.analysis.member.paid_amount, rightMemberDays) : null, "按会员数据有效日归一"),
    metric("new_members_daily", "会员", "日均新增会员", "count", "up", left.analysis ? safeAverage(left.analysis.member.new_members, leftMemberDays) : null, right.analysis ? safeAverage(right.analysis.member.new_members, rightMemberDays) : null, "按会员数据有效日归一"),
    metric("member_recruit_conversion", "会员", "新会员成交转化率", "percent", "up", leftMemberDays ? left.analysis?.member.recruit_conversion_rate ?? null : null, rightMemberDays ? right.analysis?.member.recruit_conversion_rate ?? null : null, "新会员成交人数 / 新增会员数"),
    metric("member_repurchase_daily", "会员", "日均复购会员数", "count", "up", left.analysis ? safeAverage(left.analysis.member.repurchase_members, leftMemberDays) : null, right.analysis ? safeAverage(right.analysis.member.repurchase_members, rightMemberDays) : null, "当前为每日人数累计口径"),
    metric("service_sales_daily", "客服", "客服日均销售额", "money", "up", left.analysis ? safeAverage(left.analysis.customer_service.sales_amount, leftServiceDays) : null, right.analysis ? safeAverage(right.analysis.customer_service.sales_amount, rightServiceDays) : null, "按客服数据有效日归一"),
    metric("service_consults_daily", "客服", "日均咨询人数", "count", "context", left.analysis ? safeAverage(left.analysis.customer_service.consult_users, leftServiceDays) : null, right.analysis ? safeAverage(right.analysis.customer_service.consult_users, rightServiceDays) : null, "按客服数据有效日归一"),
    metric("service_conversion", "客服", "询单转化率", "percent", "up", leftServiceDays ? left.analysis?.customer_service.sales_conversion_rate ?? null : null, rightServiceDays ? right.analysis?.customer_service.sales_conversion_rate ?? null : null, "客服销售人数 / 咨询人数"),
    metric("service_reply", "客服", "平均响应时长", "seconds", "down", leftServiceDays ? left.analysis?.customer_service.avg_reply_seconds ?? null : null, rightServiceDays ? right.analysis?.customer_service.avg_reply_seconds ?? null : null, "越低表示响应越快"),
    metric("service_satisfaction", "客服", "客户满意率", "percent", "up", leftServiceDays ? left.analysis?.customer_service.satisfaction_rate ?? null : null, rightServiceDays ? right.analysis?.customer_service.satisfaction_rate ?? null : null, "客服满意评价口径"),
  ]
})

const groupedMetrics = computed(() => {
  const groups = new Map<string, ComparisonMetric[]>()
  for (const item of metrics.value) groups.set(item.group, [...(groups.get(item.group) || []), item])
  return [...groups.entries()].map(([group, rows]) => ({ group, rows }))
})
const selectedMetric = computed(() => metrics.value.find((item) => item.key === selectedMetricKey.value) || metrics.value[0])
const coverage = computed(() => ({
  left: leftData.value?.daily_metrics.length || 0,
  right: rightData.value?.daily_metrics.length || 0,
  leftExpected: comparedPeriods.value ? dayCount(comparedPeriods.value.left.range) : 0,
  rightExpected: comparedPeriods.value ? dayCount(comparedPeriods.value.right.range) : 0,
}))

function formatValue(value: number | null, format: MetricFormat): string {
  if (value === null || !Number.isFinite(value)) return "未覆盖"
  if (format === "money") return currency(value)
  if (format === "count") return number(value)
  if (format === "percent") return ratio(value)
  if (format === "seconds") return `${value.toFixed(1)} 秒`
  return `${value.toFixed(2)}x`
}
function changePercent(item: ComparisonMetric): number | null {
  if (item.left === null || item.right === null || item.right === 0) return null
  return (item.left / item.right - 1) * 100
}
function changeClass(item: ComparisonMetric): string {
  const change = changePercent(item)
  if (change === null || Math.abs(change) < 0.01 || item.direction === "context") return "neutral"
  const positive = item.direction === "down" ? change < 0 : change > 0
  return positive ? "positive" : "negative"
}
function changeLabel(item: ComparisonMetric): string {
  const change = changePercent(item)
  if (change === null) return "不可计算"
  return `${change >= 0 ? "+" : ""}${change.toFixed(2)}%`
}

const chartOption = computed(() => {
  const metric = selectedMetric.value
  if (!metric || !comparedPeriods.value) return {}
  return {
    color: ["#16845b", "#e2a447"],
    tooltip: { trigger: "axis", valueFormatter: (value: number) => formatValue(value, metric.format) },
    grid: { left: 62, right: 24, top: 24, bottom: 34 },
    xAxis: { type: "category", data: [comparedPeriods.value.left.label, comparedPeriods.value.right.label], axisLabel: { width: 190, overflow: "truncate" } },
    yAxis: { type: "value", splitLine: { lineStyle: { color: "#edf1ef" } } },
    series: [{ type: "bar", barMaxWidth: 64, data: [metric.left, metric.right] }],
  }
})

watch(() => [props.activities, props.primaryActivityId, props.storeId, props.availableEnd] as const, () => {
  if (!props.activities.length || !props.storeId) return
  if (props.primaryActivityId && props.activities.some((item) => item.activity_id === props.primaryActivityId)) leftActivityId.value = props.primaryActivityId
  if (!leftActivityId.value) leftActivityId.value = props.activities[props.activities.length - 1]?.activity_id || ""
  const previous = matchingPreviousActivity(leftActivityId.value)
  if (!rightActivityId.value || rightActivityId.value === leftActivityId.value || !props.activities.some((item) => item.activity_id === rightActivityId.value)) rightActivityId.value = previous?.activity_id || props.activities.find((item) => item.activity_id !== leftActivityId.value)?.activity_id || ""
  const left = activityPeriod(leftActivityId.value, "活动 A")
  const right = activityPeriod(rightActivityId.value, "活动 B")
  if (left) leftCustom.value = { ...left.range }
  if (right) rightCustom.value = { ...right.range }
  if (leftActivityId.value && rightActivityId.value) void runComparison()
}, { immediate: true, deep: true })

watch(leftActivityId, (activityId) => {
  if (rightActivityId.value === activityId) rightActivityId.value = matchingPreviousActivity(activityId)?.activity_id || props.activities.find((item) => item.activity_id !== activityId)?.activity_id || ""
})
</script>

<template>
  <section class="panel activity-comparison-workbench">
    <div class="panel-heading activity-comparison-heading">
      <div><p>跨期对比</p><h2>活动对比工作台</h2></div>
      <div class="activity-comparison-mode" role="group" aria-label="选择对比方式">
        <button type="button" :class="{ active: mode === 'activity' }" @click="mode = 'activity'"><GitCompareArrows :size="14" />活动对活动</button>
        <button type="button" :class="{ active: mode === 'custom' }" @click="mode = 'custom'"><CalendarRange :size="14" />自定义日期</button>
      </div>
    </div>

    <div v-if="mode === 'activity'" class="activity-comparison-controls">
      <label><span>活动 A</span><select v-model="leftActivityId"><option v-for="item in activities" :key="`left-${item.activity_id}`" :value="item.activity_id">{{ periodLabel(item) }}</option></select></label>
      <span class="activity-comparison-versus"><Scale :size="17" />对比</span>
      <label><span>活动 B</span><select v-model="rightActivityId"><option v-for="item in activities" :key="`right-${item.activity_id}`" :value="item.activity_id" :disabled="item.activity_id === leftActivityId">{{ periodLabel(item) }}</option></select></label>
      <button type="button" class="activity-comparison-run" :disabled="loading" @click="runComparison"><RefreshCw :size="15" :class="{ spinning: loading }" />开始对比</button>
    </div>
    <div v-else class="activity-comparison-controls activity-comparison-custom-controls">
      <label><span>区间 A 开始</span><input v-model="leftCustom.start" type="date" /></label>
      <label><span>区间 A 结束</span><input v-model="leftCustom.end" type="date" /></label>
      <span class="activity-comparison-versus"><Scale :size="17" />对比</span>
      <label><span>区间 B 开始</span><input v-model="rightCustom.start" type="date" /></label>
      <label><span>区间 B 结束</span><input v-model="rightCustom.end" type="date" /></label>
      <button type="button" class="activity-comparison-run" :disabled="loading" @click="runComparison"><RefreshCw :size="15" :class="{ spinning: loading }" />开始对比</button>
    </div>

    <div v-if="loading" class="admin-loading-state activity-comparison-loading"><LoaderCircle :size="21" class="spinning" /><span>正在对齐两个区间的经营口径</span></div>
    <EmptyState v-else-if="error" title="暂未形成对比" :detail="error" :icon="GitCompareArrows" />
    <template v-else-if="comparedPeriods && metrics.length">
      <div class="activity-comparison-periods">
        <div><span>活动 / 区间 A</span><strong>{{ comparedPeriods.left.label }}</strong><small>{{ comparedPeriods.left.range.start }} 至 {{ comparedPeriods.left.range.end }} · 经营数据有效 {{ coverage.left }} / {{ coverage.leftExpected }} 天</small></div>
        <div><span>活动 / 区间 B</span><strong>{{ comparedPeriods.right.label }}</strong><small>{{ comparedPeriods.right.range.start }} 至 {{ comparedPeriods.right.range.end }} · 经营数据有效 {{ coverage.right }} / {{ coverage.rightExpected }} 天</small></div>
      </div>
      <div class="activity-comparison-summary-grid">
        <div class="activity-comparison-chart">
          <div class="activity-comparison-chart-toolbar"><span>选择指标查看规模差异</span><select v-model="selectedMetricKey"><option v-for="item in metrics" :key="item.key" :value="item.key">{{ item.group }} · {{ item.label }}</option></select></div>
          <BusinessChart :option="chartOption" :ariaLabel="`${selectedMetric?.label || '活动指标'}双区间对比`" :height="270" />
        </div>
        <div class="activity-comparison-reading">
          <strong>对比口径</strong>
          <span>金额、访客、会员和客服规模指标优先按各模块有效日归一。</span>
          <span>活动长度或覆盖天数不一致时，不用区间总额直接判断活动优劣。</span>
          <span>推广成交为平台 15 天归因，只表示归因表现，不代表活动因果增量。</span>
        </div>
      </div>
      <div class="activity-comparison-table">
        <div class="activity-comparison-row activity-comparison-table-head"><span>指标</span><span>区间 A</span><span>区间 B</span><span>A 较 B</span><span>口径</span></div>
        <template v-for="group in groupedMetrics" :key="group.group">
          <div class="activity-comparison-group">{{ group.group }}</div>
          <div v-for="item in group.rows" :key="item.key" class="activity-comparison-row">
            <strong>{{ item.label }}</strong><span>{{ formatValue(item.left, item.format) }}</span><span>{{ formatValue(item.right, item.format) }}</span><span class="activity-comparison-change" :class="changeClass(item)">{{ changeLabel(item) }}</span><small>{{ item.note }}</small>
          </div>
        </template>
      </div>
    </template>
  </section>
</template>
