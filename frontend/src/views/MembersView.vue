<script setup lang="ts">
import { computed } from "vue"
import { CircleDollarSign, Crown, LoaderCircle, Repeat2, UserRoundPlus } from "lucide-vue-next"

import BusinessChart from "@/components/BusinessChart.vue"
import EmptyState from "@/components/EmptyState.vue"
import MetricCard from "@/components/MetricCard.vue"
import { useDashboard } from "@/composables/useDashboard"
import { currency, number, ratio } from "@/lib/format"

const { dashboard, loading } = useDashboard()
const member = computed(() => dashboard.value?.analysis?.member)

const assetOption = computed(() => ({
  color: ["#35a979"],
  tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (value: number) => number(Number(value)) },
  grid: { left: 98, right: 30, top: 20, bottom: 24 },
  xAxis: { type: "value", splitLine: { lineStyle: { color: "#edf1ef" } } },
  yAxis: { type: "category", data: ["沉默会员", "活跃未购", "首购会员", "2单复购", "高频复购"] },
  series: [{ type: "bar", barMaxWidth: 22, data: member.value ? [member.value.inactive_members, member.value.active_non_buyers, member.value.first_time_members, member.value.two_order_members, member.value.high_frequency_members] : [] }],
}))

const channelOption = computed(() => ({
  color: ["#5b8def", "#e2a447"],
  tooltip: { trigger: "axis", formatter: (params: Array<{ axisValue: string; seriesName: string; value: number }>) => params.length ? `<strong>${params[0].axisValue}</strong><br/>${params.map((item) => `${item.seriesName}：${item.seriesName.includes("转化") ? `${Number(item.value).toFixed(2)}%` : number(Number(item.value))}`).join("<br/>")}` : "" },
  legend: { bottom: 0, data: ["新增会员", "成交转化率"] },
  grid: { left: 52, right: 52, top: 22, bottom: 78 },
  xAxis: { type: "category", axisLabel: { rotate: 28 }, data: member.value?.channels.slice(0, 7).map((item) => item.channel_name) ?? [] },
  yAxis: [{ type: "value", splitLine: { lineStyle: { color: "#edf1ef" } } }, { type: "value", axisLabel: { formatter: "{value}%" } }],
  series: [
    { name: "新增会员", type: "bar", barMaxWidth: 24, data: member.value?.channels.slice(0, 7).map((item) => item.new_members) ?? [] },
    { name: "成交转化率", type: "line", yAxisIndex: 1, smooth: true, data: member.value?.channels.slice(0, 7).map((item) => item.recruit_conversion_rate) ?? [] },
  ],
}))

const trendOption = computed(() => ({
  color: ["#35a979", "#8f6bd6"], tooltip: { trigger: "axis", valueFormatter: (value: number) => currency(Number(value)) }, legend: { bottom: 0, data: ["会员成交金额", "会员复购金额"] },
  grid: { left: 58, right: 24, top: 22, bottom: 52 }, xAxis: { type: "category", data: member.value?.daily_metrics.map((item) => item.stat_date.slice(5)) ?? [] },
  yAxis: { type: "value", axisLabel: { formatter: "¥{value}" }, splitLine: { lineStyle: { color: "#edf1ef" } } },
  series: [
    { name: "会员成交金额", type: "line", smooth: true, areaStyle: { opacity: 0.08 }, data: member.value?.daily_metrics.map((item) => item.paid_amount) ?? [] },
    { name: "会员复购金额", type: "line", smooth: true, data: member.value?.daily_metrics.map((item) => item.repurchase_amount) ?? [] },
  ],
}))
</script>

<template>
  <template v-if="dashboard && member">
    <section class="business-page-heading"><div><h1>会员分析</h1></div><span class="data-definition-badge">会员总数与分层为最新有效日存量</span></section>
    <section class="metrics-grid module-metrics">
      <MetricCard label="会员总数" :value="number(member.total_members)" detail="最新有效日会员资产" :icon="Crown" tone="blue" scope="期末存量" />
      <MetricCard label="会员成交金额" :value="currency(member.paid_amount)" :detail="`${number(member.paid_members)} 位成交会员`" :icon="CircleDollarSign" tone="teal" scope="区间累计" />
      <MetricCard label="会员复购金额" :value="currency(member.repurchase_amount)" :detail="`${number(member.repurchase_members)} 位复购会员`" :icon="Repeat2" tone="amber" scope="区间累计" definition="会员复购率沿用平台会员分析口径，金额和人数为区间累计。" />
      <MetricCard label="新增会员" :value="number(member.new_members)" :detail="`成交转化 ${ratio(member.recruit_conversion_rate)}`" :icon="UserRoundPlus" tone="coral" scope="区间累计" />
    </section>
    <section class="decision-chart-grid member-decision-grid">
      <article class="panel"><div class="panel-heading"><div><p>资产分层</p><h2>会员生命周期结构</h2></div></div><BusinessChart :option="assetOption" ariaLabel="会员生命周期资产分层图" :height="340" /></article>
      <article class="panel"><div class="panel-heading"><div><p>招募渠道</p><h2>新增会员与成交转化</h2></div></div><BusinessChart :option="channelOption" ariaLabel="会员招募渠道新增和转化图" :height="340" /></article>
    </section>
    <section class="panel decision-wide-chart"><div class="panel-heading"><div><p>会员贡献</p><h2>成交与复购金额趋势</h2></div><span class="panel-action">平均复购周期 {{ member.repurchase_cycle.toFixed(1) }} 天</span></div><BusinessChart :option="trendOption" ariaLabel="会员成交与复购金额趋势图" :height="320" /></section>
  </template>
  <section v-else-if="loading" class="loading-panel"><LoaderCircle :size="26" class="spinning" /><span>正在读取会员分析</span></section>
  <EmptyState v-else title="暂无会员分析数据" detail="当前日期范围没有会员分析记录。" :icon="Crown" />
</template>
