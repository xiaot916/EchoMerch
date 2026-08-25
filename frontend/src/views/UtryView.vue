<script setup lang="ts">
import { computed, ref } from "vue"
import { AlertTriangle, ArrowLeft, ArrowRight, CircleDollarSign, Gift, LoaderCircle, PackageCheck, RefreshCw, Search, Target, TicketCheck, TrendingUp, UserRoundPlus, UsersRound } from "lucide-vue-next"

import BusinessChart from "@/components/BusinessChart.vue"
import EmptyState from "@/components/EmptyState.vue"
import MetricCard from "@/components/MetricCard.vue"
import { fetchStores, fetchUtryAnalysis } from "@/api"
import { currency, number, ratio } from "@/lib/format"
import type { DataCoverage, UtryAnalysisResponse, UtryProductMetric } from "@/types"

const analysis = ref<UtryAnalysisResponse | null>(null)
const loading = ref(false)
const error = ref("")
const selectedStoreId = ref<number | null>(null)
const startDate = ref("")
const endDate = ref("")
const search = ref("")
const sortBy = ref<"sample_gmv" | "sample_people" | "store_365d_repurchase_amount">("sample_gmv")
const page = ref(1)
const pageSize = 20

async function load(useFilter = false): Promise<void> {
  loading.value = true
  error.value = ""
  try {
    if (!selectedStoreId.value) selectedStoreId.value = (await fetchStores())[0]?.store_id ?? null
    if (!selectedStoreId.value) throw new Error("当前没有可用店铺")
    const payload = await fetchUtryAnalysis(
      useFilter ? startDate.value || undefined : undefined,
      useFilter ? endDate.value || undefined : undefined,
      selectedStoreId.value,
    )
    analysis.value = payload
    startDate.value = payload.range_start
    endDate.value = payload.range_end
    page.value = 1
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : "U先分析暂不可用"
    if (!analysis.value) analysis.value = null
  } finally {
    loading.value = false
  }
}
void load()

const sample = computed(() => analysis.value?.sample_summary)
const repurchase = computed(() => analysis.value?.latest_repurchase)
const previousRepurchase = computed(() => analysis.value?.previous_repurchase)
const daily = computed(() => analysis.value?.daily_metrics ?? [])
const hasData = computed(() => Boolean(analysis.value && (analysis.value.products.length || analysis.value.daily_metrics.some((item) => item.sample_status === "complete" || item.repurchase_status === "complete"))))

function dayLabel(value: string): string { return value.slice(5) }
function optionalCurrency(value: number | null): string { return value === null ? "--" : currency(value) }
function optionalNumber(value: number | null): string { return value === null ? "--" : number(value) }
function enabled(value: string): boolean { return ["1", "是", "true", "TRUE", "yes", "Y"].includes(value) }
function coverageLabel(item: DataCoverage | null): string {
  if (!item) return "暂无覆盖记录"
  if (item.status === "complete") return `${item.covered_days}/${item.expected_days} 天完整`
  if (item.status === "empty" && item.no_data_dates?.length) return `${item.no_data_dates.length} 天平台无数据`
  return `${item.covered_days}/${item.expected_days} 天，缺 ${item.missing_dates.length} 天`
}
function coverageClass(item: DataCoverage | null): string {
  if (!item) return "is-missing"
  if (item.status === "complete") return "is-complete"
  if (item.status === "empty" && item.no_data_dates?.length) return "is-no-data"
  return "is-partial"
}
function snapshotChange(current: number, previous: number): number | null {
  return previous ? (current - previous) / Math.abs(previous) * 100 : null
}
function changeText(value: number | null): string {
  if (value === null) return "暂无前一日基准"
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}% 较前一快照`
}

const filteredProducts = computed(() => {
  const term = search.value.trim().toLowerCase()
  const rows = term
    ? (analysis.value?.products ?? []).filter((item) => `${item.product_id} ${item.product_name} ${item.leaf_category}`.toLowerCase().includes(term))
    : (analysis.value?.products ?? [])
  return [...rows].sort((left, right) => Number(right[sortBy.value] ?? 0) - Number(left[sortBy.value] ?? 0))
})
const pageCount = computed(() => Math.max(1, Math.ceil(filteredProducts.value.length / pageSize)))
const pagedProducts = computed(() => filteredProducts.value.slice((page.value - 1) * pageSize, page.value * pageSize))
function changePage(value: number): void { page.value = Math.min(Math.max(value, 1), pageCount.value) }

function chartMoney(value: number | null | undefined): string {
  return value === null || value === undefined || Number.isNaN(value) ? "暂无" : `¥${Number(value).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

const sampleTrendOption = computed(() => ({
  color: ["#2f7d68", "#5b8def", "#e4a64f"],
  tooltip: {
    trigger: "axis",
    valueFormatter: (value: number | null) => value === null ? "暂无" : Number(value).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
  },
  legend: { bottom: 0, data: ["派样人次", "180天商家新客", "派样GMV"] },
  grid: { left: 58, right: 62, top: 28, bottom: 56 },
  xAxis: { type: "category", data: daily.value.map((item) => dayLabel(item.stat_date)) },
  yAxis: [
    { type: "value", name: "人次", axisLabel: { formatter: (value: number) => Number(value).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }, splitLine: { lineStyle: { color: "#edf1ef" } } },
    { type: "value", name: "GMV", axisLabel: { formatter: (value: number) => chartMoney(value) }, splitLine: { show: false } },
  ],
  series: [
    { name: "派样人次", type: "line", smooth: true, symbolSize: 5, data: daily.value.map((item) => item.sample_people) },
    { name: "180天商家新客", type: "line", smooth: true, symbolSize: 5, data: daily.value.map((item) => item.merchant_new_customers_180d) },
    { name: "派样GMV", type: "bar", yAxisIndex: 1, barMaxWidth: 22, data: daily.value.map((item) => item.sample_gmv) },
  ],
}))

const repurchaseTrendOption = computed(() => ({
  color: ["#2f7d68", "#5b8def", "#d28a48"],
  tooltip: { trigger: "axis", formatter: (params: Array<{ dataIndex: number }>) => { const item = daily.value[params[0]?.dataIndex ?? 0]; return item ? `${item.stat_date}<br/>30日同店回购：${chartMoney(item.store_30d_repurchase_amount)}<br/>90日同店回购：${chartMoney(item.store_90d_repurchase_amount)}<br/>365日同店回购：${chartMoney(item.store_365d_repurchase_amount)}<br/>状态：${item.repurchase_status === "complete" ? "快照已采集" : item.repurchase_status === "no_data" ? "平台无数据" : "未采集"}` : "" } },
  legend: { bottom: 0, data: ["30日同店回购", "90日同店回购", "365日同店回购"] },
  grid: { left: 66, right: 26, top: 28, bottom: 56 },
  xAxis: { type: "category", data: daily.value.map((item) => dayLabel(item.stat_date)) },
  yAxis: { type: "value", axisLabel: { formatter: (value: number) => chartMoney(value) }, splitLine: { lineStyle: { color: "#edf1ef" } } },
  series: [
    { name: "30日同店回购", type: "line", smooth: true, showSymbol: false, data: daily.value.map((item) => item.store_30d_repurchase_amount) },
    { name: "90日同店回购", type: "line", smooth: true, showSymbol: false, data: daily.value.map((item) => item.store_90d_repurchase_amount) },
    { name: "365日同店回购", type: "line", smooth: true, showSymbol: false, data: daily.value.map((item) => item.store_365d_repurchase_amount) },
  ],
}))

const topProducts = computed(() => [...(analysis.value?.products ?? [])].filter((item) => (item.sample_gmv ?? 0) > 0 || (item.store_365d_repurchase_amount ?? 0) > 0).sort((left, right) => (right.sample_gmv ?? 0) - (left.sample_gmv ?? 0)).slice(0, 8))
const productOption = computed(() => ({
  color: ["#5b8def", "#2f7d68"],
  tooltip: {
    trigger: "axis",
    axisPointer: { type: "shadow" },
    formatter: (params: Array<{ seriesName: string; value: number | null }>) => params.map((item) => `${item.seriesName}：${chartMoney(item.value)}`).join("<br/>"),
  },
  legend: { bottom: 0, data: ["区间派样GMV", "最新365日同店回购"] },
  grid: { left: 162, right: 34, top: 20, bottom: 48 },
  xAxis: { type: "value", axisLabel: { formatter: (value: number) => chartMoney(value) }, splitLine: { lineStyle: { color: "#edf1ef" } } },
  yAxis: { type: "category", inverse: true, data: topProducts.value.map((item) => item.product_name.length > 16 ? `${item.product_name.slice(0, 16)}…` : item.product_name) },
  series: [
    { name: "区间派样GMV", type: "bar", barMaxWidth: 16, data: topProducts.value.map((item) => item.sample_gmv ?? 0) },
    { name: "最新365日同店回购", type: "bar", barMaxWidth: 16, data: topProducts.value.map((item) => item.store_365d_repurchase_amount ?? 0) },
  ],
}))

</script>

<template>
  <template v-if="analysis && hasData">
    <section class="business-page-heading utry-heading">
      <div><p>营销活动 / 派样获客与复购</p><h1>U先试用</h1><span>串联派样规模、商家新客、会员沉淀与后续回购承接，定位“派得出去但接不回来”的商品和配置问题。</span></div>
      <div class="utry-heading-actions"><div class="utry-date-filter"><input v-model="startDate" type="date" :max="endDate" /><span>至</span><input v-model="endDate" type="date" :min="startDate" /><button type="button" :disabled="loading" @click="load(true)"><RefreshCw :size="14" :class="{ spinning: loading }" />应用</button></div><span class="data-definition-badge">回购为最新日滚动快照，不跨日累加</span></div>
    </section>

    <section class="utry-data-status">
      <article :class="coverageClass(analysis.sample_coverage)"><div><UsersRound :size="17" /><span><strong>派样数据</strong><small>所选范围覆盖状态</small></span></div><em>{{ coverageLabel(analysis.sample_coverage) }}</em></article>
      <article :class="coverageClass(analysis.repurchase_coverage)"><div><TrendingUp :size="17" /><span><strong>复购快照</strong><small>所选范围覆盖状态</small></span></div><em>{{ coverageLabel(analysis.repurchase_coverage) }}</em></article>
      <p v-if="analysis.sample_coverage?.missing_dates.length || analysis.repurchase_coverage?.missing_dates.length"><AlertTriangle :size="15" />缺失日期按断点展示，不计作真实 0；平台确认无数据的日期单独标记且无需重复补采。</p>
    </section>

    <section v-if="sample && repurchase" class="metrics-grid module-metrics utry-metrics">
      <MetricCard label="派样人次" :value="number(sample.sample_people)" :detail="`${number(sample.sample_orders)} 单 · 人均 ${sample.average_orders_per_person.toFixed(2)} 单`" :icon="UsersRound" tone="blue" scope="区间累计" />
      <MetricCard label="派样 GMV" :value="currency(sample.sample_gmv)" :detail="`人均派样金额 ${currency(sample.sample_gmv_per_person)}`" :icon="CircleDollarSign" tone="teal" scope="区间累计" />
      <MetricCard label="180天商家新客" :value="number(sample.merchant_new_customers_180d)" :detail="sample.merchant_new_customer_rate_180d === null ? '暂无派样分母' : `占派样人次 ${ratio(sample.merchant_new_customer_rate_180d)}`" :icon="UserRoundPlus" tone="amber" scope="区间累计" />
      <MetricCard label="新会员沉淀" :value="number(sample.new_members)" :detail="`${number(sample.new_followers)} 位新粉丝`" :icon="Gift" tone="coral" scope="区间累计" />
      <MetricCard label="30日同店回购" :value="currency(repurchase.store_30d_repurchase_amount)" :detail="`${number(repurchase.store_30d_repurchase_uv)} 商品行 UV · ${changeText(snapshotChange(repurchase.store_30d_repurchase_amount, previousRepurchase?.store_30d_repurchase_amount ?? 0))}`" :icon="TrendingUp" tone="teal" scope="最新滚动快照" />
      <MetricCard label="90日同店回购" :value="currency(repurchase.store_90d_repurchase_amount)" :detail="`${number(repurchase.store_90d_repurchase_uv)} 商品行 UV`" :icon="Target" tone="blue" scope="最新滚动快照" />
      <MetricCard label="365日同店回购" :value="currency(repurchase.store_365d_repurchase_amount)" :detail="`同品牌 ${currency(repurchase.brand_365d_repurchase_amount)}`" :icon="PackageCheck" tone="amber" scope="最新滚动快照" />
      <MetricCard label="正装绑定覆盖" :value="ratio(repurchase.bound_regular_product_share ?? 0)" :detail="`${repurchase.bound_regular_product_count}/${repurchase.product_count} 个商品已绑定`" :icon="TicketCheck" tone="coral" scope="最新滚动快照" />
    </section>

    <section class="decision-chart-grid utry-chart-grid">
      <article class="panel"><div class="panel-heading"><div><p>派样获客</p><h2>派样、人群与新客趋势</h2></div><span class="panel-action">区间事实累计</span></div><BusinessChart :option="sampleTrendOption" ariaLabel="U先派样人次新客和派样GMV趋势" :height="350" /></article>
      <article class="panel"><div class="panel-heading"><div><p>后链路承接</p><h2>30 / 90 / 365 日回购快照趋势</h2></div><span class="panel-action">逐日快照比较</span></div><BusinessChart :option="repurchaseTrendOption" ariaLabel="U先同店回购滚动快照趋势" :height="350" /></article>
    </section>

    <section class="utry-middle-grid">
      <article class="panel"><div class="panel-heading"><div><p>商品贡献</p><h2>高派样商品与后续回购承接</h2></div><span class="panel-action">Top 8 仅展示，全量用于汇总</span></div><BusinessChart :option="productOption" ariaLabel="U先商品派样和回购金额对比" :height="390" /></article>
      <article class="panel utry-config-panel"><div class="panel-heading"><div><p>承接配置</p><h2>正装、回购券与礼金覆盖</h2></div><PackageCheck :size="18" /></div><div class="utry-config-list"><div><span><PackageCheck :size="16" />绑定正装</span><strong>{{ number(repurchase?.bound_regular_product_count ?? 0) }}</strong><em>{{ ratio(repurchase?.bound_regular_product_share ?? 0) }}</em></div><div><span><TicketCheck :size="16" />回购券</span><strong>{{ number(repurchase?.configured_coupon_count ?? 0) }}</strong><em>{{ ratio(repurchase?.configured_coupon_share ?? 0) }}</em></div><div><span><Gift :size="16" />回购礼金</span><strong>{{ number(repurchase?.configured_gift_count ?? 0) }}</strong><em>{{ ratio(repurchase?.configured_gift_share ?? 0) }}</em></div></div><p class="panel-footnote">覆盖率按最新回购快照的全量商品数计算；配置存在不等于产生因果增量，需做商品分组验证。</p></article>
    </section>

    <section class="panel utry-product-panel">
      <div class="panel-heading"><div><p>商品明细</p><h2>派样、获客与回购承接矩阵</h2></div><span class="panel-action">{{ filteredProducts.length }} / {{ analysis.products.length }} 个商品</span></div>
      <div class="utry-table-toolbar"><label><Search :size="15" /><input v-model="search" placeholder="搜索商品名称、ID 或类目" @input="page = 1" /></label><select v-model="sortBy" @change="page = 1"><option value="sample_gmv">按派样 GMV</option><option value="sample_people">按派样人次</option><option value="store_365d_repurchase_amount">按365日回购</option></select></div>
      <div class="utry-table-wrap"><div class="utry-table"><div class="utry-row utry-head"><span>U先商品</span><span>派样人次</span><span>派样GMV</span><span>180天新客</span><span>30日回购</span><span>90日回购</span><span>365日回购</span><span>承接配置</span></div><div v-for="item in pagedProducts" :key="item.product_id" class="utry-row"><div class="utry-product-name"><strong>{{ item.product_name || '未命名商品' }}</strong><small>{{ item.product_id }} · {{ item.leaf_category || '未分类' }}</small></div><span>{{ optionalNumber(item.sample_people) }}</span><span>{{ optionalCurrency(item.sample_gmv) }}</span><span>{{ optionalNumber(item.merchant_new_customers_180d) }}</span><span>{{ optionalCurrency(item.store_30d_repurchase_amount) }}</span><span>{{ optionalCurrency(item.store_90d_repurchase_amount) }}</span><span>{{ optionalCurrency(item.store_365d_repurchase_amount) }}</span><div class="utry-config-tags"><em :class="{ on: enabled(item.bind_regular_product) }">正装</em><em :class="{ on: enabled(item.configured_repurchase_coupon) }">券</em><em :class="{ on: enabled(item.configured_repurchase_gift) }">礼金</em></div></div></div></div>
      <footer class="utry-pagination"><span>第 {{ page }} / {{ pageCount }} 页</span><div><button :disabled="page <= 1" @click="changePage(page - 1)"><ArrowLeft :size="15" /></button><button :disabled="page >= pageCount" @click="changePage(page + 1)"><ArrowRight :size="15" /></button></div></footer>
      <p class="panel-footnote">派样指标按所选区间累计；回购指标使用最新滚动快照。商品回购 UV 跨商品可能重复，页面不把它当作店铺唯一回购买家数，也不计算缺少 cohort 分母的回购率。</p>
    </section>
  </template>

  <section v-else-if="loading" class="loading-panel"><LoaderCircle :size="26" class="spinning" /><span>正在读取 U先派样与复购数据</span></section>
  <section v-else-if="error" class="utry-error"><AlertTriangle :size="22" /><strong>U先分析加载失败</strong><span>{{ error }}</span><button @click="load()">重新加载</button></section>
  <EmptyState v-else title="暂无 U先数据" detail="当前店铺没有可用于派样与复购分析的 U先日报。" :icon="Gift" />
</template>

<style scoped>
.utry-heading { align-items: flex-end; }.utry-heading-actions { display: grid; justify-items: end; gap: 10px; }.utry-date-filter { display: flex; align-items: center; gap: 7px; }.utry-date-filter input, .utry-date-filter button, .utry-table-toolbar input, .utry-table-toolbar select { min-height: 34px; border: 1px solid #dbe4df; border-radius: 6px; background: #fff; color: #385145; font: inherit; }.utry-date-filter input { padding: 0 9px; }.utry-date-filter span { color: #809187; font-size: 11px; }.utry-date-filter button { display: inline-flex; align-items: center; gap: 5px; padding: 0 12px; cursor: pointer; }.utry-data-status { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }.utry-data-status article { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 66px; padding: 12px 15px; border: 1px solid #dce5e0; border-radius: 8px; background: #fff; }.utry-data-status article > div { display: flex; align-items: center; gap: 9px; }.utry-data-status article span { display: grid; gap: 2px; }.utry-data-status strong { color: #28453a; font-size: 12px; }.utry-data-status small, .utry-data-status em { color: #71847a; font-size: 10px; font-style: normal; }.utry-data-status .is-complete { border-left: 3px solid #38a477; }.utry-data-status .is-partial { border-left: 3px solid #e0a447; }.utry-data-status .is-no-data { border-left: 3px solid #8ba3be; }.utry-data-status .is-missing { border-left: 3px solid #d27768; }.utry-data-status > p { grid-column: 1 / -1; display: flex; align-items: center; gap: 6px; margin: 0; color: #9b6b28; font-size: 10px; }.utry-metrics { grid-template-columns: repeat(4, minmax(0, 1fr)); }.utry-chart-grid { align-items: stretch; }.utry-middle-grid { display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(300px, .75fr); gap: 14px; }.utry-config-list { display: grid; gap: 12px; padding-top: 8px; }.utry-config-list > div { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: 12px; padding: 13px 14px; border: 1px solid #e3eae6; border-radius: 7px; background: #fbfcfb; }.utry-config-list span { display: flex; align-items: center; gap: 8px; color: #587064; font-size: 11px; }.utry-config-list strong { color: #213e32; font-size: 18px; }.utry-config-list em { min-width: 56px; color: #2f7d68; font-size: 12px; font-style: normal; text-align: right; }.utry-table-toolbar { display: flex; justify-content: space-between; gap: 10px; margin-bottom: 12px; }.utry-table-toolbar label { display: flex; align-items: center; gap: 7px; width: min(430px, 100%); min-height: 34px; padding: 0 10px; border: 1px solid #dbe4df; border-radius: 6px; color: #72867b; background: #fff; }.utry-table-toolbar label input { width: 100%; min-height: 30px; padding: 0; border: 0; outline: 0; }.utry-table-toolbar select { padding: 0 10px; }.utry-table-wrap { overflow-x: auto; border: 1px solid #e1e8e4; border-radius: 7px; }.utry-table { min-width: 1060px; }.utry-row { display: grid; grid-template-columns: minmax(300px, 2.15fr) repeat(6, minmax(96px, .72fr)) minmax(120px, .8fr); align-items: center; min-height: 58px; border-bottom: 1px solid #edf1ef; }.utry-row:last-child { border-bottom: 0; }.utry-row > * { padding: 9px 10px; color: #52685d; font-size: 10px; }.utry-head { min-height: 40px; background: #f6f9f7; }.utry-head > span { color: #6a7d73; font-weight: 700; }.utry-product-name { display: grid; gap: 4px; }.utry-product-name strong { color: #29473b; font-size: 11px; line-height: 1.45; }.utry-product-name small { color: #819188; font-size: 9px; }.utry-config-tags { display: flex; gap: 4px; }.utry-config-tags em { padding: 3px 5px; border-radius: 4px; background: #f1f3f2; color: #9aa69f; font-size: 9px; font-style: normal; }.utry-config-tags em.on { background: #e8f5ef; color: #287b60; }.utry-pagination { display: flex; align-items: center; justify-content: space-between; padding-top: 12px; color: #73867b; font-size: 10px; }.utry-pagination div { display: flex; gap: 6px; }.utry-pagination button { display: grid; place-items: center; width: 32px; height: 30px; border: 1px solid #dce4e0; border-radius: 5px; background: #fff; color: #405b4e; cursor: pointer; }.utry-pagination button:disabled { cursor: default; opacity: .4; }.utry-error { display: grid; justify-items: center; gap: 9px; padding: 48px 20px; color: #9c5b4e; }.utry-error span { color: #77877f; font-size: 11px; }.utry-error button { padding: 8px 14px; border: 1px solid #d9e3de; border-radius: 6px; background: #fff; cursor: pointer; }
@media (max-width: 1180px) { .utry-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }.utry-middle-grid { grid-template-columns: 1fr; }.utry-diagnosis-grid { grid-template-columns: 1fr; } }
@media (max-width: 760px) { .utry-heading, .utry-heading-actions { align-items: stretch; justify-items: stretch; }.utry-date-filter { flex-wrap: wrap; }.utry-data-status, .utry-metrics { grid-template-columns: 1fr; }.utry-table-toolbar { flex-direction: column; }.utry-table-toolbar label { width: 100%; } }
</style>
