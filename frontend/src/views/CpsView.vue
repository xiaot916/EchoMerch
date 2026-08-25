<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { ArrowLeft, ArrowRight, BarChart3, CircleDollarSign, Coins, LoaderCircle, MousePointerClick, Scale } from "lucide-vue-next"

import BusinessChart from "@/components/BusinessChart.vue"
import EmptyState from "@/components/EmptyState.vue"
import MetricCard from "@/components/MetricCard.vue"
import { useDashboard } from "@/composables/useDashboard"
import { currency, number, ratio } from "@/lib/format"

const { dashboard, loading } = useDashboard()
const cps = computed(() => dashboard.value?.analysis?.cps)
const daily = computed(() => cps.value?.daily_metrics ?? [])
const dailyPage = ref(1)
const dailyPageSize = ref(10)
const orderedDaily = computed(() => [...daily.value].reverse())
const dailyPageCount = computed(() => Math.max(1, Math.ceil(orderedDaily.value.length / dailyPageSize.value)))
const pagedDaily = computed(() => orderedDaily.value.slice((dailyPage.value - 1) * dailyPageSize.value, dailyPage.value * dailyPageSize.value))
const dailyPageStart = computed(() => orderedDaily.value.length ? (dailyPage.value - 1) * dailyPageSize.value + 1 : 0)
const dailyPageEnd = computed(() => Math.min(dailyPage.value * dailyPageSize.value, orderedDaily.value.length))
watch(dailyPageSize, () => { dailyPage.value = 1 })
watch(dailyPageCount, (value) => { if (dailyPage.value > value) dailyPage.value = value })
watch(() => [dashboard.value?.range_start, dashboard.value?.range_end], () => { dailyPage.value = 1 })

const trendOption = computed(() => ({
  color: ["#16845b", "#5b8def", "#e2a447"],
  tooltip: { trigger: "axis", valueFormatter: (value: number) => currency(Number(value)) },
  legend: { bottom: 0, data: ["付款金额", "结算金额", "渠道支出"] },
  grid: { left: 62, right: 24, top: 24, bottom: 54 },
  xAxis: { type: "category", data: daily.value.map((item) => item.stat_date.slice(5)) },
  yAxis: { type: "value", axisLabel: { formatter: "¥{value}" }, splitLine: { lineStyle: { color: "#edf1ef" } } },
  series: [
    { name: "付款金额", type: "bar", barMaxWidth: 24, data: daily.value.map((item) => item.paid_amount) },
    { name: "结算金额", type: "line", smooth: true, data: daily.value.map((item) => item.settlement_amount) },
    { name: "渠道支出", type: "line", smooth: true, data: daily.value.map((item) => item.payment_expense + item.settlement_expense) },
  ],
}))
</script>

<template>
  <template v-if="dashboard && cps">
    <section class="business-page-heading">
      <div><p>商品推广 / CPS 渠道</p><h1>CPS 分析</h1><span>分开观察点击、付款、结算和渠道支出，不把 CPS 付款金额直接当作全店增量。</span></div>
      <span class="data-definition-badge"><Scale :size="15" /> 付款 / 结算双口径</span>
    </section>

    <section class="metrics-grid module-metrics">
      <MetricCard label="CPS 付款金额" :value="currency(cps.paid_amount)" :detail="`${number(cps.paid_order_count)} 笔付款 · ${number(cps.click_visitors)} 位点击访客`" :icon="CircleDollarSign" tone="teal" scope="区间累计" />
      <MetricCard label="CPS 结算金额" :value="currency(cps.settlement_amount)" :detail="`结算率 ${ratio(cps.settlement_rate)} · ${number(cps.settlement_order_count)} 笔结算`" :icon="Coins" tone="blue" scope="区间累计" definition="结算金额可能滞后于付款金额，不能与当期付款直接做即时利润判断。" />
      <MetricCard label="付款渠道支出" :value="currency(cps.payment_expense)" :detail="`付款成本率 ${ratio(cps.payment_cost_rate)}`" :icon="Scale" tone="amber" scope="区间累计" definition="包含付款佣金、服务费和营销服务费；这是 CPS 渠道支出，不等于全店利润成本。" />
      <MetricCard label="预售金额" :value="currency(cps.preorder_total_amount)" :detail="`定金 ${currency(cps.preorder_deposit_amount)}`" :icon="MousePointerClick" tone="coral" scope="区间累计" />
    </section>

    <section class="decision-chart-grid">
      <article class="panel"><div class="panel-heading"><div><p>渠道趋势</p><h2>付款、结算与支出变化</h2></div><BarChart3 :size="18" /></div><BusinessChart :option="trendOption" ariaLabel="CPS付款结算和渠道支出趋势图" :height="330" /></article>
      <article class="panel"><div class="panel-heading"><div><p>付款与结算</p><h2>转化与结算差额</h2></div><Scale :size="18" /></div><div class="marketing-reading-list"><div><span>点击到付款</span><strong>{{ ratio(cps.click_visitors ? cps.paid_order_count / cps.click_visitors * 100 : 0) }}</strong><small>付款笔数 / 点击人数，仅作规模效率参考</small></div><div><span>付款到结算差额</span><strong>{{ currency(cps.paid_amount - cps.settlement_amount) }}</strong><small>可能包含时间滞后、退款和结算口径差异</small></div><div><span>结算支出</span><strong>{{ currency(cps.settlement_expense) }}</strong><small>结算支出费用与结算营销服务费</small></div></div></article>
    </section>

    <section class="panel marketing-daily-panel"><div class="panel-heading"><div><p>日级核对</p><h2>CPS 原始日报明细</h2></div><span class="panel-action">{{ daily.length }} 个统计日</span></div><div class="marketing-daily-table cps-daily-table"><div class="marketing-daily-row marketing-daily-head"><span>日期</span><span>点击人数</span><span>付款金额</span><span>付款笔数</span><span>结算金额</span><span>渠道支出</span></div><div v-for="item in pagedDaily" :key="item.stat_date" class="marketing-daily-row"><span>{{ item.stat_date }}</span><span>{{ number(item.click_visitors) }}</span><span>{{ currency(item.paid_amount) }}</span><span>{{ number(item.paid_order_count) }}</span><span>{{ currency(item.settlement_amount) }}</span><span>{{ currency(item.payment_expense + item.settlement_expense) }}</span></div></div><footer class="daily-pagination"><div><span>显示 {{ number(dailyPageStart) }}–{{ number(dailyPageEnd) }} / {{ number(orderedDaily.length) }} 天</span><label>每页<select v-model.number="dailyPageSize"><option :value="10">10</option><option :value="20">20</option><option :value="30">30</option></select></label></div><div><button type="button" :disabled="dailyPage <= 1" @click="dailyPage -= 1"><ArrowLeft :size="14" />上一页</button><span>第 {{ dailyPage }} / {{ dailyPageCount }} 页</span><button type="button" :disabled="dailyPage >= dailyPageCount" @click="dailyPage += 1">下一页<ArrowRight :size="14" /></button></div></footer><p class="panel-footnote">付款、结算是平台不同阶段的事实指标；渠道支出只按 CPS 字段汇总，不扩展为用户未提供的商品成本或全店利润模型。</p></section>
  </template>
  <section v-else-if="loading" class="loading-panel"><LoaderCircle :size="26" class="spinning" /><span>正在读取 CPS 分析</span></section>
  <EmptyState v-else title="暂无 CPS 分析数据" detail="当前日期范围没有 CPS 日报记录。" :icon="Scale" />
</template>
