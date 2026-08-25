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
const funnelOption = computed(() => ({
  color: ["#a8d9c4", "#6bbd99", "#e2a447", "#5b8def"],
  tooltip: { trigger: "item", valueFormatter: (value: number) => number(Number(value)) },
  series: [{ type: "funnel", left: "8%", top: 20, bottom: 20, width: "84%", min: 0, max: Math.max(content.value?.viewers ?? 0, 1), minSize: "14%", maxSize: "100%", sort: "descending", gap: 3, label: { show: true, position: "inside", color: "#264235", fontSize: 11 }, data: content.value ? [
    { name: "内容查看", value: content.value.viewers },
    { name: "商品点击", value: content.value.product_click_users },
    { name: "加购", value: content.value.add_cart_users },
    { name: "种草成交", value: content.value.paid_buyers },
  ] : [] }],
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
  </template>
  <section v-else-if="loading" class="loading-panel"><LoaderCircle :size="26" class="spinning" /><span>正在读取内容分析</span></section>
  <EmptyState v-else title="暂无内容分析数据" detail="当前日期范围没有内容概览记录。" :icon="BarChart3" />
</template>
