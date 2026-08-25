<script setup lang="ts">
import { computed } from "vue"
import { AlertTriangle, CircleDollarSign, LoaderCircle, Percent, UserRoundPlus, UsersRound } from "lucide-vue-next"

import BusinessChart from "@/components/BusinessChart.vue"
import EmptyState from "@/components/EmptyState.vue"
import MetricCard from "@/components/MetricCard.vue"
import { useDashboard } from "@/composables/useDashboard"
import { currency, number, ratio } from "@/lib/format"

const { dashboard, loading } = useDashboard()
const value = computed(() => dashboard.value?.analysis?.new_customer_discount)
const missingDays = computed(() => value.value?.daily_metrics.filter((item) => item.record_status === "missing") ?? [])
const partialDays = computed(() => value.value?.daily_metrics.filter((item) => item.record_status === "partial") ?? [])
const completeDays = computed(() => value.value?.daily_metrics.filter((item) => item.record_status === "complete") ?? [])
const trendOption = computed(() => ({
  color: ["#5b8def", "#35a979"], tooltip: { trigger: "axis", formatter: (params: Array<{ axisValue: string; seriesName: string; value: number | null; dataIndex: number }>) => { if (!params.length) return ""; const metric = value.value?.daily_metrics[params[0].dataIndex]; if (metric?.record_status === "missing") return `<strong>${params[0].axisValue}</strong><br/>未采集到该日新客礼金记录`; if (metric?.record_status === "partial") return `<strong>${params[0].axisValue}</strong><br/>平台未返回礼金活动指标，仅返回全店新客对照`; return `<strong>${params[0].axisValue}</strong><br/>${params.filter((item) => item.value !== null).map((item) => `${item.seriesName}：${item.seriesName.includes("金额") ? currency(Number(item.value)) : `${number(Number(item.value))} 人`}`).join("<br/>")}` } }, legend: { bottom: 0, data: ["商品新访客", "新客支付人数", "新客支付金额"] }, grid: { left: 58, right: 24, top: 22, bottom: 54 },
  xAxis: { type: "category", data: value.value?.daily_metrics.map((item) => item.stat_date.slice(5)) ?? [] },
  yAxis: [{ type: "value", splitLine: { lineStyle: { color: "#edf1ef" } } }, { type: "value", axisLabel: { formatter: "¥{value}" } }],
  series: [
    { name: "商品新访客", type: "bar", barMaxWidth: 18, data: value.value?.daily_metrics.map((item) => item.record_status === "complete" ? item.product_new_visitors : null) ?? [] },
    { name: "新客支付人数", type: "line", connectNulls: false, smooth: true, data: value.value?.daily_metrics.map((item) => item.record_status === "complete" ? item.paid_buyers : null) ?? [] },
    { name: "新客支付金额", type: "line", yAxisIndex: 1, connectNulls: false, smooth: true, data: value.value?.daily_metrics.map((item) => item.record_status === "complete" ? item.paid_amount : null) ?? [] },
  ],
}))
const compareOption = computed(() => ({
  color: ["#e2a447"], tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (item: number) => `${Number(item).toFixed(2)}%` }, grid: { left: 98, right: 30, top: 24, bottom: 34 }, xAxis: { type: "value", min: 0, max: 100, axisLabel: { formatter: "{value}%" }, splitLine: { lineStyle: { color: "#edf1ef" } } }, yAxis: { type: "category", data: ["支付金额贡献", "支付买家贡献"] }, series: [{ name: "新客礼金贡献占比", type: "bar", barMaxWidth: 24, data: [value.value?.amount_share ?? 0, value.value?.buyer_share ?? 0] }] }))
</script>

<template>
  <template v-if="dashboard && value">
    <section class="business-page-heading"><div><p>营销活动 / 新客礼金</p><h1>新客礼金</h1><span>对照商品新访客和全店新客成交，判断礼金触达带来的真实新增贡献。</span></div><span class="data-definition-badge">新客口径对照，不等同优惠券成本 ROI</span></section>
    <section v-if="missingDays.length || partialDays.length" class="new-customer-coverage-warning"><AlertTriangle :size="18" /><div><strong>当前范围只有 {{ completeDays.length }} 天礼金活动指标完整</strong><span v-if="partialDays.length">{{ partialDays.map((item) => item.stat_date.slice(5)).join("、") }}：平台接口只返回全店新客对照，未返回礼金活动指标。</span><span v-if="missingDays.length">{{ missingDays.map((item) => item.stat_date.slice(5)).join("、") }}：没有采集到该日记录。</span><small>缺失和未返回均按断点显示，不计作真实 0，也不纳入活动转化与贡献汇总。</small></div></section>
    <section class="metrics-grid module-metrics"><MetricCard label="商品新访客" :value="number(value.product_new_visitors)" detail="商品维度新访客" :icon="UsersRound" tone="blue" scope="区间累计" /><MetricCard label="新客支付金额" :value="currency(value.paid_amount)" :detail="`${number(value.paid_buyers)} 位支付买家`" :icon="CircleDollarSign" tone="teal" scope="区间累计" /><MetricCard label="新客转化率" :value="ratio(value.conversion_rate)" detail="新客支付人数 / 商品新访客" :icon="Percent" tone="amber" scope="区间累计" /><MetricCard label="全店新客金额占比" :value="ratio(value.amount_share)" :detail="`买家占比 ${ratio(value.buyer_share)}`" :icon="UserRoundPlus" tone="coral" scope="区间累计" /></section>
    <section class="decision-chart-grid"><article class="panel"><div class="panel-heading"><div><p>新客趋势</p><h2>触达、支付与成交金额</h2></div><span class="panel-action">{{ completeDays.length }} / {{ value.daily_metrics.length }} 天完整</span></div><BusinessChart :option="trendOption" ariaLabel="新客礼金新访客和成交趋势图" :height="340" /></article><article class="panel"><div class="panel-heading"><div><p>贡献对照</p><h2>新客礼金对全店新客的贡献</h2></div></div><BusinessChart :option="compareOption" ariaLabel="新客礼金支付金额和买家贡献占比图" :height="340" /></article></section>
  </template>
  <section v-else-if="loading" class="loading-panel"><LoaderCircle :size="26" class="spinning" /><span>正在读取新客礼金分析</span></section>
  <EmptyState v-else title="暂无新客礼金数据" detail="当前日期范围没有新客礼金日报记录。" :icon="UserRoundPlus" />
</template>

<style scoped>
.new-customer-coverage-warning { display: flex; align-items: flex-start; gap: 10px; border: 1px solid #efd9a8; border-radius: 6px; padding: 13px 15px; color: #a16b18; background: #fffaf0; }.new-customer-coverage-warning > svg { flex: 0 0 auto; margin-top: 2px; }.new-customer-coverage-warning div { display: grid; gap: 4px; }.new-customer-coverage-warning strong { color: #76511b; font-size: 12px; }.new-customer-coverage-warning span, .new-customer-coverage-warning small { color: #9a762f; font-size: 10px; line-height: 1.55; }.new-customer-coverage-warning small { color: #8b8069; }
</style>
