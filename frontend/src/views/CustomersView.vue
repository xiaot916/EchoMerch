<script setup lang="ts">
import { computed } from "vue"
import { AlertTriangle, CircleDollarSign, LoaderCircle, Repeat2, Scale, UserRoundCheck, UserRoundSearch } from "lucide-vue-next"

import BusinessChart from "@/components/BusinessChart.vue"
import EmptyState from "@/components/EmptyState.vue"
import MetricCard from "@/components/MetricCard.vue"
import { useDashboard } from "@/composables/useDashboard"
import { currency, number, ratio } from "@/lib/format"
import type { DecisionMetric } from "@/types"

const { dashboard, loading } = useDashboard()
const customer = computed(() => dashboard.value?.analysis?.customer)
const derivedById = computed(() => new Map((customer.value?.derived_metrics ?? []).map((item) => [item.id, item])))
const customerDays = computed(() => customer.value?.daily_metrics.length ?? 0)

function derived(id: string): DecisionMetric | undefined { return derivedById.value.get(id) }
function derivedValue(id: string): number | null { return derived(id)?.status === "available" ? derived(id)?.value ?? null : null }
function optionalRatio(value: number | null | undefined): string { return value == null ? "暂无" : ratio(value) }
function metricStatus(item: DecisionMetric | undefined): string {
  if (!item) return "指标未返回"
  if (item.status === "inconsistent") return "依赖字段口径不一致"
  if (item.status === "unavailable") return item.note || "依赖字段不完整"
  return item.note || "客户有效日累计"
}
function metricValue(item: DecisionMetric): string {
  if (item.status !== "available" || item.value == null) return "暂无"
  if (item.unit === "currency") return currency(item.value)
  if (item.unit === "percent") return ratio(item.value)
  if (item.unit === "ratio") return item.value.toFixed(2)
  return number(item.value)
}

const amountTrendOption = computed(() => ({
  color: ["#5b8def", "#35a979"],
  tooltip: { trigger: "axis", valueFormatter: (value: number) => currency(Number(value)) },
  legend: { bottom: 0, data: ["首次购买金额", "老客复购金额"] },
  grid: { left: 58, right: 24, top: 24, bottom: 54 },
  xAxis: { type: "category", data: customer.value?.daily_metrics.map((item) => item.stat_date.slice(5)) ?? [] },
  yAxis: { type: "value", axisLabel: { formatter: "¥{value}" }, splitLine: { lineStyle: { color: "#edf1ef" } } },
  series: [
    { name: "首次购买金额", type: "line", smooth: true, areaStyle: { opacity: 0.08 }, data: customer.value?.daily_metrics.map((item) => item.first_purchase_paid_amount) ?? [] },
    { name: "老客复购金额", type: "line", smooth: true, areaStyle: { opacity: 0.08 }, data: customer.value?.daily_metrics.map((item) => item.repeat_paid_amount) ?? [] },
  ],
}))

const segmentOption = computed(() => {
  const daily = customer.value?.daily_metrics ?? []
  const sums = (key: "new_visitors" | "new_paid_buyers" | "no_purchase_returners" | "no_purchase_buyers" | "repeat_returners" | "repeat_buyers") => daily.reduce((total, item) => total + item[key], 0)
  return {
    color: ["#cfe9dc", "#35a979"],
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (value: number) => number(Number(value)) },
    legend: { bottom: 0, data: ["触达人群", "成交人群"] },
    grid: { left: 92, right: 28, top: 24, bottom: 48 },
    xAxis: { type: "value", splitLine: { lineStyle: { color: "#edf1ef" } } },
    yAxis: { type: "category", data: ["已购回访", "未购回访", "新访客户"] },
    series: [
      { name: "触达人群", type: "bar", barMaxWidth: 18, data: [sums("repeat_returners"), sums("no_purchase_returners"), sums("new_visitors")] },
      { name: "成交人群", type: "bar", barMaxWidth: 18, data: [sums("repeat_buyers"), sums("no_purchase_buyers"), sums("new_paid_buyers")] },
    ],
  }
})
</script>

<template>
  <template v-if="dashboard && customer">
    <section class="business-page-heading"><div><h1>客户概况</h1><p>先看完整首次购买与老客复购结构，再下钻平台三段人群漏斗。</p></div></section>

    <section v-if="customer.quality_warnings.length" class="customer-quality-warning"><AlertTriangle :size="18" /><div><strong>客户口径需要注意</strong><span v-for="warning in customer.quality_warnings" :key="warning">{{ warning }}</span></div></section>

    <section class="metrics-grid module-metrics">
      <MetricCard label="首次购买金额" :value="currency(derivedValue('first_purchase_paid_amount'))" :detail="`金额占比 ${optionalRatio(derivedValue('first_purchase_amount_share'))}`" :icon="CircleDollarSign" tone="blue" scope="客户有效日累计" :definition="metricStatus(derived('first_purchase_paid_amount'))" />
      <MetricCard label="老客复购金额" :value="currency(derivedValue('repeat_amount_share') === null ? null : customer.repeat_customer_paid_amount)" :detail="`金额占比 ${optionalRatio(derivedValue('repeat_amount_share'))}`" :icon="Repeat2" tone="teal" scope="客户有效日累计" :definition="metricStatus(derived('repeat_amount_share'))" />
      <MetricCard label="首次购买人数" :value="number(derivedValue('first_purchase_paid_buyers'))" :detail="`人数占比 ${optionalRatio(derivedValue('first_purchase_buyer_share'))}`" :icon="UserRoundCheck" tone="amber" scope="每日人数累计" :definition="metricStatus(derived('first_purchase_paid_buyers'))" />
      <MetricCard label="老客客单指数" :value="optionalRatio(derivedValue('repeat_unit_price_index'))" :detail="`首购 ${currency(derivedValue('first_purchase_unit_price'))} · 老客 ${currency(derivedValue('repeat_unit_price'))}`" :icon="Scale" tone="coral" definition="100% 表示老客与首次购买客单相同，高于 100% 表示老客客单更高。" />
    </section>

    <section class="customer-scope-strip"><span>客户有效数据 {{ customerDays }} 天</span><span>首次购买 = 总支付 - 老客复购</span><span>人数为每日累计，非跨日去重</span><span>店铺客户存量 {{ number(customer.shop_customers) }}{{ customer.shop_customers_stat_date ? ` · 截至 ${customer.shop_customers_stat_date}` : "" }}</span></section>

    <section class="decision-chart-grid">
      <article class="panel"><div class="panel-heading"><div><h2>首次购买与老客金额趋势</h2></div></div><BusinessChart :option="amountTrendOption" ariaLabel="首次购买与老客复购金额趋势图" :height="330" /></article>
      <article class="panel"><div class="panel-heading"><div><h2>平台三段人群转化</h2></div></div><BusinessChart :option="segmentOption" ariaLabel="新访未购回访和已购回访成交对比图" :height="330" /></article>
    </section>

    <section class="decision-chart-grid customer-detail-grid">
      <article class="panel customer-segment-panel"><div class="panel-heading"><div><h2>原始人群结构</h2></div><span class="panel-action">区间人次</span></div><div class="customer-segment-table"><div class="customer-segment-row customer-segment-head"><span>人群</span><span>触达</span><span>成交</span><span>转化</span><span>客单</span><span>会员 / 粉丝</span></div><div v-for="item in customer.segments" :key="item.key" class="customer-segment-row"><strong>{{ item.label }}</strong><span>{{ number(item.reached) }}</span><span>{{ number(item.buyers) }}</span><span>{{ ratio(item.conversion_rate) }}</span><span>{{ currency(item.paid_amount) }}</span><span>{{ ratio(item.member_rate) }} / {{ ratio(item.fan_rate) }}</span></div></div><p class="panel-footnote">新访成交只代表首次访问后成交；未购回访成交仍属于首次购买，因此不能只用新访成交代表全部新客。</p></article>
      <article class="panel customer-derived-panel"><div class="panel-heading"><div><h2>派生指标与对账</h2></div><span class="panel-action">公式可审计</span></div><div class="customer-derived-table"><div class="customer-derived-row customer-derived-head"><span>指标</span><span>结果</span><span>公式与状态</span></div><div v-for="item in customer.derived_metrics" :key="item.id" class="customer-derived-row"><strong>{{ item.label }}</strong><span :class="`status-${item.status}`">{{ metricValue(item) }}</span><div><b>{{ item.formula }}</b><small>{{ metricStatus(item) }}</small></div></div></div></article>
    </section>
  </template>
  <section v-else-if="loading" class="loading-panel"><LoaderCircle :size="26" class="spinning" /><span>正在读取…</span></section>
  <EmptyState v-else title="暂无客户数据" detail="当前日期范围没有客户概览记录。" :icon="UserRoundSearch" />
</template>

<style scoped>
.customer-quality-warning { display: flex; align-items: flex-start; gap: 10px; border: 1px solid #efd9a8; border-radius: 6px; padding: 13px 15px; color: #a16b18; background: #fffaf0; }.customer-quality-warning > svg { flex: 0 0 auto; margin-top: 2px; }.customer-quality-warning div { display: grid; gap: 4px; }.customer-quality-warning strong { color: #76511b; font-size: 12px; }.customer-quality-warning span { color: #916d2d; font-size: 10px; line-height: 1.55; }
.customer-scope-strip { display: flex; flex-wrap: wrap; gap: 7px; }.customer-scope-strip span { border: 1px solid #dfe9e3; border-radius: 5px; padding: 6px 9px; color: #667a6e; background: #f9fbfa; font-size: 10px; }
.customer-detail-grid { align-items: start; }.customer-segment-panel, .customer-derived-panel { overflow: hidden; }.customer-segment-table, .customer-derived-table { display: grid; }.customer-segment-row { display: grid; grid-template-columns: minmax(86px, 1fr) repeat(4, minmax(76px, .8fr)) minmax(120px, 1.15fr); align-items: center; min-height: 54px; padding: 0 16px; border-bottom: 1px solid #edf2ee; color: #607168; font-size: 12px; }.customer-segment-row:last-child, .customer-derived-row:last-child { border-bottom: 0; }.customer-segment-row strong, .customer-derived-row strong { color: #30473a; font-weight: 700; }.customer-segment-head, .customer-derived-head { min-height: 40px; color: #89978f; background: #fbfdfc; font-size: 11px; }.customer-segment-panel .panel-footnote { margin: 0; padding: 11px 16px; border-top: 1px solid #edf2ee; }
.customer-derived-row { display: grid; grid-template-columns: minmax(110px, .9fr) minmax(90px, .7fr) minmax(190px, 1.5fr); align-items: center; gap: 12px; min-height: 58px; padding: 7px 16px; border-bottom: 1px solid #edf2ee; color: #607168; font-size: 11px; }.customer-derived-row > span { color: #276b4e; font-weight: 750; }.customer-derived-row > span.status-unavailable { color: #8b958f; }.customer-derived-row > span.status-inconsistent { color: #b45f4f; }.customer-derived-row div { display: grid; gap: 3px; }.customer-derived-row b { color: #566c60; font-size: 10px; font-weight: 650; }.customer-derived-row small { color: #8a9991; font-size: 9px; line-height: 1.45; }
@media (max-width: 720px) { .customer-segment-table, .customer-derived-table { overflow-x: auto; }.customer-segment-row { min-width: 650px; }.customer-derived-row { min-width: 560px; } }
</style>
