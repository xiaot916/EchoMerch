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
const dailyRows = computed(() => [...(value.value?.daily_metrics ?? [])].reverse())
function dailyConversion(visitors: number | null, buyers: number | null): number | null { return visitors && buyers != null ? buyers / visitors * 100 : null }
function dailyShare(value: number | null, total: number | null): number | null { return total && value != null ? value / total * 100 : null }
function statusLabel(status: "complete" | "partial" | "missing"): string { return status === "complete" ? "完整" : status === "partial" ? "部分字段" : "未采集" }
const trendOption = computed(() => ({
  color: ["#5b8def", "#35a979"], tooltip: { trigger: "axis", formatter: (params: Array<{ axisValue: string; seriesName: string; value: number | null; dataIndex: number }>) => { if (!params.length) return ""; const metric = value.value?.daily_metrics[params[0].dataIndex]; if (metric?.record_status === "missing") return `<strong>${params[0].axisValue}</strong><br/>未采集到该日新客折扣记录`; if (metric?.record_status === "partial") return `<strong>${params[0].axisValue}</strong><br/>平台未返回折扣活动指标，仅返回全店新客对照`; return `<strong>${params[0].axisValue}</strong><br/>${params.filter((item) => item.value !== null).map((item) => `${item.seriesName}：${item.seriesName.includes("金额") ? currency(Number(item.value)) : `${number(Number(item.value))} 人`}`).join("<br/>")}` } }, legend: { bottom: 0, data: ["商品新访客", "新客支付人数", "新客支付金额"] }, grid: { left: 58, right: 24, top: 22, bottom: 54 },
  xAxis: { type: "category", data: value.value?.daily_metrics.map((item) => item.stat_date.slice(5)) ?? [] },
  yAxis: [{ type: "value", splitLine: { lineStyle: { color: "#edf1ef" } } }, { type: "value", axisLabel: { formatter: "¥{value}" } }],
  series: [
    { name: "商品新访客", type: "bar", barMaxWidth: 18, data: value.value?.daily_metrics.map((item) => item.record_status === "complete" ? item.product_new_visitors : null) ?? [] },
    { name: "新客支付人数", type: "line", connectNulls: false, smooth: true, data: value.value?.daily_metrics.map((item) => item.record_status === "complete" ? item.paid_buyers : null) ?? [] },
    { name: "新客支付金额", type: "line", yAxisIndex: 1, connectNulls: false, smooth: true, data: value.value?.daily_metrics.map((item) => item.record_status === "complete" ? item.paid_amount : null) ?? [] },
  ],
}))
const compareOption = computed(() => ({
  color: ["#e2a447"], tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (item: number) => `${Number(item).toFixed(2)}%` }, grid: { left: 98, right: 30, top: 24, bottom: 34 }, xAxis: { type: "value", min: 0, max: 100, axisLabel: { formatter: "{value}%" }, splitLine: { lineStyle: { color: "#edf1ef" } } }, yAxis: { type: "category", data: ["支付金额贡献", "支付买家贡献"] }, series: [{ name: "新客折扣贡献占比", type: "bar", barMaxWidth: 24, data: [value.value?.amount_share ?? 0, value.value?.buyer_share ?? 0] }] }))
</script>

<template>
  <template v-if="dashboard && value">
    <section class="business-page-heading"><div><p>营销活动 / 新客折扣</p><h1>新客折扣</h1><span>对照商品新访客和全店新客成交，判断折扣触达带来的真实新增贡献。</span></div><span class="data-definition-badge">新客口径对照，不等同优惠券成本 ROI</span></section>
    <section v-if="missingDays.length || partialDays.length" class="new-customer-coverage-warning"><AlertTriangle :size="18" /><div><strong>当前范围只有 {{ completeDays.length }} 天折扣活动指标完整</strong><span v-if="partialDays.length">{{ partialDays.map((item) => item.stat_date.slice(5)).join("、") }}：平台接口只返回全店新客对照，未返回折扣活动指标。</span><span v-if="missingDays.length">{{ missingDays.map((item) => item.stat_date.slice(5)).join("、") }}：没有采集到该日记录。</span><small>缺失和未返回均按断点显示，不计作真实 0，也不纳入活动转化与贡献汇总。</small></div></section>
    <section class="metrics-grid module-metrics"><MetricCard label="商品新访客" :value="number(value.product_new_visitors)" detail="商品维度新访客" :icon="UsersRound" tone="blue" scope="区间累计" /><MetricCard label="新客支付金额" :value="currency(value.paid_amount)" :detail="`${number(value.paid_buyers)} 位支付买家`" :icon="CircleDollarSign" tone="teal" scope="区间累计" /><MetricCard label="新客转化率" :value="ratio(value.conversion_rate)" detail="新客支付人数 / 商品新访客" :icon="Percent" tone="amber" scope="区间累计" /><MetricCard label="全店新客金额占比" :value="ratio(value.amount_share)" :detail="`买家占比 ${ratio(value.buyer_share)}`" :icon="UserRoundPlus" tone="coral" scope="区间累计" /></section>
    <section class="decision-chart-grid"><article class="panel"><div class="panel-heading"><div><p>新客趋势</p><h2>触达、支付与成交金额</h2></div><span class="panel-action">{{ completeDays.length }} / {{ value.daily_metrics.length }} 天完整</span></div><BusinessChart :option="trendOption" ariaLabel="新客折扣新访客和成交趋势图" :height="340" /></article><article class="panel"><div class="panel-heading"><div><p>贡献对照</p><h2>新客折扣对全店新客的贡献</h2></div></div><BusinessChart :option="compareOption" ariaLabel="新客折扣支付金额和买家贡献占比图" :height="340" /></article></section>
    <section class="panel new-customer-daily-panel"><div class="panel-heading"><div><p>日级核对</p><h2>覆盖、转化与全店新客贡献</h2></div><span class="panel-action">{{ dailyRows.length }} 个统计日</span></div><div class="new-customer-daily-table"><div class="new-customer-daily-row new-customer-daily-head"><span>日期 / 状态</span><span>商品新访客</span><span>支付买家</span><span>活动转化</span><span>支付金额</span><span>全店新客买家</span><span>买家贡献</span><span>金额贡献</span></div><div v-for="item in dailyRows" :key="item.stat_date" class="new-customer-daily-row" :class="`is-${item.record_status}`"><div><strong>{{ item.stat_date }}</strong><small>{{ statusLabel(item.record_status) }}</small></div><span>{{ item.product_new_visitors == null ? '--' : number(item.product_new_visitors) }}</span><span>{{ item.paid_buyers == null ? '--' : number(item.paid_buyers) }}</span><em>{{ dailyConversion(item.product_new_visitors, item.paid_buyers) == null ? '--' : ratio(dailyConversion(item.product_new_visitors, item.paid_buyers) || 0) }}</em><b>{{ item.paid_amount == null ? '--' : currency(item.paid_amount) }}</b><span>{{ item.shop_paid_buyers == null ? '--' : number(item.shop_paid_buyers) }}</span><em>{{ dailyShare(item.paid_buyers, item.shop_paid_buyers) == null ? '--' : ratio(dailyShare(item.paid_buyers, item.shop_paid_buyers) || 0) }}</em><em>{{ dailyShare(item.paid_amount, item.shop_paid_amount) == null ? '--' : ratio(dailyShare(item.paid_amount, item.shop_paid_amount) || 0) }}</em></div></div><p class="panel-footnote">当前源没有优惠成本、客户 ID 和二购订单，页面只判断触达、首购成交与全店新客贡献；CAC、30/60 天二购和回本周期由 AI 标记为待补数据，不按 0 展示。</p></section>
  </template>
  <section v-else-if="loading" class="loading-panel"><LoaderCircle :size="26" class="spinning" /><span>正在读取新客折扣分析</span></section>
  <EmptyState v-else title="暂无新客折扣数据" detail="当前日期范围没有新客折扣日报记录。" :icon="UserRoundPlus" />
</template>

<style scoped>
.new-customer-coverage-warning { display: flex; align-items: flex-start; gap: 10px; border: 1px solid #efd9a8; border-radius: 6px; padding: 13px 15px; color: #a16b18; background: #fffaf0; }.new-customer-coverage-warning > svg { flex: 0 0 auto; margin-top: 2px; }.new-customer-coverage-warning div { display: grid; gap: 4px; }.new-customer-coverage-warning strong { color: #76511b; font-size: 12px; }.new-customer-coverage-warning span, .new-customer-coverage-warning small { color: #9a762f; font-size: 10px; line-height: 1.55; }.new-customer-coverage-warning small { color: #8b8069; }
.new-customer-daily-panel { min-width: 0; overflow: hidden; }.new-customer-daily-table { margin-top: 12px; overflow-x: auto; }.new-customer-daily-row { display: grid; min-width: 940px; grid-template-columns: 1.05fr repeat(7, .9fr); min-height: 44px; align-items: center; gap: 10px; border-bottom: 1px solid #edf2ef; color: #687970; font-size: 10px; text-align: right; }.new-customer-daily-row > :first-child { text-align: left; }.new-customer-daily-row > div { display: grid; gap: 3px; }.new-customer-daily-row strong, .new-customer-daily-row b { color: #40564b; font-weight: 650; }.new-customer-daily-row small { color: #98a49d; font-size: 8px; }.new-customer-daily-row em { color: #177a55; font-style: normal; font-weight: 650; }.new-customer-daily-row.is-partial { background: #fffaf0; }.new-customer-daily-row.is-missing { color: #a39070; background: #fcfaf6; }.new-customer-daily-head { min-height: 32px; color: #98a49d; font-size: 9px; }.new-customer-daily-head > :not(:first-child) { text-align: right; }
</style>
