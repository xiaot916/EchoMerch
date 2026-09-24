<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { ArrowLeft, ArrowRight, BarChart3, CircleDollarSign, Coins, LoaderCircle, MousePointerClick, Scale, Search } from "lucide-vue-next"

import BusinessChart from "@/components/BusinessChart.vue"
import EmptyState from "@/components/EmptyState.vue"
import MetricCard from "@/components/MetricCard.vue"
import { useDashboard } from "@/composables/useDashboard"
import { baseValueAxis } from "@/lib/echartsTheme"
import { currency, number, ratio } from "@/lib/format"

const { dashboard, loading } = useDashboard()
const cps = computed(() => dashboard.value?.analysis?.cps)
const daily = computed(() => cps.value?.daily_metrics ?? [])
const products = computed(() => cps.value?.product_metrics ?? [])
const productQuery = ref("")
const productPage = ref(1)
const productPageSize = 10
const filteredProducts = computed(() => {
  const query = productQuery.value.trim().toLocaleLowerCase()
  return query ? products.value.filter((item) => `${item.product_name} ${item.product_id} ${item.series} ${item.positioning}`.toLocaleLowerCase().includes(query)) : products.value
})
const productPageCount = computed(() => Math.max(1, Math.ceil(filteredProducts.value.length / productPageSize)))
const pagedProducts = computed(() => filteredProducts.value.slice((productPage.value - 1) * productPageSize, productPage.value * productPageSize))
const productPaidAmount = computed(() => products.value.reduce((sum, item) => sum + item.paid_amount, 0))
const productExpense = computed(() => products.value.reduce((sum, item) => sum + item.estimated_expense, 0))
const topShare = (count: number) => productPaidAmount.value ? products.value.slice(0, count).reduce((sum, item) => sum + item.paid_amount, 0) / productPaidAmount.value * 100 : 0
const dailyPage = ref(1)
const dailyPageSize = ref(10)
const orderedDaily = computed(() => [...daily.value].reverse())
const dailyPageCount = computed(() => Math.max(1, Math.ceil(orderedDaily.value.length / dailyPageSize.value)))
const pagedDaily = computed(() => orderedDaily.value.slice((dailyPage.value - 1) * dailyPageSize.value, dailyPage.value * dailyPageSize.value))
const dailyPageStart = computed(() => orderedDaily.value.length ? (dailyPage.value - 1) * dailyPageSize.value + 1 : 0)
const dailyPageEnd = computed(() => Math.min(dailyPage.value * dailyPageSize.value, orderedDaily.value.length))
watch(dailyPageSize, () => { dailyPage.value = 1 })
watch(productQuery, () => { productPage.value = 1 })
watch(dailyPageCount, (value) => { if (dailyPage.value > value) dailyPage.value = value })
watch(() => [dashboard.value?.range_start, dashboard.value?.range_end], () => { dailyPage.value = 1 })
function clickPaymentRate(clickVisitors: number, paidOrders: number): number | null { return clickVisitors ? paidOrders / clickVisitors * 100 : null }
function paymentCostRate(paidAmount: number, paymentExpense: number): number | null { return paidAmount ? paymentExpense / paidAmount * 100 : null }

const trendOption = computed(() => ({
  color: ["#16845b", "#5b8def", "#e2a447"],
  tooltip: { trigger: "axis", valueFormatter: (value: number) => currency(Number(value)) },
  legend: { bottom: 0, data: ["付款金额", "结算金额", "渠道支出"] },
  grid: { left: 62, right: 24, top: 24, bottom: 54 },
  xAxis: { type: "category", data: daily.value.map((item) => item.stat_date.slice(5)) },
  yAxis: baseValueAxis({ axisLabel: { formatter: "¥{value}" } }),
  series: [
    { name: "付款金额", type: "bar", barMaxWidth: 24, data: daily.value.map((item) => item.paid_amount) },
    { name: "结算金额", type: "line", smooth: true, data: daily.value.map((item) => item.settlement_amount) },
    { name: "渠道支出", type: "line", smooth: true, data: daily.value.map((item) => item.payment_expense + item.settlement_expense) },
  ],
}))
const productOption = computed(() => ({
  color: ["#16845b", "#e2a447"],
  tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (value: number) => currency(Number(value)) },
  legend: { bottom: 0, data: ["付款金额", "预估费用"] },
  grid: { left: 132, right: 24, top: 18, bottom: 48 },
  xAxis: baseValueAxis({ axisLabel: { formatter: "¥{value}" } }),
  yAxis: { type: "category", inverse: true, data: products.value.slice(0, 8).map((item) => item.product_name.length > 12 ? `${item.product_name.slice(0, 12)}…` : item.product_name) },
  series: [
    { name: "付款金额", type: "bar", barMaxWidth: 18, data: products.value.slice(0, 8).map((item) => item.paid_amount) },
    { name: "预估费用", type: "bar", barMaxWidth: 18, data: products.value.slice(0, 8).map((item) => item.estimated_expense) },
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

    <section v-if="products.length" class="decision-chart-grid cps-product-overview">
      <article class="panel"><div class="panel-heading"><div><p>商品贡献</p><h2>Top 商品付款与预估费用</h2></div><span class="panel-action">{{ number(products.length) }} 个商品</span></div><BusinessChart :option="productOption" ariaLabel="CPS商品付款金额与预估费用对比" :height="350" /></article>
      <article class="panel"><div class="panel-heading"><div><p>集中度</p><h2>商品组合依赖</h2></div><BarChart3 :size="18" /></div><div class="marketing-reading-list"><div><span>Top 1 付款占比</span><strong>{{ ratio(topShare(1)) }}</strong><small>头部单品依赖程度</small></div><div><span>Top 3 付款占比</span><strong>{{ ratio(topShare(3)) }}</strong><small>核心商品组合贡献</small></div><div><span>Top 10 付款占比</span><strong>{{ ratio(topShare(10)) }}</strong><small>长尾空间与集中风险参考</small></div><div><span>商品预估费用率</span><strong>{{ ratio(productPaidAmount ? productExpense / productPaidAmount * 100 : 0) }}</strong><small>预估总费用 / 商品付款金额</small></div></div></article>
    </section>

    <section v-if="products.length" class="panel cps-product-panel"><div class="panel-heading cps-product-heading"><div><p>商品明细</p><h2>CPS 商品贡献与效率</h2></div><label class="cps-product-search"><Search :size="15" /><input v-model="productQuery" type="search" placeholder="搜索商品、ID、系列或定位" /></label></div><div class="cps-product-table"><div class="cps-product-row cps-product-head"><span>商品</span><span>系列 / 定位</span><span>进店 UV</span><span>付款金额</span><span>付款笔数</span><span>付款转化</span><span>预估费用</span><span>费用率</span><span>结算金额</span></div><div v-for="item in pagedProducts" :key="item.product_id" class="cps-product-row"><div><strong>{{ item.product_name }}</strong><small>{{ item.product_id }}</small></div><div><span>{{ item.series }}</span><small>{{ item.positioning }}</small></div><span>{{ number(item.entry_visitors) }}</span><b>{{ currency(item.paid_amount) }}</b><span>{{ number(item.paid_order_count) }}</span><em>{{ ratio(item.conversion_rate) }}</em><span>{{ currency(item.estimated_expense) }}</span><em>{{ ratio(item.expense_rate) }}</em><span>{{ currency(item.settled_amount) }}</span></div></div><footer class="daily-pagination"><div><span>显示 {{ number((productPage - 1) * productPageSize + (filteredProducts.length ? 1 : 0)) }}–{{ number(Math.min(productPage * productPageSize, filteredProducts.length)) }} / {{ number(filteredProducts.length) }} 个商品</span></div><div><button type="button" :disabled="productPage <= 1" @click="productPage -= 1"><ArrowLeft :size="14" />上一页</button><span>第 {{ productPage }} / {{ productPageCount }} 页</span><button type="button" :disabled="productPage >= productPageCount" @click="productPage += 1">下一页<ArrowRight :size="14" /></button></div></footer><p class="panel-footnote">费用率使用商品明细中的预估佣金与服务费。付款和结算可能跨周期；当前明细没有达人、合作方和退款扣除字段，因此不生成达人排行，也不把付款减费用解释为利润。</p></section>

    <section class="decision-chart-grid">
      <article class="panel"><div class="panel-heading"><div><p>渠道趋势</p><h2>付款、结算与支出变化</h2></div><BarChart3 :size="18" /></div><BusinessChart :option="trendOption" ariaLabel="CPS付款结算和渠道支出趋势图" :height="330" /></article>
      <article class="panel"><div class="panel-heading"><div><p>付款与结算</p><h2>转化与结算差额</h2></div><Scale :size="18" /></div><div class="marketing-reading-list"><div><span>点击到付款</span><strong>{{ ratio(cps.click_visitors ? cps.paid_order_count / cps.click_visitors * 100 : 0) }}</strong><small>付款笔数 / 点击人数，仅作规模效率参考</small></div><div><span>付款到结算差额</span><strong>{{ currency(cps.paid_amount - cps.settlement_amount) }}</strong><small>可能包含时间滞后、退款和结算口径差异</small></div><div><span>结算支出</span><strong>{{ currency(cps.settlement_expense) }}</strong><small>结算支出费用与结算营销服务费</small></div></div></article>
    </section>

    <section class="panel marketing-daily-panel"><div class="panel-heading"><div><p>日级核对</p><h2>CPS 付款、费用与结算效率</h2></div><span class="panel-action">{{ daily.length }} 个统计日</span></div><div class="marketing-daily-table cps-daily-table"><div class="marketing-daily-row marketing-daily-head"><span>日期</span><span>点击人数</span><span>付款金额</span><span>付款笔数</span><span>点击付款率</span><span>付款支出</span><span>付款成本率</span><span>结算金额</span><span>付款结算差额</span></div><div v-for="item in pagedDaily" :key="item.stat_date" class="marketing-daily-row"><span>{{ item.stat_date }}</span><span>{{ number(item.click_visitors) }}</span><b>{{ currency(item.paid_amount) }}</b><span>{{ number(item.paid_order_count) }}</span><em>{{ clickPaymentRate(item.click_visitors, item.paid_order_count) == null ? '--' : ratio(clickPaymentRate(item.click_visitors, item.paid_order_count) || 0) }}</em><span>{{ currency(item.payment_expense) }}</span><em>{{ paymentCostRate(item.paid_amount, item.payment_expense) == null ? '--' : ratio(paymentCostRate(item.paid_amount, item.payment_expense) || 0) }}</em><span>{{ currency(item.settlement_amount) }}</span><span>{{ currency(item.paid_amount - item.settlement_amount) }}</span></div></div><footer class="daily-pagination"><div><span>显示 {{ number(dailyPageStart) }}–{{ number(dailyPageEnd) }} / {{ number(orderedDaily.length) }} 天</span><label>每页<select v-model.number="dailyPageSize"><option :value="10">10</option><option :value="20">20</option><option :value="30">30</option></select></label></div><div><button type="button" :disabled="dailyPage <= 1" @click="dailyPage -= 1"><ArrowLeft :size="14" />上一页</button><span>第 {{ dailyPage }} / {{ dailyPageCount }} 页</span><button type="button" :disabled="dailyPage >= dailyPageCount" @click="dailyPage += 1">下一页<ArrowRight :size="14" /></button></div></footer><p class="panel-footnote">付款成本率 = 付款阶段渠道支出 ÷ CPS 付款金额。付款与结算可能跨周期，差额仅用于核对时间滞后和退款/结算口径，不直接解释为利润或损失。</p></section>
  </template>
  <section v-else-if="loading" class="loading-panel"><LoaderCircle :size="26" class="spinning" /><span>正在读取 CPS 分析</span></section>
  <EmptyState v-else title="暂无 CPS 分析数据" detail="当前日期范围没有 CPS 日报记录。" :icon="Scale" />
</template>

<style scoped>
.cps-daily-table .marketing-daily-row { min-width: 1120px; grid-template-columns: 1fr repeat(8, .9fr); }.cps-daily-table .marketing-daily-row b { color: #40564a; }.cps-daily-table .marketing-daily-row em { color: #167b55; font-style: normal; font-weight: 700; }
.cps-product-heading { align-items: center; }.cps-product-search { display: flex; align-items: center; gap: 7px; width: min(320px, 42vw); border: 1px solid #dfe6e2; padding: 7px 10px; background: #fff; }.cps-product-search input { width: 100%; border: 0; outline: 0; color: #25352d; background: transparent; }.cps-product-table { overflow-x: auto; }.cps-product-row { display: grid; grid-template-columns: minmax(220px, 1.8fr) minmax(120px, 1fr) repeat(7, minmax(90px, .75fr)); gap: 10px; align-items: center; min-width: 1180px; padding: 10px 4px; border-bottom: 1px solid #edf1ef; font-size: 12px; }.cps-product-row > div { display: grid; gap: 3px; min-width: 0; }.cps-product-row strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.cps-product-row small { color: #829087; }.cps-product-row b { color: #40564a; }.cps-product-row em { color: #167b55; font-style: normal; font-weight: 700; }.cps-product-head { color: #738078; font-size: 12px; font-weight: 700; }.cps-product-head span { white-space: nowrap; }
@media (max-width: 760px) { .cps-product-heading { align-items: stretch; flex-direction: column; }.cps-product-search { width: 100%; }.cps-product-overview { grid-template-columns: 1fr; } }
</style>
