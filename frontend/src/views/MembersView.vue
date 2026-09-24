<script setup lang="ts">
import { computed } from "vue"
import { AlertTriangle, CircleDollarSign, Crown, LoaderCircle, Repeat2, UserRoundPlus } from "lucide-vue-next"

import BusinessChart from "@/components/BusinessChart.vue"
import EmptyState from "@/components/EmptyState.vue"
import MetricCard from "@/components/MetricCard.vue"
import { useDashboard } from "@/composables/useDashboard"
import { currency, number, ratio, shortDate } from "@/lib/format"

const { dashboard, loading } = useDashboard()
const member = computed(() => dashboard.value?.analysis?.member)
const channelRows = computed(() => [...(member.value?.channels ?? [])].sort((left, right) => right.new_members - left.new_members))
const channelNewMemberTotal = computed(() => channelRows.value.reduce((total, item) => total + item.new_members, 0))
const largestChannel = computed(() => channelRows.value[0])
const largestChannelShare = computed(() => channelNewMemberTotal.value && largestChannel.value ? largestChannel.value.new_members / channelNewMemberTotal.value * 100 : 0)
const channelCoverageDiffers = computed(() => Boolean(member.value?.channel_latest_date && member.value?.overview_latest_date && member.value.channel_latest_date !== member.value.overview_latest_date))
function channelShare(value: number): number { return channelNewMemberTotal.value ? value / channelNewMemberTotal.value * 100 : 0 }

const assetOption = computed(() => ({
  color: ["#35a979"],
  tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (value: number) => number(Number(value)) },
  grid: { left: 98, right: 30, top: 20, bottom: 24 },
  xAxis: { type: "value", splitLine: { lineStyle: { color: "#edf1ef" } } },
  yAxis: { type: "category", data: ["沉默会员", "活跃未购", "首购会员", "2单复购", "高频复购"] },
  series: [{ type: "bar", barMaxWidth: 22, data: member.value ? [member.value.inactive_members, member.value.active_non_buyers, member.value.first_time_members, member.value.two_order_members, member.value.high_frequency_members] : [] }],
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
    <section class="business-page-heading"><div><h1>会员分析</h1></div></section>
    <section v-if="channelCoverageDiffers" class="member-data-warning" role="status"><AlertTriangle :size="16" /><div><strong>会员资产与渠道数据截止日不同</strong><span>资产与成交总览截至 {{ shortDate(member.overview_latest_date || '') }}，入会渠道截至 {{ shortDate(member.channel_latest_date || '') }}；两者分别展示，不强行对账。</span></div></section>
    <section class="metrics-grid module-metrics">
      <MetricCard v-if="member.asset_date" label="会员总数" :value="number(member.total_members)" :detail="`截至 ${shortDate(member.asset_date)} 的会员资产`" :icon="Crown" tone="blue" scope="期末存量" />
      <MetricCard label="会员成交金额" :value="currency(member.paid_amount)" :detail="`${number(member.paid_members)} 日成交会员人次`" :icon="CircleDollarSign" tone="teal" scope="区间累计" definition="人数为每日会员成交人数求和，可能包含跨日重复会员，不等于区间去重人数。" />
      <MetricCard label="会员复购金额" :value="currency(member.repurchase_amount)" :detail="`${number(member.repurchase_members)} 日复购会员人次`" :icon="Repeat2" tone="amber" scope="区间累计" definition="金额为区间累计；人数为每日复购会员数求和，可能包含跨日重复会员。" />
      <MetricCard label="新增会员" :value="number(member.new_members)" :detail="`成交转化 ${ratio(member.recruit_conversion_rate)}`" :icon="UserRoundPlus" tone="coral" scope="区间累计" />
    </section>
    <section class="decision-chart-grid member-decision-grid">
      <article class="panel"><div class="panel-heading"><div><p>资产分层</p><h2>会员生命周期结构</h2></div></div><BusinessChart v-if="member.asset_date" :option="assetOption" ariaLabel="会员生命周期资产分层图" :height="340" /><EmptyState v-else title="暂无会员资产快照" detail="当前日期范围没有可用的会员存量与分层数据。" /></article>
      <article class="panel member-channel-panel"><div class="panel-heading"><div><p>招募渠道</p><h2>来源集中度与成交质量</h2></div><span class="panel-action">渠道记录 {{ number(channelNewMemberTotal) }} 人</span></div><div class="member-channel-summary"><div><span>最大来源</span><strong>{{ largestChannel?.channel_name || '--' }}</strong><small>{{ number(largestChannel?.new_members || 0) }} 人 · 占渠道记录 {{ ratio(largestChannelShare) }}</small></div><div><span>渠道与总览差额</span><strong>{{ number(channelNewMemberTotal - member.new_members) }}</strong><small>来自截止日和平台模块口径差异，不解释为漏数</small></div></div><div class="member-channel-table"><div class="member-channel-row member-channel-head"><span>入会渠道</span><span>新增会员 / 占比</span><span>新会员成交</span><span>成交转化</span><span>成交金额</span></div><div v-for="item in channelRows" :key="item.channel_name" class="member-channel-row"><strong>{{ item.channel_name || '未分类' }}</strong><div><b>{{ number(item.new_members) }}</b><small>{{ ratio(channelShare(item.new_members)) }}</small></div><span>{{ number(item.paid_new_members) }}</span><em>{{ ratio(item.recruit_conversion_rate) }}</em><b>{{ currency(item.paid_amount) }}</b></div></div>
      </article>
    </section>
    <section class="panel decision-wide-chart"><div class="panel-heading"><div><p>会员贡献</p><h2>成交与复购金额趋势</h2></div><span v-if="member.asset_date && member.repurchase_cycle > 0" class="panel-action">{{ shortDate(member.asset_date) }} 复购周期 {{ member.repurchase_cycle.toFixed(1) }} 天</span></div><BusinessChart v-if="member.daily_metrics.length" :option="trendOption" ariaLabel="会员成交与复购金额趋势图" :height="320" /><EmptyState v-else title="暂无会员成交趋势" detail="当前日期范围没有可用的会员成交日报。" /></section>
  </template>
  <section v-else-if="loading" class="loading-panel"><LoaderCircle :size="26" class="spinning" /><span>正在读取会员分析</span></section>
  <EmptyState v-else title="暂无会员分析数据" detail="当前日期范围没有会员分析记录。" :icon="Crown" />
</template>

<style scoped>
.member-data-warning { display: flex; align-items: flex-start; gap: 9px; border: 1px solid #e7ddbd; padding: 10px 12px; color: #826520; background: #fffaf1; }.member-data-warning svg { flex: 0 0 auto; margin-top: 1px; }.member-data-warning div { display: grid; gap: 3px; }.member-data-warning strong { font-size: 12px; }.member-data-warning span { font-size: 12px; line-height: 1.5; }
.member-channel-panel { min-width: 0; overflow: hidden; }.member-channel-summary { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1px; margin-top: 12px; border: 1px solid #e2ebe6; border-radius: 5px; overflow: hidden; background: #e2ebe6; }.member-channel-summary > div { display: grid; gap: 4px; padding: 10px 12px; background: #fbfdfc; }.member-channel-summary span { color: #829188; font-size: 12px; }.member-channel-summary strong { overflow: hidden; color: #345045; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }.member-channel-summary small { color: #8e9c95; font-size: 12px; }.member-channel-table { margin-top: 10px; overflow-x: auto; }.member-channel-row { display: grid; min-width: 610px; grid-template-columns: minmax(140px, 1.3fr) 1fr .85fr .85fr 1fr; min-height: 42px; align-items: center; gap: 10px; border-bottom: 1px solid #edf2ef; color: #687a70; font-size: 12px; text-align: right; }.member-channel-row > :first-child { text-align: left; }.member-channel-row > div { display: grid; gap: 2px; }.member-channel-row strong, .member-channel-row b { color: #40574b; font-weight: 650; }.member-channel-row em { color: #167b55; font-style: normal; font-weight: 700; }.member-channel-row small { color: #9aa69f; font-size: 12px; }.member-channel-head { min-height: 32px; color: #96a39c; font-size: 12px; }.member-channel-head > :not(:first-child) { text-align: right; }
@media (max-width: 620px) { .member-channel-summary { grid-template-columns: 1fr; } }
</style>
