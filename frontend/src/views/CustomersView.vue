<script setup lang="ts">
import { computed } from "vue"
import { CircleDollarSign, LoaderCircle, Repeat2, UserRoundCheck, UserRoundSearch } from "lucide-vue-next"

import BusinessChart from "@/components/BusinessChart.vue"
import EmptyState from "@/components/EmptyState.vue"
import MetricCard from "@/components/MetricCard.vue"
import { useDashboard } from "@/composables/useDashboard"
import { currency, number, ratio } from "@/lib/format"

const { dashboard, loading } = useDashboard()
const customer = computed(() => dashboard.value?.analysis?.customer)

const amountTrendOption = computed(() => ({
  color: ["#5b8def", "#35a979"],
  tooltip: { trigger: "axis", valueFormatter: (value: number) => currency(Number(value)) },
  legend: { bottom: 0, data: ["新访成交金额", "老客复购金额"] },
  grid: { left: 58, right: 24, top: 24, bottom: 54 },
  xAxis: { type: "category", data: customer.value?.daily_metrics.map((item) => item.stat_date.slice(5)) ?? [] },
  yAxis: { type: "value", axisLabel: { formatter: "¥{value}" }, splitLine: { lineStyle: { color: "#edf1ef" } } },
  series: [
    { name: "新访成交金额", type: "line", smooth: true, areaStyle: { opacity: 0.08 }, data: customer.value?.daily_metrics.map((item) => item.new_paid_amount) ?? [] },
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

const segmentPaidOption = computed(() => {
  const segments = customer.value?.segments ?? []
  return {
    color: ["#5b8def", "#35a979", "#e0a54b"],
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (value: number) => currency(Number(value)) },
    grid: { left: 88, right: 24, top: 20, bottom: 28 },
    xAxis: { type: "value", splitLine: { lineStyle: { color: "#edf1ef" } } },
    yAxis: { type: "category", data: segments.map((item) => item.label).reverse() },
    series: [{ name: "成交金额", type: "bar", colorBy: "data", barMaxWidth: 24, data: segments.map((item) => item.paid_amount).reverse() }],
  }
})
</script>

<template>
  <template v-if="dashboard && customer">
    <section class="business-page-heading"><div><h1>客户概况</h1></div></section>

    <section class="metrics-grid module-metrics">
      <MetricCard label="店铺客户数" :value="number(customer.shop_customers)" :detail="customer.shop_customers_stat_date ? `数据截至 ${customer.shop_customers_stat_date}` : '暂无有效数据'" :icon="UserRoundCheck" tone="blue" definition="取所选范围内最近一个有值日期的店铺客户数。" />
      <MetricCard label="新访成交金额" :value="currency(customer.new_customer_paid_amount)" :detail="`${number(customer.new_customer_paid_buyers)} 人成交 · ${ratio(customer.new_customer_conversion_rate)}`" :icon="CircleDollarSign" tone="teal" />
      <MetricCard label="老客复购金额" :value="currency(customer.repeat_customer_paid_amount)" :detail="`${number(customer.repeat_customers)} 人复购`" :icon="Repeat2" tone="amber" definition="复购金额按平台已购回访支付金额占比计算。" />
      <MetricCard label="未购回访转化" :value="ratio(customer.no_purchase_conversion_rate)" :detail="`${number(customer.no_purchase_buyers)} / ${number(customer.no_purchase_returners)} 人`" :icon="UserRoundSearch" tone="coral" />
    </section>

    <section class="decision-chart-grid">
      <article class="panel"><div class="panel-heading"><div><h2>成交金额趋势</h2></div></div><BusinessChart :option="amountTrendOption" ariaLabel="新访成交与老客复购金额趋势图" :height="330" /></article>
      <article class="panel"><div class="panel-heading"><div><h2>客户转化</h2></div></div><BusinessChart :option="segmentOption" ariaLabel="新访未购回访和已购回访成交对比图" :height="330" /></article>
    </section>

    <section class="decision-chart-grid">
      <article class="panel"><div class="panel-heading"><div><h2>成交金额贡献</h2></div><span class="panel-action">区间累计</span></div><BusinessChart :option="segmentPaidOption" ariaLabel="三类客户成交金额贡献图" :height="300" /></article>
      <article class="panel customer-segment-panel"><div class="panel-heading"><div><h2>客户结构</h2></div><span class="panel-action">区间人次</span></div><div class="customer-segment-table"><div class="customer-segment-row customer-segment-head"><span>人群</span><span>触达</span><span>成交</span><span>转化</span><span>客单</span><span>会员 / 粉丝</span></div><div v-for="item in customer.segments" :key="item.key" class="customer-segment-row"><strong>{{ item.label }}</strong><span>{{ number(item.reached) }}</span><span>{{ number(item.buyers) }}</span><span>{{ ratio(item.conversion_rate) }}</span><span>{{ currency(item.unit_price) }}</span><span>{{ ratio(item.member_rate) }} / {{ ratio(item.fan_rate) }}</span></div></div><p class="panel-footnote">触达和成交为所选日期内每日人数累计，不是跨日去重人数。</p></article>
    </section>
  </template>
  <section v-else-if="loading" class="loading-panel"><LoaderCircle :size="26" class="spinning" /><span>正在读取…</span></section>
  <EmptyState v-else title="暂无客户数据" detail="当前日期范围没有客户概览记录。" :icon="UserRoundSearch" />
</template>

<style scoped>
.customer-segment-panel { overflow: hidden; }
.customer-segment-table { display: grid; }
.customer-segment-row { display: grid; grid-template-columns: minmax(86px, 1fr) repeat(4, minmax(76px, .8fr)) minmax(120px, 1.15fr); align-items: center; min-height: 54px; padding: 0 16px; border-bottom: 1px solid #edf2ee; color: #607168; font-size: 12px; }
.customer-segment-row:last-child { border-bottom: 0; }
.customer-segment-row strong { color: #30473a; font-weight: 700; }
.customer-segment-head { min-height: 40px; color: #89978f; background: #fbfdfc; font-size: 11px; }
.customer-segment-panel .panel-footnote { margin: 0; padding: 11px 16px; border-top: 1px solid #edf2ee; }
@media (max-width: 720px) { .customer-segment-table { overflow-x: auto; } .customer-segment-row { min-width: 650px; } }
</style>
