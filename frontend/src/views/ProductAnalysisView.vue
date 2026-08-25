<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import { BarChart3, CircleAlert, CircleDollarSign, Eye, Filter, PackageSearch, RefreshCw, Search, ShoppingCart, Target, UsersRound, X } from "lucide-vue-next"

import BusinessChart from "@/components/BusinessChart.vue"
import EmptyState from "@/components/EmptyState.vue"
import MetricCard from "@/components/MetricCard.vue"
import { fetchProductAnalysis, fetchAnalyticsProducts, fetchStores } from "@/api"
import type { ProductAnalysisResponse, ProductMetric } from "@/types"
import { useDashboard } from "@/composables/useDashboard"
import { currency, number, ratio, compactRange } from "@/lib/format"

const { dashboard } = useDashboard()
const products = ref<ProductMetric[]>([])
const analysis = ref<ProductAnalysisResponse | null>(null)
const selectedProductId = ref("")
const selectedSeries = ref("all")
const productSearch = ref("")
const searchOpen = ref(false)
const loading = ref(true)
const analysisLoading = ref(false)
const error = ref("")

const seriesOptions = computed(() => [...new Set(products.value.map((item) => item.series).filter(Boolean))].sort())
const filteredProducts = computed(() => products.value.filter((item) => selectedSeries.value === "all" || item.series === selectedSeries.value))
const searchResults = computed(() => {
  const keyword = productSearch.value.trim().toLocaleLowerCase("zh-CN")
  if (!keyword) return filteredProducts.value.slice(0, 12)
  return filteredProducts.value
    .filter((item) => item.product_id.toLocaleLowerCase().includes(keyword) || item.product_name.toLocaleLowerCase("zh-CN").includes(keyword))
    .sort((left, right) => {
      const leftId = left.product_id.toLocaleLowerCase()
      const rightId = right.product_id.toLocaleLowerCase()
      const leftName = left.product_name.toLocaleLowerCase("zh-CN")
      const rightName = right.product_name.toLocaleLowerCase("zh-CN")
      const score = (id: string, name: string) => id === keyword ? 0 : id.startsWith(keyword) ? 1 : name.startsWith(keyword) ? 2 : id.includes(keyword) ? 3 : 4
      return score(leftId, leftName) - score(rightId, rightName) || right.paid_amount - left.paid_amount
    })
    .slice(0, 12)
})
const selectedProduct = computed(() => analysis.value?.product || products.value.find((item) => item.product_id === selectedProductId.value) || null)
const daily = computed(() => analysis.value?.daily_metrics || [])
const productRows = computed(() => products.value.slice(0, 20).map((item, index) => ({ ...item, rank: index + 1, conversionRate: item.visitors ? item.buyers / item.visitors * 100 : 0 })))
const totalPaid = computed(() => products.value.reduce((sum, item) => sum + item.paid_amount, 0))
const topOneShare = computed(() => totalPaid.value ? (products.value[0]?.paid_amount || 0) / totalPaid.value * 100 : 0)
const topThreeShare = computed(() => totalPaid.value ? products.value.slice(0, 3).reduce((sum, item) => sum + item.paid_amount, 0) / totalPaid.value * 100 : 0)
const selectedConversion = computed(() => selectedProduct.value?.visitors ? selectedProduct.value.buyers / selectedProduct.value.visitors * 100 : 0)

function queryDates(): { start: string; end: string } {
  return { start: dashboard.value?.range_start || "", end: dashboard.value?.range_end || "" }
}

function selectSearchResult(item: ProductMetric): void {
  selectedProductId.value = item.product_id
  productSearch.value = ""
  searchOpen.value = false
}

function selectFirstSearchResult(): void {
  const first = searchResults.value[0]
  if (first) selectSearchResult(first)
}

async function load(): Promise<void> {
  if (!dashboard.value) return
  loading.value = true
  error.value = ""
  try {
    const stores = await fetchStores()
    const { start, end } = queryDates()
    products.value = await fetchAnalyticsProducts(start, end, stores[0]?.store_id)
    if (!filteredProducts.value.some((item) => item.product_id === selectedProductId.value)) selectedProductId.value = filteredProducts.value[0]?.product_id || ""
    await loadAnalysis()
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : "商品目录读取失败"
  } finally {
    loading.value = false
  }
}

async function loadAnalysis(): Promise<void> {
  if (!selectedProductId.value || !dashboard.value) {
    analysis.value = null
    return
  }
  analysisLoading.value = true
  error.value = ""
  try {
    const stores = await fetchStores()
    const { start, end } = queryDates()
    analysis.value = await fetchProductAnalysis(selectedProductId.value, start, end, stores[0]?.store_id)
  } catch (exc) {
    analysis.value = null
    error.value = exc instanceof Error ? exc.message : "单品分析读取失败"
  } finally {
    analysisLoading.value = false
  }
}

const trendOption = computed(() => ({
  color: ["#2d9b70", "#6289d8", "#d49a38"],
  tooltip: { trigger: "axis" },
  legend: { bottom: 0, data: ["支付金额", "访客", "支付买家"] },
  grid: { left: 62, right: 18, top: 18, bottom: 42 },
  xAxis: { type: "category", data: daily.value.map((item) => item.stat_date.slice(5)), boundaryGap: false },
  yAxis: [{ type: "value", axisLabel: { formatter: (value: number) => `¥${Math.round(value / 1000)}k` }, splitLine: { lineStyle: { color: "#edf2ef" } } }, { type: "value", axisLabel: { formatter: (value: number) => `${number(value)}` }, splitLine: { show: false } }],
  series: [
    { name: "支付金额", type: "line", smooth: true, data: daily.value.map((item) => item.paid_amount) },
    { name: "访客", type: "line", yAxisIndex: 1, smooth: true, data: daily.value.map((item) => item.visitors) },
    { name: "支付买家", type: "line", yAxisIndex: 1, smooth: true, data: daily.value.map((item) => item.buyers) },
  ],
}))

const peerOption = computed(() => {
  const rows = (analysis.value?.peers || []).slice().sort((left, right) => right.paid_amount - left.paid_amount).slice(0, 8)
  return {
    color: ["#2d9b70"],
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (value: number) => currency(Number(value)) },
    grid: { left: 112, right: 22, top: 18, bottom: 24 },
    xAxis: { type: "value", splitLine: { lineStyle: { color: "#edf2ef" } } },
    yAxis: { type: "category", data: rows.map((item) => item.product_name.slice(0, 13)).reverse() },
    series: [{ type: "bar", barMaxWidth: 22, data: rows.map((item) => item.paid_amount).reverse() }],
  }
})

watch(selectedSeries, () => {
  productSearch.value = ""
  if (!filteredProducts.value.some((item) => item.product_id === selectedProductId.value)) selectedProductId.value = filteredProducts.value[0]?.product_id || ""
})
watch(selectedProductId, () => { if (!loading.value) void loadAnalysis() })
watch(() => [dashboard.value?.range_start, dashboard.value?.range_end], () => { void load() })
onMounted(() => { void load() })
</script>

<template>
  <template v-if="dashboard && !loading && !error && products.length && selectedProduct">
    <header class="product-analysis-heading"><div><h1>单品分析</h1><span>商品 ID、产品系列与经营指标</span></div><button class="product-analysis-refresh" type="button" :disabled="analysisLoading" @click="load"><RefreshCw :size="15" :class="{ spinning: analysisLoading }" />刷新</button></header>
    <section class="product-analysis-toolbar" aria-label="单品分析筛选">
      <label><span>产品系列</span><select v-model="selectedSeries"><option value="all">全部系列</option><option v-for="series in seriesOptions" :key="series" :value="series">{{ series }}</option></select></label>
      <div class="product-analysis-search" @focusin="searchOpen = true" @focusout="searchOpen = false">
        <span>搜索商品</span>
        <div class="product-analysis-search-input"><Search :size="15" /><input v-model="productSearch" type="search" placeholder="输入商品名称或商品 ID" aria-label="搜索商品名称或商品 ID" aria-controls="product-search-results" @keydown.enter.prevent="selectFirstSearchResult" @keydown.esc="searchOpen = false" /><button v-if="productSearch" type="button" aria-label="清空商品搜索" @mousedown.prevent @click="productSearch = ''"><X :size="14" /></button></div>
        <div v-if="searchOpen" id="product-search-results" class="product-analysis-search-results" role="listbox">
          <button v-for="item in searchResults" :key="item.product_id" type="button" role="option" :aria-selected="item.product_id === selectedProductId" @mousedown.prevent @click="selectSearchResult(item)"><strong>{{ item.product_name }}</strong><small>商品 ID {{ item.product_id }} · {{ item.series || "未分类系列" }}</small></button>
          <p v-if="!searchResults.length">没有匹配的商品名称或商品 ID</p>
        </div>
      </div>
      <label class="product-analysis-select"><span>选择商品</span><select v-model="selectedProductId"><option v-for="item in filteredProducts" :key="item.product_id" :value="item.product_id">{{ item.product_id }} · {{ item.product_name }}</option></select></label>
      <span class="product-analysis-coverage">商品日报覆盖 {{ number(products.length) }} 个商品</span>
    </section>
    <section class="product-analysis-identity"><div class="product-analysis-icon"><PackageSearch :size="22" /></div><div><p>{{ selectedProduct.series || "未分类系列" }} · {{ selectedProduct.positioning || "未设置定位" }}</p><h2>{{ selectedProduct.product_name }}</h2><span>商品 ID {{ selectedProduct.product_id }} · {{ selectedProduct.product_type || "未分类" }}</span></div><div class="product-analysis-meta"><span>成交金额</span><strong>{{ currency(selectedProduct.paid_amount) }}</strong><small>{{ number(selectedProduct.buyers) }} 位买家 · {{ ratio(selectedConversion) }} 转化</small></div></section>
    <section class="metrics-grid product-analysis-metrics"><MetricCard label="支付金额" :value="currency(selectedProduct.paid_amount)" detail="所选区间商品成交" :icon="CircleDollarSign" tone="teal" /><MetricCard label="商品访客" :value="number(selectedProduct.visitors)" detail="详情页访客规模" :icon="Eye" tone="blue" /><MetricCard label="支付转化率" :value="ratio(selectedConversion)" detail="支付买家 / 商品访客" :icon="Target" tone="teal" /><MetricCard label="推广投入" :value="currency(selectedProduct.promotion_spend)" detail="商品日报推广消耗" :icon="BarChart3" tone="amber" /></section>
    <section class="product-analysis-grid"><article class="panel product-analysis-trend"><div class="panel-heading"><div><p>商品趋势</p><h2>支付、访客与买家</h2></div><BarChart3 :size="18" /></div><BusinessChart v-if="daily.length" :option="trendOption" ariaLabel="单品支付金额访客和支付买家趋势" :height="300" /><EmptyState v-else title="暂无商品日趋势" detail="所选区间没有该商品的日报记录。" :icon="Filter" /></article><article class="panel product-analysis-diagnostic"><div class="panel-heading"><div><p>商品指标</p><h2>成交集中度与互动</h2></div><UsersRound :size="18" /></div><div class="product-analysis-signals"><div><span>Top 1 成交集中度</span><strong>{{ topOneShare.toFixed(1) }}%</strong><small>全量商品成交占比</small></div><div><span>Top 3 成交集中度</span><strong>{{ topThreeShare.toFixed(1) }}%</strong><small>全量商品成交占比</small></div><div><span>加购人数</span><strong>{{ number(selectedProduct.add_cart_users) }}</strong><small>当前区间</small></div><div><span>收藏人数</span><strong>{{ number(selectedProduct.favorite_users) }}</strong><small>当前区间</small></div></div><p class="panel-footnote">集中度按当前区间全量商品支付金额计算。</p></article></section>
    <section class="product-analysis-grid"><article class="panel"><div class="panel-heading"><div><p>系列对比</p><h2>{{ selectedProduct.series || "未分类系列" }}成交贡献</h2></div><span class="panel-action">同系列商品</span></div><BusinessChart v-if="analysis?.peers?.length" :option="peerOption" ariaLabel="同系列商品成交金额对比" :height="300" /><EmptyState v-else title="暂无系列对比" detail="当前商品没有可比较的同系列商品。" /></article><article class="panel product-analysis-detail"><div class="panel-heading"><div><p>商品明细</p><h2>当前商品经营数据</h2></div><ShoppingCart :size="18" /></div><div class="product-analysis-detail-list"><div><span>支付买家</span><strong>{{ number(selectedProduct.buyers) }}</strong></div><div><span>加购人数</span><strong>{{ number(selectedProduct.add_cart_users) }}</strong></div><div><span>收藏人数</span><strong>{{ number(selectedProduct.favorite_users) }}</strong></div><div><span>商品浏览量</span><strong>{{ number(selectedProduct.page_views) }}</strong></div><div><span>搜索引导访客</span><strong>{{ number(selectedProduct.search_visitors) }}</strong></div><div><span>数据范围</span><strong>{{ compactRange(dashboard.range_start, dashboard.range_end) }}</strong></div></div></article></section>
    <section class="panel product-analysis-table"><div class="panel-heading"><div><p>商品排名</p><h2>成交贡献明细</h2></div><span class="panel-action">共 {{ number(products.length) }} 个商品</span></div><div class="product-analysis-rows"><div class="product-analysis-row product-analysis-row-head"><span>排名 / 商品</span><span>访客</span><span>买家</span><span>转化</span><span>支付金额</span><span>推广投入</span></div><div v-for="item in productRows" :key="item.product_id" class="product-analysis-row"><strong><i>{{ String(item.rank).padStart(2, "0") }}</i><span>{{ item.product_name }}</span><small>{{ item.product_id }} · {{ item.series || "未分类" }}</small></strong><span>{{ number(item.visitors) }}</span><span>{{ number(item.buyers) }}</span><span>{{ ratio(item.conversionRate) }}</span><span>{{ currency(item.paid_amount) }}</span><span>{{ currency(item.promotion_spend) }}</span></div></div></section>
  </template>
  <section v-else-if="loading" class="loading-panel"><span>正在读取商品日报</span></section>
  <section v-else-if="error" class="error-panel"><CircleAlert :size="22" /><div><strong>单品分析暂不可用</strong><p>{{ error }}</p></div><button type="button" @click="load">重试</button></section>
  <section v-else class="empty-state"><PackageSearch :size="24" /><div><strong>暂无商品日报</strong><p>当前店铺没有可用于单品分析的商品排行数据。</p></div></section>
</template>

<style scoped>
.product-analysis-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 18px; margin: 2px 2px 15px; }
.product-analysis-heading p, .product-analysis-panel p { margin: 0 0 5px; color: #21845f; font-size: 11px; font-weight: 700; }
.product-analysis-heading h1 { margin: 0; color: #20342a; font-size: 24px; font-weight: 750; }
.product-analysis-heading span { display: block; margin-top: 7px; color: #7e8e85; font-size: 12px; }
.product-analysis-refresh { display: inline-flex; align-items: center; gap: 6px; min-height: 32px; border: 1px solid #bedaca; border-radius: 4px; padding: 0 10px; color: #176b4b; background: #eff9f3; font-size: 11px; }
.product-analysis-toolbar { display: flex; align-items: flex-end; gap: 11px; margin-bottom: 16px; border: 1px solid #dce8e1; border-radius: 6px; padding: 13px 15px; background: #fff; }
.product-analysis-toolbar label { display: grid; gap: 6px; min-width: 150px; }
.product-analysis-toolbar label span { color: #73837a; font-size: 10px; }
.product-analysis-toolbar select { width: 100%; min-width: 0; max-width: 100%; min-height: 33px; border: 1px solid #ccdcd2; border-radius: 4px; padding: 0 9px; color: #32483d; background: #fbfdfc; font: inherit; font-size: 11px; }
.product-analysis-search { position: relative; display: grid; min-width: 260px; flex: 1; gap: 6px; }
.product-analysis-search > span { color: #73837a; font-size: 10px; }
.product-analysis-search-input { display: flex; min-height: 33px; align-items: center; gap: 7px; border: 1px solid #ccdcd2; border-radius: 4px; padding: 0 8px; color: #75877d; background: #fbfdfc; }
.product-analysis-search-input:focus-within { border-color: #55a881; box-shadow: 0 0 0 2px rgba(45, 155, 112, .11); background: #fff; }
.product-analysis-search-input input { width: 100%; min-width: 0; border: 0; outline: 0; color: #32483d; background: transparent; font: inherit; font-size: 11px; }
.product-analysis-search-input input::-webkit-search-cancel-button { display: none; }
.product-analysis-search-input button { display: grid; width: 24px; height: 24px; flex: 0 0 auto; place-items: center; border: 0; border-radius: 4px; color: #829188; background: transparent; }
.product-analysis-search-input button:hover { color: #176b4b; background: #edf7f1; }
.product-analysis-search-results { position: absolute; z-index: 20; top: calc(100% + 5px); right: 0; left: 0; overflow-y: auto; max-height: 310px; border: 1px solid #cbdcd2; border-radius: 6px; padding: 5px; background: #fff; box-shadow: 0 12px 28px rgba(37, 67, 52, .14); }
.product-analysis-search-results button { display: grid; width: 100%; gap: 4px; border: 0; border-radius: 4px; padding: 9px 10px; color: #40574a; background: transparent; text-align: left; }
.product-analysis-search-results button:hover, .product-analysis-search-results button[aria-selected="true"] { background: #eff8f3; }
.product-analysis-search-results strong { overflow: hidden; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.product-analysis-search-results small { overflow: hidden; color: #87958e; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.product-analysis-search-results p { margin: 0; padding: 13px 10px; color: #87958e; font-size: 10px; text-align: center; }
.product-analysis-select { min-width: 280px !important; flex: 1; }
.product-analysis-coverage { margin-left: auto; padding-bottom: 8px; color: #87958e; font-size: 10px; white-space: nowrap; }
.product-analysis-identity { display: flex; align-items: center; gap: 13px; margin-bottom: 16px; border: 1px solid #cfe4d7; border-radius: 6px; padding: 15px 17px; background: #f7fcf9; }
.product-analysis-icon { display: grid; width: 44px; height: 44px; flex: 0 0 auto; place-items: center; border: 1px solid #bfe0cc; border-radius: 6px; color: #21845f; background: #eff9f3; }
.product-analysis-identity p { margin: 0 0 4px; color: #21845f; font-size: 10px; font-weight: 700; }
.product-analysis-identity h2 { margin: 0; color: #263b30; font-size: 17px; }
.product-analysis-identity span { display: block; margin-top: 5px; color: #839187; font-size: 10px; }
.product-analysis-meta { display: grid; gap: 3px; margin-left: auto; text-align: right; }
.product-analysis-meta span, .product-analysis-meta small { color: #829188; font-size: 9px; }
.product-analysis-meta strong { color: #21845f; font-size: 17px; }
.product-analysis-grid { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(340px, .85fr); gap: 16px; margin-top: 16px; }
.product-analysis-grid > .panel { min-width: 0; overflow: hidden; }
.product-analysis-signals { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1px; margin-top: 16px; background: #e3ece7; }
.product-analysis-signals > div { display: grid; gap: 6px; min-height: 90px; padding: 13px; background: #fbfdfc; }
.product-analysis-signals span, .product-analysis-signals small { color: #84928a; font-size: 9px; }
.product-analysis-signals strong { color: #2f4d3e; font-size: 16px; }
.product-analysis-detail-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1px; margin-top: 14px; background: #e3ece7; }
.product-analysis-detail-list div { display: grid; gap: 6px; padding: 13px; background: #fbfdfc; }
.product-analysis-detail-list span { color: #84928a; font-size: 9px; }
.product-analysis-detail-list strong { color: #2f4d3e; font-size: 13px; }
.product-analysis-table { margin-top: 16px; overflow: hidden; }
.product-analysis-rows { margin-top: 12px; overflow-x: auto; border: 1px solid #e5ece8; border-radius: 5px; }
.product-analysis-row { display: grid; grid-template-columns: minmax(280px, 2fr) 90px 90px 90px 130px 130px; min-width: 820px; min-height: 53px; align-items: center; gap: 14px; border-bottom: 1px solid #edf2ef; padding: 0 14px; color: #687970; font-size: 10px; font-variant-numeric: tabular-nums; }
.product-analysis-row:last-child { border-bottom: 0; }
.product-analysis-row > :not(:first-child) { text-align: right; }
.product-analysis-row strong { display: grid; grid-template-columns: 28px minmax(0, 1fr); gap: 4px 8px; min-width: 0; color: #40574a; font-size: 11px; text-align: left; }
.product-analysis-row strong i { grid-row: span 2; color: #89a095; font-size: 9px; font-style: normal; }
.product-analysis-row strong span, .product-analysis-row strong small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.product-analysis-row strong small { color: #94a199; font-size: 9px; font-weight: 400; }
.product-analysis-row-head { min-height: 34px; color: #96a29b; background: #f7faf8; font-size: 9px; font-weight: 650; }
@media (max-width: 900px) { .product-analysis-grid { grid-template-columns: 1fr; } }
@media (max-width: 900px) { .product-analysis-toolbar { flex-wrap: wrap; } .product-analysis-search { min-width: 300px; } .product-analysis-coverage { width: 100%; margin-left: 0; padding-bottom: 0; } }
@media (max-width: 650px) { .product-analysis-heading { align-items: flex-start; flex-direction: column; } .product-analysis-toolbar { align-items: stretch; } .product-analysis-toolbar label, .product-analysis-select, .product-analysis-search { width: 100%; min-width: 0 !important; max-width: 100%; flex-basis: 100%; } .product-analysis-identity { align-items: flex-start; flex-wrap: wrap; } .product-analysis-meta { width: 100%; margin-left: 57px; text-align: left; } .product-analysis-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
