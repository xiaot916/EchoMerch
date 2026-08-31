<script setup lang="ts">
import { computed } from "vue"
import { BarChart3, CircleDollarSign, Eye, LoaderCircle, MousePointerClick } from "lucide-vue-next"

import BusinessChart from "@/components/BusinessChart.vue"
import EmptyState from "@/components/EmptyState.vue"
import MetricCard from "@/components/MetricCard.vue"
import { useDashboard } from "@/composables/useDashboard"
import { currency, number, ratio } from "@/lib/format"

const { dashboard, loading } = useDashboard()
const content = computed(() => dashboard.value?.analysis?.content)
const dailyRows = computed(() => [...(content.value?.daily_metrics ?? [])].reverse())
const funnelStages = computed(() => {
  if (!content.value) return []
  const rows = [
    { name: "曝光", value: content.value.exposure_users },
    { name: "内容查看", value: content.value.viewers },
    { name: "商品点击", value: content.value.product_click_users },
    { name: "加购", value: content.value.add_cart_users },
    { name: "种草成交", value: content.value.paid_buyers },
  ].filter((item, index) => index > 0 || item.value > 0)
  return rows.map((item, index) => ({ ...item, conversion: index && rows[index - 1].value ? item.value / rows[index - 1].value * 100 : null }))
})
function stepRate(value: number, denominator: number): number | null { return denominator ? value / denominator * 100 : null }
function uvValue(amount: number, viewers: number): number | null { return viewers ? amount / viewers : null }
const funnelOption = computed(() => ({
  color: ["#a8d9c4", "#6bbd99", "#e2a447", "#5b8def"],
  tooltip: { trigger: "item", formatter: (params: { name: string; value: number; data: { conversion: number | null } }) => `${params.name}<br/>人数：${number(params.value)}${params.data.conversion == null ? "" : `<br/>环节转化：${ratio(params.data.conversion)}`}` },
  series: [{ type: "funnel", left: "8%", top: 20, bottom: 20, width: "84%", min: 0, max: Math.max(...funnelStages.value.map((item) => item.value), 1), minSize: "14%", maxSize: "100%", sort: "none", gap: 3, label: { show: true, position: "inside", color: "#264235", fontSize: 10, formatter: (params: { name: string; value: number; data: { conversion: number | null } }) => `${params.name} ${number(params.value)}${params.data.conversion == null ? "" : `\n${ratio(params.data.conversion)}`}` }, data: funnelStages.value }],
}))
const trendOption = computed(() => ({
  color: ["#35a979", "#5b8def"], tooltip: { trigger: "axis", formatter: (params: Array<{ axisValue: string; seriesName: string; value: number }>) => params.length ? `<strong>${params[0].axisValue}</strong><br/>${params.map((item) => `${item.seriesName}：${item.seriesName.includes("金额") ? currency(Number(item.value)) : `${number(Number(item.value))} 人`}`).join("<br/>")}` : "" }, legend: { bottom: 0, data: ["内容查看人数", "种草成交金额"] }, grid: { left: 58, right: 24, top: 22, bottom: 54 },
  xAxis: { type: "category", data: content.value?.daily_metrics.map((item) => item.stat_date.slice(5)) ?? [] },
  yAxis: [{ type: "value", splitLine: { lineStyle: { color: "#edf1ef" } } }, { type: "value", axisLabel: { formatter: "¥{value}" } }],
  series: [
    { name: "内容查看人数", type: "bar", barMaxWidth: 24, data: content.value?.daily_metrics.map((item) => item.viewers) ?? [] },
    { name: "种草成交金额", type: "line", yAxisIndex: 1, smooth: true, data: content.value?.daily_metrics.map((item) => item.paid_amount) ?? [] },
  ],
}))
</script>

<template>
  <template v-if="dashboard && content">
    <section class="business-page-heading"><div><p>内容运营 / 触达与种草</p><h1>内容概览</h1><span>把内容曝光、商品点击、加购和成交放到同一条链路中，区分热度与实际带货。</span></div><span class="data-definition-badge">成交为内容归因口径</span></section>
    <section class="metrics-grid module-metrics">
      <MetricCard label="内容查看人数" :value="number(content.viewers)" detail="内容触达用户" :icon="Eye" tone="blue" scope="区间累计" />
      <MetricCard label="商品点击人数" :value="number(content.product_click_users)" :detail="`点击率 ${ratio(content.product_click_rate)}`" :icon="MousePointerClick" tone="teal" scope="区间累计" />
      <MetricCard label="种草成交金额" :value="currency(content.paid_amount)" :detail="`${number(content.paid_buyers)} 位成交买家`" :icon="CircleDollarSign" tone="amber" scope="区间累计" />
      <MetricCard label="内容互动率" :value="ratio(content.interaction_rate)" :detail="`${number(content.interaction_count)} 次互动`" :icon="BarChart3" tone="coral" scope="区间累计" />
    </section>
    <section class="decision-chart-grid"><article class="panel"><div class="panel-heading"><div><p>内容漏斗</p><h2>从查看到种草成交</h2></div></div><BusinessChart :option="funnelOption" ariaLabel="内容查看商品点击加购成交漏斗" :height="340" /></article><article class="panel"><div class="panel-heading"><div><p>日趋势</p><h2>内容触达与成交变化</h2></div></div><BusinessChart :option="trendOption" ariaLabel="内容触达和种草成交趋势图" :height="340" /></article></section>
    <section class="panel content-daily-panel"><div class="panel-heading"><div><p>日级效率</p><h2>查看、点击、加购与成交承接</h2></div><span class="panel-action">{{ dailyRows.length }} 个统计日</span></div><div class="content-daily-table"><div class="content-daily-row content-daily-head"><span>日期</span><span>查看人数</span><span>商品点击 / 点击率</span><span>加购 / 点击后加购</span><span>成交买家 / 点击成交</span><span>成交金额</span><span>查看 UV 价值</span></div><div v-for="item in dailyRows" :key="item.stat_date" class="content-daily-row"><strong>{{ item.stat_date }}</strong><span>{{ number(item.viewers) }}</span><div><b>{{ number(item.product_click_users) }}</b><small>{{ stepRate(item.product_click_users, item.viewers) == null ? '--' : ratio(stepRate(item.product_click_users, item.viewers) || 0) }}</small></div><div><b>{{ number(item.add_cart_users) }}</b><small>{{ stepRate(item.add_cart_users, item.product_click_users) == null ? '--' : ratio(stepRate(item.add_cart_users, item.product_click_users) || 0) }}</small></div><div><b>{{ number(item.paid_buyers) }}</b><small>{{ stepRate(item.paid_buyers, item.product_click_users) == null ? '--' : ratio(stepRate(item.paid_buyers, item.product_click_users) || 0) }}</small></div><b>{{ currency(item.paid_amount) }}</b><em>{{ uvValue(item.paid_amount, item.viewers) == null ? '--' : currency(uvValue(item.paid_amount, item.viewers) || 0) }}</em></div></div><p class="panel-footnote">当前内容源只有店铺日级概览，没有内容 ID、素材 ID 与承接商品明细，因此页面先定位日期级漏斗掉点；具体内容和商品下钻标记为待补采，不用日级汇总伪造对象结论。</p></section>
  </template>
  <section v-else-if="loading" class="loading-panel"><LoaderCircle :size="26" class="spinning" /><span>正在读取内容分析</span></section>
  <EmptyState v-else title="暂无内容分析数据" detail="当前日期范围没有内容概览记录。" :icon="BarChart3" />
</template>

<style scoped>
.content-daily-panel { min-width: 0; overflow: hidden; }.content-daily-table { margin-top: 12px; overflow-x: auto; }.content-daily-row { display: grid; min-width: 850px; grid-template-columns: 1fr .8fr 1fr 1fr 1.1fr 1fr .9fr; min-height: 44px; align-items: center; gap: 11px; border-bottom: 1px solid #edf2ef; color: #687a70; font-size: 10px; text-align: right; }.content-daily-row > :first-child { text-align: left; }.content-daily-row > div { display: grid; gap: 2px; }.content-daily-row strong, .content-daily-row b { color: #40564b; font-weight: 650; }.content-daily-row small { color: #98a59e; font-size: 8px; }.content-daily-row em { color: #167b55; font-style: normal; font-weight: 700; }.content-daily-head { min-height: 32px; color: #98a59e; font-size: 9px; }.content-daily-head > :not(:first-child) { text-align: right; }
</style>
