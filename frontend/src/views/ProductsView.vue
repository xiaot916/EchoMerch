<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  BadgePercent,
  CircleDollarSign,
  Eye,
  Gauge,
  PackageCheck,
  ShoppingCart,
  TrendingDown,
  TrendingUp,
} from "lucide-vue-next"

import EmptyState from "@/components/EmptyState.vue"
import BusinessChart from "@/components/BusinessChart.vue"
import BusinessActionTable from "@/components/BusinessActionTable.vue"
import MetricCard from "@/components/MetricCard.vue"
import { fetchAnalyticsProducts, fetchStores } from "@/api"
import { useDashboard } from "@/composables/useDashboard"
import { compactRange, currency, number, ratio } from "@/lib/format"
import type { BusinessActionRow } from "@/lib/businessDecision"
import type { ProductMetric } from "@/types"

const { dashboard, currentStoreId } = useDashboard()
const products = ref<ProductMetric[]>([])
const fullLoading = ref(false)
const fullError = ref("")
type PositioningBucket = "正装" | "MINI装" | "试用装" | "其他"
const POSITIONING_ORDER: PositioningBucket[] = ["正装", "MINI装", "试用装", "其他"]
const selectedPositioning = ref<PositioningBucket>("正装")
const selectedSeries = ref("")
type ProductSortKey = "paid_amount" | "visitors" | "buyers" | "conversionRate" | "contribution"
const detailSortKey = ref<ProductSortKey>("paid_amount")
const detailSortDirection = ref<"asc" | "desc">("desc")
const detailPage = ref(1)
const detailPageSize = ref(20)
const focusProducts = computed(() => products.value.slice(0, 8))
const productCount = computed(() => products.value.length)
const hasProducts = computed(() => productCount.value > 0)

function normalizePositioning(value: string): PositioningBucket {
  const normalized = (value || "").trim()
  if (normalized.includes("正装")) return "正装"
  if (/mini/i.test(normalized)) return "MINI装"
  if (normalized.includes("试用")) return "试用装"
  return "其他"
}

const positioningBreakdown = computed(() => {
  const grouped = new Map<PositioningBucket, ProductMetric[]>(POSITIONING_ORDER.map((name) => [name, []]))
  for (const item of products.value) grouped.get(normalizePositioning(item.positioning))!.push(item)
  const total = products.value.reduce((sum, item) => sum + item.paid_amount, 0)
  return POSITIONING_ORDER.map((name) => {
    const items = grouped.get(name)!.slice().sort((left, right) => right.paid_amount - left.paid_amount)
    const amount = items.reduce((sum, item) => sum + item.paid_amount, 0)
    return {
      name,
      items,
      amount,
      share: total ? amount / total * 100 : 0,
      seriesCount: new Set(items.map((item) => item.series || "未分类系列")).size,
    }
  })
})
const selectedPositioningNode = computed(() => positioningBreakdown.value.find((item) => item.name === selectedPositioning.value))
const seriesBreakdown = computed(() => {
  const grouped = new Map<string, ProductMetric[]>()
  for (const item of selectedPositioningNode.value?.items ?? []) {
    const series = item.series || "未分类系列"
    if (!grouped.has(series)) grouped.set(series, [])
    grouped.get(series)!.push(item)
  }
  const total = selectedPositioningNode.value?.amount ?? 0
  return [...grouped.entries()].map(([series, rawItems]) => {
    const items = rawItems.slice().sort((left, right) => right.paid_amount - left.paid_amount)
    const amount = items.reduce((sum, item) => sum + item.paid_amount, 0)
    return { series, items, amount, share: total ? amount / total * 100 : 0 }
  }).sort((left, right) => right.amount - left.amount)
})
const selectedSeriesNode = computed(() => seriesBreakdown.value.find((item) => item.series === selectedSeries.value))
const selectedHierarchyItems = computed(() => selectedSeriesNode.value?.items ?? selectedPositioningNode.value?.items ?? [])
const selectedHierarchyAmount = computed(() => selectedHierarchyItems.value.reduce((sum, item) => sum + item.paid_amount, 0))
const selectedHierarchyShare = computed(() => {
  const denominator = selectedSeries.value ? selectedPositioningNode.value?.amount ?? 0 : topProductsTotal.value
  return denominator ? selectedHierarchyAmount.value / denominator * 100 : 0
})
const selectedHierarchyProductRows = computed(() => selectedHierarchyItems.value.map((item) => ({
  ...item,
  scopeShare: selectedHierarchyAmount.value ? item.paid_amount / selectedHierarchyAmount.value * 100 : 0,
})))
const productConversionRate = computed(() => {
  const valid = focusProducts.value.filter((item) => item.visitors > 0 && item.buyers <= item.visitors)
  const visitors = valid.reduce((total, item) => total + item.visitors, 0)
  const buyers = valid.reduce((total, item) => total + item.buyers, 0)
  return visitors ? (buyers / visitors) * 100 : 0
})
const topProductsTotal = computed(() => products.value.reduce((total, item) => total + item.paid_amount, 0))
const allProductVisitors = computed(() => products.value.reduce((total, item) => total + item.visitors, 0))
const allProductBuyers = computed(() => products.value.reduce((total, item) => total + item.buyers, 0))
const allProductConversion = computed(() => allProductVisitors.value ? (allProductBuyers.value / allProductVisitors.value) * 100 : 0)
const topThreeAmount = computed(() => products.value.slice(0, 3).reduce((total, item) => total + item.paid_amount, 0))
const topOneShare = computed(() => topProductsTotal.value ? (products.value[0].paid_amount / topProductsTotal.value) * 100 : 0)
const topThreeShare = computed(() => topProductsTotal.value ? (topThreeAmount.value / topProductsTotal.value) * 100 : 0)

const productRows = computed(() => products.value.map((item, index) => ({
  ...item,
  rank: index + 1,
  conversionRate: item.visitors ? (item.buyers / item.visitors) * 100 : 0,
  contribution: topProductsTotal.value ? (item.paid_amount / topProductsTotal.value) * 100 : 0,
})))

const sortedProductRows = computed(() => {
  const rows = [...productRows.value]
  const key = detailSortKey.value
  const direction = detailSortDirection.value === "asc" ? 1 : -1
  return rows.sort((left, right) => {
    const leftValue = Number(left[key]) || 0
    const rightValue = Number(right[key]) || 0
    if (leftValue !== rightValue) return (leftValue - rightValue) * direction
    return left.product_name.localeCompare(right.product_name, "zh-CN")
  })
})

const detailPageCount = computed(() => Math.max(1, Math.ceil(sortedProductRows.value.length / detailPageSize.value)))
const pagedProductRows = computed(() => {
  const page = Math.min(detailPage.value, detailPageCount.value)
  const start = (page - 1) * detailPageSize.value
  return sortedProductRows.value.slice(start, start + detailPageSize.value)
})
const detailStart = computed(() => sortedProductRows.value.length ? (detailPage.value - 1) * detailPageSize.value + 1 : 0)
const detailEnd = computed(() => Math.min(detailPage.value * detailPageSize.value, sortedProductRows.value.length))
const detailPageNumbers = computed(() => {
  const count = detailPageCount.value
  const current = detailPage.value
  const start = Math.max(1, Math.min(current - 2, count - 4))
  return Array.from({ length: Math.min(5, count) }, (_, index) => start + index)
})

const highestConversion = computed(() => {
  const qualified = productRows.value.filter((item) => item.visitors >= 50 && item.conversionRate <= 100)
  return [...(qualified.length ? qualified : productRows.value)].sort((left, right) => right.conversionRate - left.conversionRate)[0]
})
const highestTrafficLowConversion = computed(() => {
  if (!productRows.value.length) return undefined
  const average = productConversionRate.value
  return [...productRows.value]
    .filter((item) => item.visitors >= 50 && item.conversionRate < average)
    .sort((left, right) => right.visitors - left.visitors)[0]
})
const rangeMismatch = computed(() => {
  if (!dashboard.value) return false
  return dashboard.value.range_start !== dashboard.value.product_range_start || dashboard.value.range_end !== dashboard.value.product_range_end
})

const efficiencyOption = computed(() => ({
  color: ["#35a979"], tooltip: { trigger: "item", formatter: (params: { data: [number, number, number, string] }) => `${params.data[3]}<br/>访客 ${params.data[0].toLocaleString("zh-CN")}<br/>转化 ${params.data[1].toFixed(2)}%<br/>成交 ${currency(params.data[2])}` },
  grid: { left: 56, right: 24, top: 22, bottom: 42 }, xAxis: { name: "访客", type: "value", splitLine: { lineStyle: { color: "#edf1ef" } } }, yAxis: { name: "转化率", type: "value", axisLabel: { formatter: "{value}%" }, splitLine: { lineStyle: { color: "#edf1ef" } } },
  series: [{ type: "scatter", symbolSize: (value: [number, number, number]) => Math.max(14, Math.min(50, Math.sqrt(value[2]) / 7)), data: focusProducts.value.map((item) => [item.visitors, item.visitors ? item.buyers / item.visitors * 100 : 0, item.paid_amount, productLabel(item.product_name, 14)]) }],
}))

async function loadFullProducts(): Promise<void> {
  if (!dashboard.value) return
  fullLoading.value = true
  fullError.value = ""
  try {
    const stores = await fetchStores()
    products.value = await fetchAnalyticsProducts(dashboard.value.range_start, dashboard.value.range_end, currentStoreId.value ?? stores[0]?.store_id)
  } catch (exc) {
    fullError.value = exc instanceof Error ? exc.message : "商品全量数据读取失败"
    products.value = dashboard.value?.top_products ?? []
  } finally {
    fullLoading.value = false
  }
}
function selectPositioning(positioning: PositioningBucket): void {
  selectedPositioning.value = positioning
  selectedSeries.value = ""
}
function selectSeries(series: string): void { selectedSeries.value = selectedSeries.value === series ? "" : series }
function conversionLabel(value: number): string { return value > 100 ? "口径异常" : ratio(value) }
function conversionDetail(item: { conversionRate: number; buyers: number; visitors: number }): string { return item.conversionRate > 100 ? `支付买家 ${number(item.buyers)} > 访客 ${number(item.visitors)}，不纳入高转化判断` : ratio(item.conversionRate) }
function sortLabel(key: ProductSortKey): string {
  return { paid_amount: "支付金额", visitors: "访客", buyers: "买家", conversionRate: "转化率", contribution: "贡献占比" }[key]
}
function toggleDetailSort(key: ProductSortKey): void {
  if (detailSortKey.value === key) detailSortDirection.value = detailSortDirection.value === "desc" ? "asc" : "desc"
  else { detailSortKey.value = key; detailSortDirection.value = "desc" }
  detailPage.value = 1
}
function sortIcon(key: ProductSortKey): typeof ArrowUpDown {
  if (detailSortKey.value !== key) return ArrowUpDown
  return detailSortDirection.value === "desc" ? ArrowDown : ArrowUp
}
function setDetailPage(page: number): void { detailPage.value = Math.max(1, Math.min(page, detailPageCount.value)) }
watch(() => [dashboard.value?.range_start, dashboard.value?.range_end], () => { detailPage.value = 1; void loadFullProducts() })
watch(detailPageSize, () => { detailPage.value = 1 })
watch(positioningBreakdown, (items) => {
  if (!items.find((item) => item.name === selectedPositioning.value && item.items.length)) {
    selectedPositioning.value = items.find((item) => item.items.length)?.name ?? "正装"
  }
  if (selectedSeries.value && !seriesBreakdown.value.some((item) => item.series === selectedSeries.value)) selectedSeries.value = ""
})
onMounted(() => { void loadFullProducts() })

const productActionRows = computed<BusinessActionRow[]>(() => {
  const rows: BusinessActionRow[] = []
  const averageConversion = allProductConversion.value
  const highTrafficLowConversion = productRows.value
    .filter((item) => item.visitors >= allProductVisitors.value / Math.max(productCount.value, 1) && item.visitors > 50 && item.conversionRate <= averageConversion * .75 && item.conversionRate <= 100)
    .sort((left, right) => right.visitors - left.visitors)[0]
  if (highTrafficLowConversion) rows.push({ id: `low-cvr-${highTrafficLowConversion.product_id}`, priority: "P0", object: highTrafficLowConversion.product_name, issue: "高流量低转化", evidence: `${number(highTrafficLowConversion.visitors)} 访客，转化 ${ratio(highTrafficLowConversion.conversionRate)}，商品整体 ${ratio(averageConversion)}`, impact: currency(highTrafficLowConversion.paid_amount), action: "检查详情首屏卖点、价格权益、评价和可售状态，暂缓继续加大引流。", validation: "支付转化率、加购率、支付金额", window: "3-7 天", tone: "risk", to: { name: "product-analysis", query: { product_id: highTrafficLowConversion.product_id } } })
  const topConcentration = topThreeShare.value
  if (topConcentration >= 70 && products.value.length >= 3) rows.push({ id: "concentration", priority: "P1", object: "Top 3 商品", issue: "成交集中度过高", evidence: `Top 3 占全量商品支付 ${topConcentration.toFixed(1)}%`, impact: currency(topThreeAmount.value), action: "为第二梯队商品补充曝光和关联销售，降低单品依赖；先按系列拆解验证。", validation: "Top 3 占比、第二梯队支付金额", window: "7-14 天", tone: "warning" })
  const miniProducts = products.value.filter((item) => /mini|尝鲜|试用/i.test(`${item.product_name} ${item.positioning} ${item.product_type}`))
  if (miniProducts.length) {
    const miniAmount = miniProducts.reduce((sum, item) => sum + item.paid_amount, 0)
    rows.push({ id: "mini", priority: "P1", object: "MINI/尝鲜商品", issue: "需要验证试用到正装承接", evidence: `${miniProducts.length} 个商品，支付金额 ${currency(miniAmount)}`, impact: currency(miniAmount), action: "进入单品分析核对商品 ID、正装绑定、推广、问大家和库存覆盖。", validation: "正装绑定率、正装首购/复购", window: "7-30 天", tone: "opportunity", to: { name: "product-analysis", query: { product_id: miniProducts[0].product_id } } })
  }
  const noTraffic = productRows.value.filter((item) => item.paid_amount > 0 && item.visitors === 0).sort((left, right) => right.paid_amount - left.paid_amount)[0]
  if (noTraffic) rows.push({ id: `quality-${noTraffic.product_id}`, priority: "P0", object: noTraffic.product_name, issue: "支付金额存在但商品访客为零", evidence: `支付 ${currency(noTraffic.paid_amount)}，访客 0`, impact: currency(noTraffic.paid_amount), action: "核对商品日报字段与统计口径，不把异常数据用于转化判断。", validation: "商品访客、买家和日报原始记录", window: "1 天", tone: "risk", to: { name: "product-analysis", query: { product_id: noTraffic.product_id } } })
  return rows.slice(0, 4)
})

function productLabel(value: string, max = 22): string {
  return value.length > max ? `${value.slice(0, max)}…` : value
}
</script>

<template>
  <template v-if="dashboard">
    <section class="product-page-heading">
      <div>
        <h1>商品表现</h1>
        <span>商品、系列与装型</span>
      </div>
      <div class="product-page-meta">
        <span><PackageCheck :size="15" /> {{ fullLoading ? "正在读取全量商品" : `全量覆盖 ${productCount} 个商品` }}</span>
        <small v-if="fullError">全量接口异常，当前回退仪表盘商品：{{ fullError }}</small>
        <small v-if="rangeMismatch">商品数据实际覆盖 {{ compactRange(dashboard.product_range_start, dashboard.product_range_end) }}</small>
      </div>
    </section>

    <section class="metrics-grid product-metrics">
      <MetricCard label="全量商品支付金额" :value="hasProducts ? currency(topProductsTotal) : '暂无'" :detail="`${productCount} 个商品全量汇总`" :icon="CircleDollarSign" tone="teal" />
      <MetricCard label="商品访客人次" :value="hasProducts ? number(products.reduce((sum, item) => sum + item.visitors, 0)) : '暂无'" detail="商品日报逐商品加总，非全店去重 UV" :icon="Eye" tone="blue" />
      <MetricCard label="商品支付买家人次" :value="hasProducts ? number(products.reduce((sum, item) => sum + item.buyers, 0)) : '暂无'" detail="商品日报逐商品加总，跨商品可能重复" :icon="ShoppingCart" tone="amber" />
      <MetricCard label="商品整体转化" :value="hasProducts ? ratio(allProductConversion) : '暂无'" detail="有效商品买家人次 / 访客人次" :icon="BadgePercent" tone="coral" />
    </section>

    <section class="panel product-hierarchy-panel">
      <div class="panel-heading"><div><p>货品结构</p><h2>装型 → 系列 → 商品</h2></div><span class="panel-action">占比分母随选择联动</span></div>
      <div v-if="positioningBreakdown.some((item) => item.items.length)" class="product-structure-content">
        <div class="product-positioning-tabs" aria-label="商品装型选择">
          <button v-for="item in positioningBreakdown" :key="item.name" type="button" :class="{ active: selectedPositioning === item.name }" :disabled="!item.items.length" @click="selectPositioning(item.name)">
            <span><strong>{{ item.name }}</strong><em>{{ item.share.toFixed(1) }}%</em></span>
            <small>{{ currency(item.amount) }} · {{ number(item.items.length) }} 商品</small>
            <i><b :style="{ width: `${Math.min(item.share, 100)}%` }"></b></i>
          </button>
        </div>
        <div class="product-structure-caption">
          <strong>{{ selectedPositioning }}占全店商品成交 {{ (selectedPositioningNode?.share ?? 0).toFixed(1) }}%</strong>
          <span>下面的系列占比以 {{ selectedPositioning }}成交 {{ currency(selectedPositioningNode?.amount ?? 0) }} 为 100%</span>
        </div>
        <div class="product-hierarchy-layout">
          <div class="product-series-share-list">
            <button v-for="item in seriesBreakdown" :key="item.series" type="button" :class="{ active: selectedSeries === item.series }" @click="selectSeries(item.series)">
              <span><strong>{{ item.series }}</strong><em>{{ item.share.toFixed(1) }}%</em></span>
              <i><b :style="{ width: `${Math.min(item.share, 100)}%` }"></b></i>
              <small>{{ currency(item.amount) }} · {{ number(item.items.length) }} 商品</small>
            </button>
          </div>
          <div class="product-hierarchy-detail">
            <header><div><p>商品贡献</p><h3>{{ selectedPositioning }}{{ selectedSeries ? ` / ${selectedSeries}` : " / 全部系列" }}</h3></div><button v-if="selectedSeries" type="button" @click="selectedSeries = ''">返回装型</button></header>
            <div class="product-hierarchy-summary"><div><span>商品数</span><strong>{{ number(selectedHierarchyItems.length) }}</strong></div><div><span>支付金额</span><strong>{{ currency(selectedHierarchyAmount) }}</strong></div><div><span>{{ selectedSeries ? "装型内占比" : "全店占比" }}</span><strong>{{ selectedHierarchyShare.toFixed(1) }}%</strong></div><div><span>系列数</span><strong>{{ selectedSeries ? 1 : number(seriesBreakdown.length) }}</strong></div></div>
            <div class="product-hierarchy-products"><article v-for="item in selectedHierarchyProductRows.slice(0, 30)" :key="item.product_id"><div><strong :title="item.product_name">{{ item.product_name }}</strong><small>{{ item.series || "未分类系列" }} · {{ item.positioning || "未分类定位" }} · ID {{ item.product_id }}</small><i><b :style="{ width: `${Math.min(item.scopeShare, 100)}%` }"></b></i></div><span><strong>{{ currency(item.paid_amount) }}</strong><small>{{ item.scopeShare.toFixed(1) }}%</small></span></article></div>
          </div>
        </div>
      </div>
      <EmptyState v-else title="暂无商品层级" detail="商品档案与商品日报关联后显示装型、系列和商品层级。" />
    </section>

    <section class="product-analysis-grid">
      <article class="panel product-contribution-panel">
        <div class="panel-heading"><div><p>商品效率</p><h2>访客规模、转化率与成交</h2></div><span class="panel-action">气泡大小代表支付金额</span></div>
        <BusinessChart v-if="hasProducts" :option="efficiencyOption" ariaLabel="商品访客转化率和成交金额气泡图" :height="330" />
        <EmptyState v-else title="暂无商品效率图" detail="所选范围没有已入库的商品排行数据。" />
      </article>

      <article class="panel product-diagnostic-panel">
        <div class="panel-heading"><div><p>商品指标</p><h2>转化与成交集中度</h2></div><Gauge :size="18" /></div>
        <div v-if="hasProducts" class="product-diagnostic-list">
          <div class="product-diagnostic-item"><div class="diagnostic-icon positive"><TrendingUp :size="16" /></div><div><span>高转化商品</span><strong :title="highestConversion?.product_name">{{ highestConversion ? productLabel(highestConversion.product_name) : "当前无法判断" }}</strong><small>{{ highestConversion ? `${conversionDetail(highestConversion)} · ${number(highestConversion.visitors)} 访客` : "样本不足" }}</small></div></div>
          <div class="product-diagnostic-item"><div class="diagnostic-icon warning"><TrendingDown :size="16" /></div><div><span>高流量低转化</span><strong :title="highestTrafficLowConversion?.product_name">{{ highestTrafficLowConversion ? productLabel(highestTrafficLowConversion.product_name) : "当前未发现明显样本" }}</strong><small>{{ highestTrafficLowConversion ? `${number(highestTrafficLowConversion.visitors)} 访客 · ${ratio(highestTrafficLowConversion.conversionRate)}` : "按当前商品平均转化率判断" }}</small></div></div>
          <div class="product-concentration"><div><span>Top 1 成交集中度</span><strong>{{ topOneShare.toFixed(1) }}%</strong></div><div><span>Top 3 成交集中度</span><strong>{{ topThreeShare.toFixed(1) }}%</strong></div></div>
        </div>
        <EmptyState v-else title="暂无商品指标" detail="当前区间没有商品排行数据。" />
      </article>
    </section>

    <BusinessActionTable :rows="productActionRows" eyebrow="商品决策" title="需要下钻的商品对象" note="流量承接、集中度与数据质量" />

    <section class="panel product-detail-panel">
      <div class="panel-heading product-detail-heading"><div><p>商品排名</p><h2>全量商品明细</h2></div><span class="panel-action">共 {{ productCount }} 个 · 当前按{{ sortLabel(detailSortKey) }}{{ detailSortDirection === "desc" ? "降序" : "升序" }}</span></div>
      <div v-if="sortedProductRows.length" class="product-detail-table-wrap">
        <div class="product-detail-table product-detail-table-head">
          <span>排名 / 商品</span>
          <button type="button" class="product-sort-head" @click="toggleDetailSort('visitors')">访客 <component :is="sortIcon('visitors')" :size="12" /></button>
          <button type="button" class="product-sort-head" @click="toggleDetailSort('buyers')">买家 <component :is="sortIcon('buyers')" :size="12" /></button>
          <button type="button" class="product-sort-head" @click="toggleDetailSort('conversionRate')">转化率 <component :is="sortIcon('conversionRate')" :size="12" /></button>
          <button type="button" class="product-sort-head" @click="toggleDetailSort('paid_amount')">支付金额 <component :is="sortIcon('paid_amount')" :size="12" /></button>
          <button type="button" class="product-sort-head" @click="toggleDetailSort('contribution')">贡献占比 <component :is="sortIcon('contribution')" :size="12" /></button>
        </div>
        <div class="product-detail-table product-detail-table-total">
          <strong>当前范围合计</strong><span>{{ number(allProductVisitors) }}</span><span>{{ number(allProductBuyers) }}</span><span>{{ ratio(allProductConversion) }}</span><strong>{{ currency(topProductsTotal) }}</strong><strong>100%</strong>
        </div>
        <article v-for="(item, rowIndex) in pagedProductRows" :key="item.product_id" class="product-detail-table product-detail-item">
          <div class="product-detail-copy"><div class="product-rank">{{ String((detailPage - 1) * detailPageSize + rowIndex + 1).padStart(2, "0") }}</div><div><strong :title="item.product_name">{{ item.product_name }}</strong><span>{{ item.series || "未分类系列" }} · {{ item.positioning || "未分类定位" }} · ID {{ item.product_id }}</span></div></div>
          <strong>{{ number(item.visitors) }}</strong>
          <strong>{{ number(item.buyers) }}</strong>
          <strong :title="item.conversionRate > 100 ? '支付买家数高于访客数，源数据口径异常，未修正' : ''">{{ conversionLabel(item.conversionRate) }}</strong>
          <strong class="product-money">{{ currency(item.paid_amount) }}</strong>
          <div class="product-share"><div><i :style="{ width: `${Math.min(item.contribution, 100)}%` }"></i></div><strong>{{ item.contribution.toFixed(1) }}%</strong></div>
        </article>
      </div>
      <EmptyState v-else title="暂无商品明细" detail="所选范围没有已入库的商品排行数据。" />
      <div v-if="sortedProductRows.length" class="product-detail-pagination"><span>显示 {{ detailStart }}–{{ detailEnd }} / {{ productCount }} 个商品</span><label>每页 <select v-model.number="detailPageSize"><option :value="10">10</option><option :value="20">20</option><option :value="50">50</option><option :value="100">100</option></select> 条</label><div class="product-page-buttons"><button type="button" :disabled="detailPage <= 1" @click="setDetailPage(detailPage - 1)">上一页</button><button v-for="page in detailPageNumbers" :key="page" type="button" :class="{ active: page === detailPage }" @click="setDetailPage(page)">{{ page }}</button><button type="button" :disabled="detailPage >= detailPageCount" @click="setDetailPage(detailPage + 1)">下一页</button></div></div>
    </section>
  </template>
</template>

<style scoped>
.product-hierarchy-panel { margin-top: 16px; overflow: hidden; }
.product-structure-content { display: grid; gap: 13px; margin-top: 14px; }
.product-positioning-tabs { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.product-positioning-tabs button { display: grid; min-width: 0; gap: 8px; border: 1px solid #dfe6e2; border-radius: 6px; padding: 12px; color: #475467; background: #fff; text-align: left; cursor: pointer; }
.product-positioning-tabs button:hover:not(:disabled), .product-positioning-tabs button.active { border-color: #4f9a79; background: #f5faf7; box-shadow: 0 0 0 2px rgba(45, 145, 105, .08); }
.product-positioning-tabs button:disabled { cursor: default; opacity: .48; }
.product-positioning-tabs button > span, .product-series-share-list button > span { display: flex; min-width: 0; align-items: center; justify-content: space-between; gap: 8px; }
.product-positioning-tabs strong { color: #34473c; font-size: 13px; }.product-positioning-tabs em { color: #258463; font-size: 15px; font-style: normal; font-weight: 750; }.product-positioning-tabs small { overflow: hidden; color: #8a978f; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.product-positioning-tabs i, .product-series-share-list i, .product-hierarchy-products article > div > i { display: block; height: 5px; overflow: hidden; border-radius: 4px; background: #e7efeb; }
.product-positioning-tabs i b, .product-series-share-list i b, .product-hierarchy-products article > div > i b { display: block; height: 100%; border-radius: inherit; background: #35a979; }
.product-structure-caption { display: flex; align-items: center; justify-content: space-between; gap: 14px; border-left: 3px solid #35a979; padding: 4px 0 4px 11px; }.product-structure-caption strong { color: #34473c; font-size: 11px; }.product-structure-caption span { color: #849188; font-size: 10px; }
.product-hierarchy-layout { display: grid; grid-template-columns: minmax(390px, .95fr) minmax(420px, 1.05fr); gap: 16px; margin-top: 14px; }
.product-series-share-list { display: grid; align-content: start; gap: 7px; max-height: 520px; overflow: auto; padding-right: 3px; }
.product-series-share-list button { display: grid; gap: 7px; border: 1px solid #e2e8e4; border-radius: 5px; padding: 10px 11px; color: #475467; background: #fff; text-align: left; cursor: pointer; }.product-series-share-list button:hover, .product-series-share-list button.active { border-color: #5d9c80; background: #f7faf8; }.product-series-share-list strong { overflow: hidden; color: #34473c; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }.product-series-share-list em { color: #258463; font-size: 11px; font-style: normal; font-weight: 750; }.product-series-share-list small { color: #8d9992; font-size: 9px; }
.product-hierarchy-detail { min-width: 0; border: 1px solid #e1e8f0; border-radius: 5px; padding: 14px; background: #fbfcfe; }.product-hierarchy-detail > header { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }.product-hierarchy-detail p { margin: 0 0 4px; color: #21845f; font-size: 10px; font-weight: 700; }.product-hierarchy-detail h3 { margin: 0; overflow: hidden; color: #344054; font-size: 14px; text-overflow: ellipsis; white-space: nowrap; }.product-hierarchy-detail header button { border: 1px solid #cbd8e8; border-radius: 4px; padding: 5px 8px; color: #356ae6; background: #fff; font-size: 10px; cursor: pointer; }
.product-hierarchy-summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 1px; margin: 13px 0; background: #e1e8f0; }.product-hierarchy-summary > div { display: grid; gap: 5px; padding: 10px; background: #fff; }.product-hierarchy-summary span { color: #98a2b3; font-size: 9px; }.product-hierarchy-summary strong { color: #344054; font-size: 12px; }
.product-hierarchy-products { display: grid; max-height: 440px; overflow-y: auto; }.product-hierarchy-products article { display: grid; grid-template-columns: minmax(0, 1fr) auto; min-height: 62px; align-items: center; gap: 14px; border-bottom: 1px solid #edf0f4; }.product-hierarchy-products article > div { min-width: 0; }.product-hierarchy-products article > div > i { margin-top: 7px; }.product-hierarchy-products strong, .product-hierarchy-products small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.product-hierarchy-products strong { color: #475467; font-size: 10px; }.product-hierarchy-products small { margin-top: 4px; color: #98a2b3; font-size: 9px; }.product-hierarchy-products article > span { display: grid; flex: 0 0 auto; gap: 3px; text-align: right; }.product-hierarchy-products article > span strong { color: #258463; }.product-hierarchy-products article > span small { margin: 0; }
.product-detail-heading { align-items: end; }
.product-detail-table-wrap { margin-top: 12px; overflow-x: auto; border-top: 1px solid #dfe6ed; }
.product-detail-table { display: grid; grid-template-columns: minmax(360px, 2fr) minmax(92px, .55fr) minmax(84px, .48fr) minmax(90px, .5fr) minmax(132px, .72fr) minmax(130px, .7fr); min-width: 980px; align-items: center; column-gap: 14px; font-variant-numeric: tabular-nums; }
.product-detail-table > :not(:first-child) { text-align: right; }
.product-detail-table-head { position: sticky; top: 0; z-index: 2; min-height: 38px; border-bottom: 1px solid #dfe6ed; color: #8491a1; background: #fff; font-size: 10px; }
.product-sort-head { display: inline-flex; min-height: 30px; align-items: center; justify-content: flex-end; gap: 4px; border: 0; padding: 0; color: inherit; background: transparent; font: inherit; cursor: pointer; }
.product-sort-head:hover { color: #2b63d9; }
.product-detail-table-total { min-height: 43px; border-bottom: 1px solid #d8e2ec; color: #47647b; background: #f4f8fb; font-size: 11px; }
.product-detail-table-total > :first-child { padding-left: 8px; color: #27485d; }
.product-detail-table-total strong { font-size: 12px; }
.product-detail-table.product-detail-item { min-height: 58px; border-bottom: 1px solid #edf1f4; padding: 5px 0; }
.product-detail-table.product-detail-item:hover { background: #f9fbfc; }
.product-detail-table.product-detail-item > strong { color: #526879; font-size: 11px; font-weight: 650; }
.product-detail-table.product-detail-item > .product-money { color: #207a5d; }
.product-detail-copy { display: grid; grid-template-columns: 38px minmax(0, 1fr); align-items: center; min-width: 0; padding-left: 5px; text-align: left; }
.product-detail-copy > div:last-child { min-width: 0; }
.product-detail-copy strong, .product-detail-copy span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.product-detail-copy strong { color: #344d43; font-size: 11px; font-weight: 680; }
.product-detail-copy span { margin-top: 4px; color: #96a39f; font-size: 9px; }
.product-rank { color: #32aa7d; font-size: 12px; font-weight: 750; }
.product-share { display: grid; grid-template-columns: minmax(55px, 1fr) 38px; align-items: center; gap: 8px; }
.product-share > div { height: 5px; overflow: hidden; border-radius: 4px; background: #e7efeb; }
.product-share i { display: block; height: 100%; border-radius: inherit; background: #3db286; }
.product-share strong { color: #668074; font-size: 10px; }
.product-detail-pagination { display: flex; min-height: 52px; align-items: center; justify-content: flex-end; gap: 14px; border-top: 1px solid #edf1f4; color: #7c8998; font-size: 10px; }
.product-detail-pagination > span { margin-right: auto; }
.product-detail-pagination label { display: inline-flex; align-items: center; gap: 6px; }
.product-detail-pagination select { height: 29px; border: 1px solid #d8e1e9; border-radius: 4px; padding: 0 6px; color: #536579; background: #fff; }
.product-page-buttons { display: inline-flex; gap: 4px; }
.product-page-buttons button { min-width: 30px; height: 29px; border: 1px solid #d8e1e9; border-radius: 4px; padding: 0 8px; color: #536579; background: #fff; font-size: 10px; }
.product-page-buttons button.active { border-color: #356ae6; color: #fff; background: #356ae6; }
.product-page-buttons button:disabled { opacity: .42; }
@media (max-width: 1050px) { .product-positioning-tabs { grid-template-columns: repeat(2, minmax(0, 1fr)); }.product-hierarchy-layout { grid-template-columns: 1fr; } }
@media (max-width: 720px) { .product-detail-heading { align-items: flex-start; flex-direction: column; gap: 8px; }.product-detail-pagination { align-items: flex-start; flex-wrap: wrap; padding: 12px 0; }.product-detail-pagination > span { width: 100%; margin-right: 0; }.product-page-buttons { overflow-x: auto; max-width: 100%; } }
@media (max-width: 620px) { .product-positioning-tabs { grid-template-columns: 1fr; }.product-structure-caption { align-items: flex-start; flex-direction: column; }.product-hierarchy-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
