<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue"
import { AlertTriangle, BarChart3, CheckCircle2, Database, Filter, HelpCircle, History, LoaderCircle, MessageCircle, RefreshCw, Search, ShieldCheck, Tags, Wrench } from "lucide-vue-next"

import BusinessChart from "@/components/BusinessChart.vue"
import EmptyState from "@/components/EmptyState.vue"
import ReviewWordCloud from "@/components/ReviewWordCloud.vue"
import { collectAsks, collectReviews, fetchAskSummary, fetchAsks, fetchReviewAnalysis, fetchReviewProducts, fetchReviewSeries, fetchReviewSummary, fetchReviews } from "@/api"
import { useAuth } from "@/composables/useAuth"
import type { AskRecord, AskSummary, ReviewAnalysis, ReviewCollectionSummary, ReviewRecord } from "@/types"
import { number } from "@/lib/format"

type Scope = "all" | "product" | "series"
type InsightMode = "reviews" | "asks"
type AnswerFilter = "all" | "answered" | "unanswered"
type SentimentFilter = "all" | "positive" | "neutral" | "negative" | "unknown"
type ReviewOptions = { productId?: string; series?: string; sentiment?: "positive" | "neutral" | "negative" | "unknown"; startDate?: string; endDate?: string }

const pageSizeOptions = [10, 20, 30, 50]
const insightMode = ref<InsightMode>("reviews")
const summary = ref<ReviewCollectionSummary | null>(null)
const analysis = ref<ReviewAnalysis | null>(null)
const products = ref<Array<{ item_id: string; item_name: string | null; series: string | null; review_count: number }>>([])
const series = ref<Array<{ series: string; review_count: number; product_count: number }>>([])

const reviews = ref<ReviewRecord[]>([])
const reviewTotal = ref(0)
const reviewPage = ref(1)
const reviewPageSize = ref(20)
const reviewJumpPage = ref("")
const scope = ref<Scope>("all")
const productId = ref("")
const seriesName = ref("")
const category = ref("")
const sentiment = ref<SentimentFilter>("all")
const search = ref("")
const startDate = ref("")
const endDate = ref("")

const askSummary = ref<AskSummary | null>(null)
const asks = ref<AskRecord[]>([])
const askTotal = ref(0)
const askPage = ref(1)
const askPageSize = ref(20)
const askJumpPage = ref("")
const askProductId = ref("")
const askSeriesName = ref("")
const askCategory = ref("")
const askSearch = ref("")
const askHasAnswer = ref<AnswerFilter>("all")
const asksLoaded = ref(false)

const loading = ref(true)
const analysisLoading = ref(false)
const askLoading = ref(false)
const error = ref("")
const reviewRequestToken = ref(0)
const { can } = useAuth()
const canManageCollection = computed(() => can("data.manage"))
const collectionStarting = ref(false)
const collectionError = ref("")
const collectionNotice = ref("")
let collectionNoticeTimer: number | undefined

const selectedProduct = computed(() => products.value.find(item => item.item_id === productId.value))
const categories = computed(() => analysis.value?.category_counts || [])
const riskProducts = computed(() => analysis.value?.risk_products || [])
const riskSeries = computed(() => analysis.value?.risk_series || [])
const issueCloudItems = computed(() => categories.value.map(item => ({ name: item.name, count: item.count })))
const topCategories = computed(() => categories.value.slice(0, 8))
const competitorRank = computed(() => (analysis.value?.competitor_counts || []).slice(0, 10))
const competitorMax = computed(() => competitorRank.value[0]?.count || 1)
const scopeLabel = computed(() => scope.value === "product" ? selectedProduct.value?.item_name || productId.value : scope.value === "series" ? seriesName.value : "全部评价")
const topIssue = computed(() => categories.value[0] || null)
const reviewPageCount = computed(() => Math.max(1, Math.ceil(reviewTotal.value / reviewPageSize.value)))
const askPageCount = computed(() => Math.max(1, Math.ceil(askTotal.value / askPageSize.value)))
const reviewPageNumbers = computed(() => nearbyPages(reviewPage.value, reviewPageCount.value))
const askPageNumbers = computed(() => nearbyPages(askPage.value, askPageCount.value))
const askCategories = computed(() => askSummary.value?.category_counts || [])
const topAskCategory = computed(() => askCategories.value[0] || null)
const diagnosis = computed(() => {
  if (!analysis.value || !analysis.value.total_reviews) return "当前范围暂无可用评价样本，先完成评价采集再做商品质量判断。"
  if (!topIssue.value) return `当前范围有 ${number(analysis.value.total_reviews)} 条评价，但关键词规则暂未识别出集中问题，建议结合原文抽样复核。`
  return `“${topIssue.value.name}”共识别 ${number(topIssue.value.count)} 条，占评价 ${topIssue.value.share.toFixed(2)}%。当前问题评价率 ${analysis.value.negative_rate.toFixed(2)}%，该指标来自文本问题关键词识别，不等同平台官方差评率或售后率。`
})
const sentimentLabelText = computed(() => sentiment.value === "positive" ? "平台好评" : sentiment.value === "neutral" ? "平台中评" : sentiment.value === "negative" ? "平台差评" : sentiment.value === "unknown" ? "等级未知" : "全部等级")
const analysisStatusText = computed(() => {
  if (analysisLoading.value) return `正在筛选${sentimentLabelText.value}…`
  return `${sentimentLabelText.value} · ${number(reviewTotal.value)} 条评价`
})
const askDiagnosis = computed(() => {
  if (!askSummary.value?.total_questions) return "当前暂无顾客提问。采集后可用它识别购买前最常见的顾虑。"
  if (!topAskCategory.value) return `当前已有 ${number(askSummary.value.total_questions)} 条顾客提问，建议从未回答问题和高频原文开始整理商品 FAQ。`
  return `“${topAskCategory.value.name}”是当前最集中的购买疑虑，共 ${number(topAskCategory.value.count)} 条。建议优先补进商品详情页、客服快捷回复和直播讲解话术，并复核未回答问题。`
})
const trendOption = computed(() => {
  const rows = analysis.value?.trend || []
  return { color: ["#35a979", "#e09b46"], tooltip: { trigger: "axis" }, legend: { bottom: 0, data: ["评价数", "问题评价数"], textStyle: { color: "#718179", fontSize: 11 } }, grid: { left: 42, right: 18, top: 16, bottom: 44 }, xAxis: { type: "category", data: rows.map(row => row.day.slice(5)), axisLabel: { color: "#829188" } }, yAxis: { type: "value", splitLine: { lineStyle: { color: "#edf1ef" } } }, series: [{ name: "评价数", type: "line", smooth: true, showSymbol: false, data: rows.map(row => row.total) }, { name: "问题评价数", type: "line", smooth: true, showSymbol: false, data: rows.map(row => row.negative) }] }
})
const categoryOption = computed(() => ({ color: ["#35a979"], tooltip: { trigger: "axis", axisPointer: { type: "shadow" } }, grid: { left: 92, right: 20, top: 16, bottom: 26 }, xAxis: { type: "value", splitLine: { lineStyle: { color: "#edf1ef" } } }, yAxis: { type: "category", data: topCategories.value.map(item => item.name).reverse(), axisLabel: { color: "#718179" } }, series: [{ type: "bar", barMaxWidth: 20, data: topCategories.value.map(item => item.count).reverse() }] }))

function nearbyPages(current: number, total: number): number[] {
  const start = Math.max(1, Math.min(current - 2, total - 4))
  const end = Math.min(total, Math.max(current + 2, 5))
  return Array.from({ length: end - start + 1 }, (_, index) => start + index)
}

function currentReviewOptions(): ReviewOptions {
  return { productId: scope.value === "product" ? productId.value : undefined, series: scope.value === "series" ? seriesName.value : undefined, sentiment: sentiment.value === "all" ? undefined : sentiment.value, startDate: startDate.value || undefined, endDate: endDate.value || undefined }
}

async function loadAnalysis(): Promise<void> {
  analysisLoading.value = true
  error.value = ""
  const requestToken = ++reviewRequestToken.value
  try {
    const options = currentReviewOptions()
    const [nextAnalysis, nextReviews] = await Promise.all([
      fetchReviewAnalysis(options),
      fetchReviews({ ...options, category: category.value || undefined, sentiment: sentiment.value === "all" ? undefined : sentiment.value, search: search.value || undefined, page: reviewPage.value, pageSize: reviewPageSize.value }),
    ])
    if (requestToken !== reviewRequestToken.value) return
    analysis.value = nextAnalysis
    reviews.value = nextReviews.items
    reviewTotal.value = nextReviews.total
  } catch (requestError) {
    if (requestToken !== reviewRequestToken.value) return
    error.value = requestError instanceof Error ? requestError.message : "评价分析读取失败。"
  } finally {
    if (requestToken === reviewRequestToken.value) analysisLoading.value = false
  }
}

async function loadReviews(options = currentReviewOptions()): Promise<void> {
  const response = await fetchReviews({ ...options, category: category.value || undefined, sentiment: sentiment.value === "all" ? undefined : sentiment.value, search: search.value || undefined, page: reviewPage.value, pageSize: reviewPageSize.value })
  reviews.value = response.items
  reviewTotal.value = response.total
}

async function loadAskData(refreshSummary = false): Promise<void> {
  askLoading.value = true
  error.value = ""
  try {
    const hasAnswer = askHasAnswer.value === "all" ? undefined : askHasAnswer.value === "answered"
    const askRequest = fetchAsks({ productId: askProductId.value || undefined, series: askSeriesName.value || undefined, category: askCategory.value || undefined, search: askSearch.value || undefined, hasAnswer, page: askPage.value, pageSize: askPageSize.value })
    const [response, refreshedSummary] = await Promise.all([askRequest, refreshSummary ? fetchAskSummary() : Promise.resolve(null)])
    asks.value = response.items
    askTotal.value = response.total
    if (refreshedSummary) askSummary.value = refreshedSummary
    asksLoaded.value = true
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : "问大家数据读取失败。"
  } finally { askLoading.value = false }
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ""
  try {
    const metadata = Promise.all([fetchReviewSummary(), fetchReviewProducts(), fetchReviewSeries(), fetchAskSummary()])
      .then(([nextSummary, nextProducts, nextSeries, nextAskSummary]) => {
        summary.value = nextSummary
        products.value = nextProducts
        series.value = nextSeries
        askSummary.value = nextAskSummary
      })
    await Promise.all([metadata, loadAnalysis()])
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : "用户反馈数据读取失败。"
  } finally { loading.value = false }
}

function setInsightMode(next: InsightMode): void {
  insightMode.value = next
  error.value = ""
  if (next === "asks" && !asksLoaded.value) void loadAskData()
}

function setScope(next: Scope): void {
  scope.value = next
  if (next === "product" && !productId.value) productId.value = products.value[0]?.item_id || ""
  if (next === "series" && !seriesName.value) seriesName.value = series.value[0]?.series || ""
  reviewPage.value = 1
  void loadAnalysis()
}

function queryReviews(): void { reviewPage.value = 1; void loadAnalysis() }
function categoryClick(name: string): void { category.value = category.value === name ? "" : name; reviewPage.value = 1; void loadReviews() }
function competitorClick(name: string): void { search.value = search.value === name ? "" : name; category.value = ""; reviewPage.value = 1; void loadReviews() }
function changeSentiment(): void { category.value = ""; reviewPage.value = 1; void loadAnalysis() }
function resetReviewFilters(): void { category.value = ""; sentiment.value = "all"; search.value = ""; startDate.value = ""; endDate.value = ""; reviewPage.value = 1; void loadAnalysis() }
function openRiskProduct(itemId: string): void { scope.value = "product"; productId.value = itemId; category.value = ""; search.value = ""; reviewPage.value = 1; void loadAnalysis() }
function openRiskSeries(name: string): void { scope.value = "series"; seriesName.value = name; category.value = ""; search.value = ""; reviewPage.value = 1; void loadAnalysis() }
function changeReviewPage(next: number): void { reviewPage.value = Math.min(reviewPageCount.value, Math.max(1, next)); reviewJumpPage.value = ""; void loadReviews() }
function changeReviewPageSize(): void { reviewPage.value = 1; reviewJumpPage.value = ""; void loadReviews() }
function jumpReviewPage(): void { const target = Number.parseInt(reviewJumpPage.value, 10); if (Number.isFinite(target)) changeReviewPage(target) }

function queryAsks(): void { askPage.value = 1; void loadAskData() }
function askCategoryClick(name: string): void { askCategory.value = askCategory.value === name ? "" : name; askPage.value = 1; void loadAskData() }
function changeAskPage(next: number): void { askPage.value = Math.min(askPageCount.value, Math.max(1, next)); askJumpPage.value = ""; void loadAskData() }
function changeAskPageSize(): void { askPage.value = 1; askJumpPage.value = ""; void loadAskData() }
function jumpAskPage(): void { const target = Number.parseInt(askJumpPage.value, 10); if (Number.isFinite(target)) changeAskPage(target) }
function resetAskFilters(): void { askProductId.value = ""; askSeriesName.value = ""; askCategory.value = ""; askSearch.value = ""; askHasAnswer.value = "all"; askPage.value = 1; void loadAskData() }
function mediaCount(review: ReviewRecord): number { return review.main_media.length + review.append_media.length }
function reviewPreview(review: ReviewRecord): string { return review.merged_content || "（该评价没有文字内容）" }
function sentimentLabel(review: ReviewRecord): string {
  if (review.sentiment === "positive") return "平台好评"
  if (review.sentiment === "neutral") return "平台中评"
  if (review.sentiment === "negative") return "平台差评"
  return "评价等级未知"
}

async function startFeedbackCollection(): Promise<void> {
  collectionStarting.value = true
  collectionError.value = ""
  collectionNotice.value = ""
  try {
    if (insightMode.value === "reviews") await collectReviews("incremental")
    else await collectAsks("incremental")
    collectionNotice.value = insightMode.value === "reviews"
      ? "评价采集任务已启动，后台会自动打开或复用采集浏览器。"
      : "问大家采集任务已启动，后台会自动打开或复用采集浏览器。"
    if (collectionNoticeTimer !== undefined) window.clearTimeout(collectionNoticeTimer)
    collectionNoticeTimer = window.setTimeout(() => { collectionNotice.value = "" }, 8000)
  } catch (requestError) {
    collectionError.value = requestError instanceof Error ? requestError.message : "采集任务启动失败。"
  } finally {
    collectionStarting.value = false
  }
}

onMounted(() => { void load() })
onUnmounted(() => {
  if (collectionNoticeTimer !== undefined) window.clearTimeout(collectionNoticeTimer)
})
</script>

<template>
  <section class="review-page">
    <header class="review-hero">
      <div><h1>{{ insightMode === 'reviews' ? '评价分析' : '问大家' }}</h1><span>{{ insightMode === 'reviews' ? '评价、问题类型、商品和系列。' : '顾客提问、回答状态和疑虑类型。' }}</span></div>
      <div v-if="canManageCollection" class="review-hero-actions">
        <button type="button" class="review-action" :disabled="collectionStarting" @click="startFeedbackCollection"><LoaderCircle v-if="collectionStarting" :size="15" class="spinning" /><RefreshCw v-else :size="15" />{{ collectionStarting ? '启动中' : insightMode === 'reviews' ? '采集新评价' : '采集新问答' }}</button>
        <RouterLink class="review-action secondary" to="/imports/tasks"><History :size="15" />查看任务记录</RouterLink>
      </div>
    </header>

    <section v-if="collectionNotice || collectionError" class="review-collection-feedback" :class="{ error: collectionError }"><AlertTriangle v-if="collectionError" :size="16" /><CheckCircle2 v-else :size="16" /><span>{{ collectionError || collectionNotice }}</span></section>

    <nav class="insight-switch" aria-label="用户反馈分析模式"><button type="button" :class="{ active: insightMode === 'reviews' }" @click="setInsightMode('reviews')"><BarChart3 :size="16" />评价分析</button><button type="button" :class="{ active: insightMode === 'asks' }" @click="setInsightMode('asks')"><MessageCircle :size="16" />问大家洞察</button></nav>

    <section v-if="loading && !summary" class="review-state"><LoaderCircle :size="25" class="spinning" /><span>正在读取用户反馈库</span></section>
    <section v-else-if="error" class="review-state error"><AlertTriangle :size="22" /><span>{{ error }}</span><button type="button" @click="insightMode === 'reviews' ? load() : loadAskData(true)">重试</button></section>
    <section v-else-if="insightMode === 'reviews' && !analysis" class="review-state"><LoaderCircle :size="25" class="spinning" /><span>正在分析评价内容，请稍候</span></section>

    <template v-else-if="insightMode === 'reviews'">
      <section class="review-kpis"><article><Database :size="17" /><span>评价总数</span><strong>{{ number(analysis?.total_reviews || 0) }}</strong><small>{{ scope === 'all' ? `${summary?.first_review_date || '--'} 至 ${summary?.latest_review_date || '--'}` : scopeLabel }}</small></article><article><AlertTriangle :size="17" /><span>问题评价率</span><strong>{{ (analysis?.negative_rate || 0).toFixed(2) }}%</strong><small>{{ number(analysis?.negative_reviews || 0) }} 条关键词识别问题</small></article><article><Tags :size="17" /><span>问题类型</span><strong>{{ number(analysis?.category_counts.length || 0) }}</strong><small>不含单独竞品提及</small></article><article><ShieldCheck :size="17" /><span>追评 / 媒体评价</span><strong>{{ number(analysis?.append_reviews || 0) }} / {{ number(analysis?.media_reviews || 0) }}</strong><small>主评与追评已合并</small></article></section>

      <section class="review-toolbar"><div class="review-tabs"><button :class="{ active: scope === 'all' }" @click="setScope('all')">全部评价</button><button :class="{ active: scope === 'product' }" @click="setScope('product')">单品分析</button><button :class="{ active: scope === 'series' }" @click="setScope('series')">系列分析</button></div><select v-if="scope === 'product'" v-model="productId" @change="queryReviews"><option value="">选择商品</option><option v-for="product in products" :key="product.item_id" :value="product.item_id">{{ product.item_id }} · {{ product.item_name || '未命名商品' }}</option></select><select v-if="scope === 'series'" v-model="seriesName" @change="queryReviews"><option value="">选择系列</option><option v-for="item in series" :key="item.series" :value="item.series">{{ item.series }} · {{ item.review_count }} 条</option></select><select v-model="sentiment" aria-label="平台评价等级" @change="changeSentiment"><option value="all">全部评价等级</option><option value="positive">平台好评</option><option value="neutral">平台中评</option><option value="negative">平台差评</option><option value="unknown">等级未知</option></select><input v-model="startDate" type="date" aria-label="开始日期" /><input v-model="endDate" type="date" aria-label="结束日期" /><input v-model="search" placeholder="搜索评价或商品" @keyup.enter="queryReviews" /><button type="button" class="review-query" :disabled="analysisLoading" @click="queryReviews"><Search :size="15" />查询</button><button type="button" class="filter-reset" @click="resetReviewFilters">重置</button></section>

      <section class="review-scope-note"><Filter :size="16" /><span>当前分析范围：<strong>{{ scopeLabel }}</strong>。评价等级：<strong>{{ sentimentLabelText }}</strong>。单品分析只读取所选商品 ID。</span><small>平台等级与文本问题分开；“没有红屁股、不漏尿”不会计入问题</small><em v-if="analysisLoading" class="review-filter-status"><LoaderCircle :size="13" class="spinning" />{{ analysisStatusText }}</em><em v-else class="review-filter-status">{{ analysisStatusText }}</em></section>
      <section class="review-diagnosis"><div><p>商品质量</p><h2>问题评价</h2></div><Wrench :size="18" /><span>{{ diagnosis }}</span></section>

      <section class="review-chart-grid"><article class="review-panel"><header><div><p>问题类型分布</p><h2>问题类型排行</h2></div><BarChart3 :size="18" /></header><BusinessChart v-if="topCategories.length" :key="`category-${scope}-${productId}-${seriesName}-${sentiment}-${startDate}-${endDate}`" :option="categoryOption" ariaLabel="问题类型排行" :height="300" /><EmptyState v-else title="暂无分类结果" detail="采集评价后，系统会按关键词生成问题类型。" /></article><article class="review-panel"><header><div><p>评价趋势</p><h2>评价量与问题评价量</h2></div><BarChart3 :size="18" /></header><BusinessChart v-if="analysis?.trend.length" :key="`trend-${scope}-${productId}-${seriesName}-${sentiment}-${startDate}-${endDate}`" :option="trendOption" ariaLabel="评价量与问题评价趋势" :height="300" /><EmptyState v-else title="暂无趋势数据" detail="当前筛选范围没有带日期的评价。" /></article></section>

      <section class="review-chart-grid review-risk-grid"><article class="review-panel"><header><div><p>商品风险</p><h2>问题商品</h2></div><AlertTriangle :size="18" /></header><div v-if="riskProducts.length" class="review-risk-list"><button v-for="item in riskProducts" :key="item.key" type="button" @click="openRiskProduct(item.key)"><span><strong>{{ item.label }}</strong><small>{{ item.series || '未归类系列' }} · {{ item.top_issue || '未分类问题' }}</small></span><em>{{ item.issue_reviews }} / {{ item.total_reviews }} 条</em><b>{{ item.issue_rate.toFixed(2) }}%</b></button></div><EmptyState v-else title="暂无商品风险" detail="当前范围未识别到商品问题评价。" /></article><article class="review-panel"><header><div><p>系列风险</p><h2>问题最集中的产品系列</h2></div><Tags :size="18" /></header><div v-if="riskSeries.length" class="review-risk-list"><button v-for="item in riskSeries" :key="item.key" type="button" @click="openRiskSeries(item.key)"><span><strong>{{ item.label }}</strong><small>{{ item.top_issue || '未分类问题' }}</small></span><em>{{ item.issue_reviews }} / {{ item.total_reviews }} 条</em><b>{{ item.issue_rate.toFixed(2) }}%</b></button></div><EmptyState v-else title="暂无系列风险" detail="当前范围未识别到系列问题评价。" /></article></section>

      <section class="review-lower-grid"><article class="review-panel"><header><div><p>问题词云</p><h2>点击问题词筛选评价明细</h2></div><Tags :size="18" /></header><ReviewWordCloud v-if="issueCloudItems.length" :key="`cloud-${scope}-${productId}-${seriesName}-${sentiment}-${startDate}-${endDate}`" :items="issueCloudItems" ariaLabel="评价问题词云" @select="categoryClick" /><EmptyState v-else title="暂无问题词" detail="当前范围未识别到问题关键词。" /></article><article class="review-panel"><header><div><p>竞品提及</p><h2>品牌提及次数与占比</h2></div><BarChart3 :size="18" /></header><div v-if="competitorRank.length" class="competitor-rank-grid"><button v-for="(item, index) in competitorRank" :key="item.name" type="button" :class="{ selected: search === item.name }" @click="competitorClick(item.name)"><span class="competitor-rank">{{ index + 1 }}</span><span class="competitor-name">{{ item.name }}</span><strong>{{ number(item.count) }} 次</strong><small>占当前评价 {{ item.share.toFixed(2) }}%</small><i><em :style="{ width: `${item.count / competitorMax * 100}%` }"></em></i></button></div><EmptyState v-else title="暂无竞品提及" detail="当前范围未识别到竞品品牌。" /></article></section>

      <section class="review-panel review-table-panel"><header><div><p>评价明细</p><h2>{{ reviewTotal ? `共 ${number(reviewTotal)} 条评价` : '暂无评价明细' }}</h2></div><span class="review-panel-note">第 {{ reviewPage }} / {{ reviewPageCount }} 页 · 每页 {{ reviewPageSize }} 条</span></header><div v-if="reviews.length" class="review-table-wrap"><table class="review-data-table"><thead><tr><th>评价时间</th><th>商品</th><th>评价内容</th><th>识别到的问题</th><th>用户 / 订单</th><th>平台等级</th></tr></thead><tbody><tr v-for="review in reviews" :key="review.review_key"><td>{{ review.review_date || '--' }}</td><td><strong>{{ review.item_name || review.item_id || '未命名商品' }}</strong><small>{{ review.series || '未归类系列' }}</small></td><td><p>{{ reviewPreview(review) }}</p><small v-if="review.append_content">含追评 · {{ mediaCount(review) }} 个媒体</small></td><td><div class="table-tags"><button v-for="tag in review.categories" :key="tag" type="button" @click="categoryClick(tag)">{{ tag }}</button><span v-if="!review.categories.length">未识别到问题</span></div></td><td>{{ review.user_name || '匿名用户' }}<small>{{ review.order_id || '--' }}</small></td><td><em :class="review.sentiment">{{ sentimentLabel(review) }}</em><small v-if="review.is_negative">文本含问题证据</small></td></tr></tbody></table><div class="review-pagination"><span class="pagination-total">显示 {{ (reviewPage - 1) * reviewPageSize + 1 }}–{{ Math.min(reviewPage * reviewPageSize, reviewTotal) }} / {{ number(reviewTotal) }} 条</span><label>每页<select v-model.number="reviewPageSize" @change="changeReviewPageSize"><option v-for="size in pageSizeOptions" :key="size" :value="size">{{ size }} 条</option></select></label><div class="pagination-pages"><button type="button" :disabled="reviewPage <= 1 || analysisLoading" @click="changeReviewPage(1)">首页</button><button type="button" :disabled="reviewPage <= 1 || analysisLoading" @click="changeReviewPage(reviewPage - 1)">上一页</button><button v-for="page in reviewPageNumbers" :key="page" type="button" :class="{ active: page === reviewPage }" :disabled="analysisLoading" @click="changeReviewPage(page)">{{ page }}</button><button type="button" :disabled="reviewPage >= reviewPageCount || analysisLoading" @click="changeReviewPage(reviewPage + 1)">下一页</button><button type="button" :disabled="reviewPage >= reviewPageCount || analysisLoading" @click="changeReviewPage(reviewPageCount)">末页</button></div><label class="pagination-jump">跳至<input v-model="reviewJumpPage" inputmode="numeric" aria-label="评价跳转页码" @keyup.enter="jumpReviewPage" />页<button type="button" @click="jumpReviewPage">确定</button></label></div></div><EmptyState v-else title="暂无评价" detail="调整筛选条件，或先执行一次评价采集。" /></section>
    </template>

    <template v-else>
      <section class="ask-intro"><HelpCircle :size="21" /><div><strong>问大家 = 顾客购买前的真实疑虑</strong><span>这里不是普通评价。顾客通常会问尺码是否合适、会不会漏尿、厚不厚、是否适合夏天或新生儿等，用来判断自己要不要买。</span></div></section>

      <section class="review-kpis ask-kpis"><article><Database :size="17" /><span>问题总数</span><strong>{{ number(askSummary?.total_questions || 0) }}</strong><small>{{ askSummary?.first_question_date || '--' }} 至 {{ askSummary?.latest_question_date || '--' }}</small></article><article><CheckCircle2 :size="17" /><span>已回答</span><strong>{{ number(askSummary?.answered_questions || 0) }}</strong><small>回答率 {{ askSummary?.answer_rate || 0 }}%</small></article><article><AlertTriangle :size="17" /><span>待回答</span><strong>{{ number(askSummary?.unanswered_questions || 0) }}</strong><small>建议优先检查高频购买疑虑</small></article><article><Tags :size="17" /><span>涉及商品</span><strong>{{ number(askSummary?.product_count || 0) }}</strong><small>{{ number(askCategories.length) }} 类已识别疑虑</small></article></section>

      <section class="ask-toolbar"><select v-model="askProductId" @change="queryAsks"><option value="">全部商品</option><option v-for="product in products" :key="product.item_id" :value="product.item_id">{{ product.item_id }} · {{ product.item_name || '未命名商品' }}</option></select><select v-model="askSeriesName" @change="queryAsks"><option value="">全部系列</option><option v-for="item in series" :key="item.series" :value="item.series">{{ item.series }}</option></select><select v-model="askHasAnswer" @change="queryAsks"><option value="all">全部回答状态</option><option value="answered">已回答</option><option value="unanswered">待回答</option></select><select v-model="askCategory" @change="queryAsks"><option value="">全部疑虑类型</option><option v-for="item in askCategories" :key="item.name" :value="item.name">{{ item.name }} · {{ item.count }}</option></select><input v-model="askSearch" placeholder="搜索顾客问题或商品" @keyup.enter="queryAsks" /><button type="button" class="review-query" :disabled="askLoading" @click="queryAsks"><Search :size="15" />查询</button><button type="button" class="filter-reset" @click="resetAskFilters">重置</button></section>

      <section class="review-diagnosis ask-diagnosis"><div><p>购买前问题</p><h2>高频疑虑</h2></div><MessageCircle :size="18" /><span>{{ askDiagnosis }}</span></section>

      <section class="review-chart-grid"><article class="review-panel"><header><div><p>购买前疑虑</p><h2>高频问题类型</h2></div><BarChart3 :size="18" /></header><div v-if="askCategories.length" class="ask-category-list"><button v-for="item in askCategories.slice(0, 12)" :key="item.name" type="button" :class="{ selected: askCategory === item.name }" @click="askCategoryClick(item.name)"><span>{{ item.name }}</span><i><em :style="{ width: `${item.count / (askCategories[0]?.count || 1) * 100}%` }"></em></i><strong>{{ number(item.count) }}</strong><small>{{ item.share.toFixed(2) }}%</small></button></div><EmptyState v-else title="暂无疑虑分类" detail="问大家采集后会按问题内容识别顾客疑虑。" /></article><article class="review-panel"><header><div><p>业务应用</p><h2>问题使用场景</h2></div><Wrench :size="18" /></header><div class="ask-actions"><article><strong>商品详情页 FAQ</strong><span>尺码、适用月龄、季节、厚度和使用方法等高频问题。</span></article><article><strong>客服与直播话术</strong><span>高频疑虑的统一回答与口径。</span></article><article><strong>商品与包装验证</strong><span>漏尿、异味、材质等持续集中的疑虑。</span></article><article><strong>待回答问题</strong><span>无人回答且影响购买决策的问题。</span></article></div></article></section>

      <section class="review-panel review-table-panel"><header><div><p>问大家明细</p><h2>{{ askTotal ? `共 ${number(askTotal)} 条顾客疑虑` : '暂无顾客提问' }}</h2></div><span class="review-panel-note">第 {{ askPage }} / {{ askPageCount }} 页 · 每页 {{ askPageSize }} 条</span></header><div v-if="askLoading && !asks.length" class="table-loading"><LoaderCircle :size="21" class="spinning" />正在读取顾客问题</div><div v-else-if="asks.length" class="review-table-wrap"><table class="review-data-table ask-data-table"><thead><tr><th>提问时间</th><th>商品</th><th>顾客问题</th><th>疑虑类型</th><th>提问用户</th><th>回答状态</th></tr></thead><tbody><tr v-for="ask in asks" :key="ask.ask_id"><td>{{ ask.question_date || '--' }}</td><td><strong>{{ ask.item_name || ask.item_id || '未命名商品' }}</strong><small>{{ ask.series || '未归类系列' }}</small></td><td><p>{{ ask.question || '（没有问题文本）' }}</p><small v-if="ask.competitors.length">提及竞品：{{ ask.competitors.join('、') }}</small></td><td><div class="table-tags"><button v-for="tag in ask.categories" :key="tag" type="button" @click="askCategoryClick(tag)">{{ tag }}</button><span v-if="!ask.categories.length">未分类</span></div></td><td>{{ ask.user_name || '匿名用户' }}</td><td><em :class="ask.has_answer ? 'normal' : 'negative'">{{ ask.has_answer ? `已回答 · ${ask.answer_count}` : '待回答' }}</em></td></tr></tbody></table><div class="review-pagination"><span class="pagination-total">显示 {{ (askPage - 1) * askPageSize + 1 }}–{{ Math.min(askPage * askPageSize, askTotal) }} / {{ number(askTotal) }} 条</span><label>每页<select v-model.number="askPageSize" @change="changeAskPageSize"><option v-for="size in pageSizeOptions" :key="size" :value="size">{{ size }} 条</option></select></label><div class="pagination-pages"><button type="button" :disabled="askPage <= 1 || askLoading" @click="changeAskPage(1)">首页</button><button type="button" :disabled="askPage <= 1 || askLoading" @click="changeAskPage(askPage - 1)">上一页</button><button v-for="page in askPageNumbers" :key="page" type="button" :class="{ active: page === askPage }" :disabled="askLoading" @click="changeAskPage(page)">{{ page }}</button><button type="button" :disabled="askPage >= askPageCount || askLoading" @click="changeAskPage(askPage + 1)">下一页</button><button type="button" :disabled="askPage >= askPageCount || askLoading" @click="changeAskPage(askPageCount)">末页</button></div><label class="pagination-jump">跳至<input v-model="askJumpPage" inputmode="numeric" aria-label="问大家跳转页码" @keyup.enter="jumpAskPage" />页<button type="button" @click="jumpAskPage">确定</button></label></div></div><EmptyState v-else title="暂无顾客提问" detail="调整筛选条件，或到采集任务执行问大家增量采集。" /></section>
    </template>
  </section>
</template>

<style scoped>
.review-page { display: grid; gap: 16px; padding: 4px 2px 28px; color: #263b30; }
.insight-switch { display: inline-flex; width: fit-content; gap: 4px; padding: 4px; border: 1px solid #dce8e1; border-radius: 7px; background: #f7fbf8; }
.insight-switch button { display: inline-flex; align-items: center; gap: 7px; border: 0; border-radius: 5px; padding: 8px 14px; color: #718179; background: transparent; font: inherit; font-size: 12px; cursor: pointer; }
.insight-switch button.active { color: #176b4b; background: #fff; box-shadow: 0 1px 3px #d7e7dc; font-weight: 700; }
.review-hero { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; }
.review-hero p, .review-panel p { margin: 0 0 5px; color: #21845f; font-size: 11px; font-weight: 700; }
.review-hero h1 { margin: 0; color: #20342a; font-size: 24px; font-weight: 750; }
.review-hero > div:first-child > span { display: block; max-width: 760px; margin-top: 7px; color: #7e8e85; font-size: 12px; line-height: 1.55; }
.review-hero-actions { display: flex; gap: 8px; }
.review-action, .review-query { display: inline-flex; align-items: center; justify-content: center; gap: 7px; min-height: 34px; border: 1px solid #237b58; border-radius: 5px; padding: 0 13px; color: #fff; background: #237b58; font: inherit; font-size: 12px; font-weight: 650; cursor: pointer; }
.review-action.secondary { color: #176b4b; border-color: #bedaca; background: #eff9f3; }
.review-action:disabled, .review-query:disabled { cursor: not-allowed; opacity: .55; }
.review-collection-feedback { display: flex; align-items: center; gap: 8px; margin-top: 12px; border: 1px solid #cfe8d8; padding: 9px 12px; color: #24754f; background: #f0faf3; font-size: 11px; }
.review-collection-feedback.error { border-color: #f0caca; color: #a44d4d; background: #fff4f3; }
.ask-intro { display: flex; align-items: flex-start; gap: 12px; border: 1px solid #d9e8f2; border-radius: 6px; padding: 14px 16px; color: #557080; background: #f6fbff; }
.ask-intro > svg { flex: 0 0 auto; margin-top: 1px; color: #3e8bb2; }
.ask-intro strong, .ask-intro span { display: block; }.ask-intro strong { color: #2c617d; font-size: 13px; }.ask-intro span { margin-top: 5px; color: #718996; font-size: 11px; line-height: 1.55; }
.review-notice, .review-state, .review-scope-note { display: flex; align-items: center; gap: 10px; border: 1px solid #dce8e1; border-radius: 6px; padding: 13px 15px; background: #fff; color: #65776c; font-size: 12px; }
.review-notice.error, .review-state.error { border-color: #ebcccc; color: #a44d4d; background: #fffafa; }
.review-diagnosis { display: grid; grid-template-columns: minmax(190px, .45fr) auto minmax(0, 1.55fr); align-items: center; gap: 14px; border: 1px solid #e6dfca; border-radius: 6px; padding: 14px 16px; background: #fffdf7; color: #6d654f; }
.review-diagnosis p { margin: 0 0 5px; color: #b07b2f; font-size: 11px; font-weight: 700; }
.review-diagnosis h2 { margin: 0; color: #574a32; font-size: 15px; }
.review-diagnosis > svg { color: #b07b2f; }
.review-diagnosis > span { color: #766b54; font-size: 12px; line-height: 1.6; }
.review-state { justify-content: center; min-height: 116px; }
.review-state button { margin-left: auto; border: 0; color: #176b4b; background: transparent; cursor: pointer; }
.review-kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 1px; overflow: hidden; border: 1px solid #dce8e1; border-radius: 6px; background: #dce8e1; }
.review-kpis article { display: grid; grid-template-columns: auto 1fr; align-items: center; column-gap: 8px; gap: 5px; min-height: 96px; padding: 13px 15px; background: #fff; }
.review-kpis svg { grid-row: span 2; color: #21845f; }
.review-kpis span { color: #7a8b81; font-size: 11px; }.review-kpis strong { color: #30473a; font-size: 17px; }.review-kpis small { grid-column: 2; color: #9aa69f; font-size: 10px; }
.review-toolbar { display: flex; align-items: flex-end; flex-wrap: wrap; gap: 9px; padding: 13px 15px; border: 1px solid #dce8e1; border-radius: 6px; background: #fff; }
.review-tabs { display: flex; align-self: stretch; gap: 3px; margin-right: auto; }.review-tabs button { border: 0; border-bottom: 2px solid transparent; padding: 0 10px; color: #7a8b81; background: transparent; font: inherit; font-size: 12px; cursor: pointer; }.review-tabs button.active { border-color: #21845f; color: #21845f; font-weight: 700; }
.review-toolbar select, .review-toolbar input { min-height: 34px; border: 1px solid #ccdcd2; border-radius: 4px; padding: 0 9px; color: #32483d; background: #fbfdfc; font: inherit; font-size: 12px; }.review-toolbar select { min-width: 210px; }.review-toolbar input[type="date"] { min-width: 135px; }.review-toolbar input[placeholder] { min-width: 170px; }
.review-scope-note small { margin-left: auto; color: #87968d; font-size: 10px; }.review-scope-note strong { color: #21845f; }.review-filter-status { display: inline-flex; align-items: center; gap: 5px; border: 1px solid #cce5d7; border-radius: 4px; padding: 4px 7px; color: #176b4b; background: #eff9f3; font-size: 10px; font-style: normal; font-weight: 700; white-space: nowrap; }
.ask-toolbar { display: flex; align-items: flex-end; flex-wrap: wrap; gap: 9px; padding: 13px 15px; border: 1px solid #dce8e1; border-radius: 6px; background: #fff; }.ask-toolbar select, .ask-toolbar input { min-height: 34px; border: 1px solid #ccdcd2; border-radius: 4px; padding: 0 9px; color: #32483d; background: #fbfdfc; font: inherit; font-size: 12px; }.ask-toolbar select { min-width: 150px; }.ask-toolbar input { min-width: 210px; }.filter-reset { min-height: 34px; border: 1px solid #ccdcd2; border-radius: 4px; padding: 0 12px; color: #60746a; background: #fff; font: inherit; font-size: 12px; cursor: pointer; }
.ask-diagnosis { border-color: #d9e8f2; background: #f8fcff; }.ask-diagnosis .review-diagnosis p, .ask-diagnosis p { color: #3e8bb2; }.ask-diagnosis h2, .ask-diagnosis > span { color: #557080; }.ask-diagnosis > svg { color: #3e8bb2; }
.review-chart-grid, .review-lower-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }.review-panel { min-width: 0; overflow: hidden; border: 1px solid #dce8e1; border-radius: 6px; background: #fff; }.review-panel > header { display: flex; min-height: 65px; align-items: center; justify-content: space-between; gap: 12px; padding: 13px 16px; border-bottom: 1px solid #e9efeb; }.review-panel h2 { margin: 0; color: #263b30; font-size: 16px; }.review-panel > header > svg { color: #21845f; }.review-panel-note { color: #87968d; font-size: 10px; }
.review-tag-list { display: flex; flex-wrap: wrap; gap: 8px; padding: 15px; }.review-tag-list button { border: 1px solid #d8e8de; border-radius: 999px; padding: 7px 10px; color: #4c6b5a; background: #f4faf6; font: inherit; font-size: 11px; cursor: pointer; }.review-tag-list button.selected { border-color: #21845f; color: #fff; background: #21845f; }.review-tag-list button strong { margin-left: 4px; }.review-muted { padding: 16px; color: #95a199; font-size: 12px; }
.review-risk-list { display: grid; padding: 4px 15px 12px; }
.review-risk-list button { display: grid; grid-template-columns: minmax(0, 1fr) auto 58px; align-items: center; gap: 10px; border: 0; border-bottom: 1px solid #edf2ee; padding: 11px 0; color: #52675a; background: transparent; text-align: left; cursor: pointer; }
.review-risk-list button:hover { background: #fbfefc; }
.review-risk-list span { min-width: 0; }
.review-risk-list strong, .review-risk-list small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.review-risk-list strong { color: #405449; font-size: 12px; }
.review-risk-list small { margin-top: 4px; color: #96a39b; font-size: 10px; }
.review-risk-list em { color: #7f8e85; font-size: 10px; font-style: normal; text-align: right; }
.review-risk-list b { color: #b06f32; font-size: 12px; text-align: right; }
.review-competitor-list { display: grid; gap: 12px; padding: 16px; }.review-competitor-list > div { display: grid; grid-template-columns: 74px 1fr 34px; align-items: center; gap: 10px; color: #60746a; font-size: 11px; }.review-competitor-list i { height: 6px; overflow: hidden; border-radius: 5px; background: #edf3ef; }.review-competitor-list em { display: block; height: 100%; border-radius: inherit; background: #e0a54b; }.review-competitor-list strong { color: #3e5648; text-align: right; }
.competitor-rank-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 9px; padding: 14px; }
.competitor-rank-grid button { display: grid; grid-template-columns: 24px 1fr auto; align-items: center; gap: 4px 8px; border: 1px solid #e3ece6; border-radius: 6px; padding: 10px; color: #52675a; background: #fbfdfb; text-align: left; cursor: pointer; }
.competitor-rank-grid button.selected { border-color: #21845f; background: #f0faf4; }
.competitor-rank { color: #b38a45; font-size: 11px; font-weight: 750; }
.competitor-name { color: #3d5748; font-size: 12px; font-weight: 700; }
.competitor-rank-grid strong { color: #405449; font-size: 11px; }
.competitor-rank-grid small { grid-column: 2 / 4; color: #8a9a91; font-size: 10px; }
.competitor-rank-grid i { grid-column: 2 / 4; height: 5px; overflow: hidden; border-radius: 99px; background: #e9f1eb; }
.competitor-rank-grid em { display: block; height: 100%; border-radius: inherit; background: #e0a54b; }
.ask-category-list { display: grid; gap: 5px; padding: 13px 15px 15px; }.ask-category-list button { display: grid; grid-template-columns: 94px minmax(80px, 1fr) 40px 54px; align-items: center; gap: 9px; border: 0; padding: 7px 0; color: #587064; background: transparent; font: inherit; font-size: 11px; text-align: left; cursor: pointer; }.ask-category-list button.selected { color: #176b4b; font-weight: 700; }.ask-category-list i { height: 6px; overflow: hidden; border-radius: 99px; background: #edf3ef; }.ask-category-list i em { display: block; height: 100%; border-radius: inherit; background: #5c9fbd; }.ask-category-list strong { color: #405449; font-size: 11px; text-align: right; }.ask-category-list small { color: #96a39b; font-size: 10px; text-align: right; }.ask-actions { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1px; background: #e9efeb; }.ask-actions article { min-height: 90px; padding: 13px 15px; background: #fff; }.ask-actions strong, .ask-actions span { display: block; }.ask-actions strong { color: #405449; font-size: 12px; }.ask-actions span { margin-top: 6px; color: #7f9086; font-size: 10px; line-height: 1.55; }
.review-table-panel { min-height: 200px; }.review-table { padding: 0 15px; }.review-row { display: flex; justify-content: space-between; gap: 18px; border-bottom: 1px solid #edf2ee; padding: 14px 0; }.review-row:last-child { border-bottom: 0; }.review-row-main { min-width: 0; flex: 1; }.review-row-meta { display: flex; align-items: baseline; gap: 10px; }.review-row-meta strong { overflow: hidden; color: #405449; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }.review-row-meta span, .review-row-side span { color: #96a39b; font-size: 10px; }.review-row-main p { margin: 7px 0; overflow: hidden; color: #5c6f63; font-size: 12px; font-weight: 400; line-height: 1.55; text-overflow: ellipsis; white-space: nowrap; }.review-row-tags { display: flex; flex-wrap: wrap; gap: 5px; }.review-row-tags button, .review-row-tags span { border: 0; border-radius: 3px; padding: 3px 6px; color: #557765; background: #f0f7f2; font: inherit; font-size: 9px; cursor: pointer; }.review-row-tags span { color: #9a7a43; background: #fbf6eb; }.review-row-side { display: grid; flex: 0 0 110px; align-content: center; justify-items: end; gap: 4px; }.review-row-side strong { color: #52645a; font-size: 11px; }.review-row-side em { border-radius: 3px; padding: 3px 6px; font-size: 9px; font-style: normal; }.review-row-side em.negative { color: #a44d4d; background: #fff0f0; }.review-row-side em.normal { color: #5f806c; background: #eff8f2; }
.review-table-wrap { overflow-x: auto; padding: 0 15px 14px; }
.review-data-table { width: 100%; min-width: 920px; border-collapse: collapse; table-layout: fixed; }
.review-data-table th { border-bottom: 1px solid #dfeae3; padding: 11px 8px; color: #819087; font-size: 10px; font-weight: 650; text-align: left; white-space: nowrap; }
.review-data-table td { border-bottom: 1px solid #edf2ee; padding: 12px 8px; color: #52675a; font-size: 11px; vertical-align: top; }
.review-data-table tbody tr:hover { background: #fbfefc; }
.review-data-table th:nth-child(1), .review-data-table td:nth-child(1) { width: 136px; }
.review-data-table th:nth-child(2), .review-data-table td:nth-child(2) { width: 190px; }
.review-data-table th:nth-child(3), .review-data-table td:nth-child(3) { width: 310px; }
.review-data-table th:nth-child(4), .review-data-table td:nth-child(4) { width: 145px; }
.review-data-table th:nth-child(5), .review-data-table td:nth-child(5) { width: 130px; }
.review-data-table td strong, .review-data-table td small { display: block; }
.review-data-table td small { margin-top: 4px; color: #96a39b; font-size: 10px; }
.review-data-table td p { display: -webkit-box; margin: 0; overflow: hidden; -webkit-box-orient: vertical; -webkit-line-clamp: 2; line-height: 1.5; }
.table-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.table-tags button { border: 0; border-radius: 3px; padding: 3px 5px; color: #557765; background: #f0f7f2; font-size: 9px; cursor: pointer; }
.review-data-table td em { border-radius: 3px; padding: 3px 6px; font-size: 9px; font-style: normal; white-space: nowrap; }
.review-data-table td em.negative { color: #a44d4d; background: #fff0f0; }
.review-data-table td em.positive, .review-data-table td em.normal { color: #5f806c; background: #eff8f2; }
.review-data-table td em.neutral { color: #946d32; background: #fff7e7; }
.review-pagination { display: flex; align-items: center; flex-wrap: wrap; justify-content: flex-end; gap: 9px; padding-top: 14px; color: #87968d; font-size: 11px; }.pagination-total { margin-right: auto; }
.review-pagination label { display: inline-flex; align-items: center; gap: 5px; white-space: nowrap; }.review-pagination select, .review-pagination input { min-height: 28px; border: 1px solid #d8e5dc; border-radius: 4px; padding: 0 6px; color: #557765; background: #fff; font: inherit; font-size: 11px; }.review-pagination input { width: 46px; text-align: center; }.pagination-pages { display: inline-flex; gap: 4px; }.review-pagination button { border: 1px solid #d8e5dc; border-radius: 4px; padding: 6px 9px; color: #557765; background: #fff; font: inherit; cursor: pointer; }.review-pagination button.active { border-color: #21845f; color: #fff; background: #21845f; }
.review-pagination button:disabled { cursor: not-allowed; opacity: .45; }
.pagination-jump button { padding: 5px 8px; }.table-loading { display: flex; align-items: center; justify-content: center; gap: 8px; min-height: 140px; color: #87968d; font-size: 12px; }
@media (max-width: 900px) { .review-hero { align-items: flex-start; flex-direction: column; }.review-hero-actions { width: 100%; }.review-action { flex: 1; }.review-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }.review-chart-grid, .review-lower-grid { grid-template-columns: 1fr; }.competitor-rank-grid { grid-template-columns: 1fr; }.review-toolbar { align-items: stretch; flex-direction: column; }.review-tabs { min-height: 34px; margin-right: 0; }.review-toolbar select, .review-toolbar input, .review-query { width: 100%; }.review-scope-note { align-items: flex-start; flex-wrap: wrap; }.review-scope-note small { width: 100%; margin-left: 26px; }.review-diagnosis { grid-template-columns: 1fr auto; }.review-diagnosis > span { grid-column: 1 / -1; } }
@media (max-width: 560px) { .review-kpis { grid-template-columns: 1fr; }.review-row { align-items: flex-start; flex-direction: column; }.review-row-side { width: 100%; flex: auto; align-items: start; justify-items: start; }.review-row-main p { white-space: normal; }.ask-actions { grid-template-columns: 1fr; }.ask-category-list button { grid-template-columns: 82px minmax(50px, 1fr) 32px 44px; }.pagination-total { width: 100%; margin-right: 0; } }
</style>
