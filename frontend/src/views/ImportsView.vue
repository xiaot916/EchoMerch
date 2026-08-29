<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue"
import {
  CheckCircle2,
  CircleAlert,
  DatabaseZap,
  FileLock2,
  History,
  LoaderCircle,
  Play,
  RefreshCw,
} from "lucide-vue-next"

import {
  createDryRunImportRun,
  fetchCollectionBatches,
  fetchCrawlRun,
  fetchCrawlRuns,
  fetchDailyDryRun,
  fetchImportRun,
  fetchImportRuns,
  collectReviews,
  collectAsks,
  startDailyCollection,
  startCollectionBrowser,
  fetchAskRuns,
  fetchReviewRuns,
} from "@/api"
import type {
  CrawlRun,
  CrawlRunDetail,
  CrawlRunDay,
  DailyDryRunSummary,
  ImportCandidate,
  ImportRun,
  ImportRunDetail,
  ImportRunItem,
  ReviewCollectionRun,
  CollectionBatch,
} from "@/types"
import { number } from "@/lib/format"

const plan = ref<DailyDryRunSummary | null>(null)
const activeRun = ref<ImportRunDetail | null>(null)
const runs = ref<ImportRun[]>([])
const activeCrawl = ref<CrawlRunDetail | null>(null)
const crawlRuns = ref<CrawlRun[]>([])
const collectionBatches = ref<CollectionBatch[]>([])
const loading = ref(false)
const creating = ref(false)
const crawlLoading = ref(false)
const error = ref("")
const runError = ref("")
const crawlError = ref("")
const reviewRuns = ref<ReviewCollectionRun[]>([])
const reviewLoading = ref(false)
const reviewCollecting = ref(false)
const reviewError = ref("")
const askRuns = ref<ReviewCollectionRun[]>([])
const askLoading = ref(false)
const askCollecting = ref(false)
const askError = ref("")
const dailyCollecting = ref(false)
const browserStarting = ref(false)
const retryingBatchId = ref<string | null>(null)
const taskView = ref<"daily" | "feedback" | "contracts">("daily")
let crawlPollTimer: number | undefined
let reviewPollTimer: number | undefined
let askPollTimer: number | undefined

const selected = computed(() => plan.value?.selected ?? [])
const deferred = computed(() => plan.value?.deferred ?? [])
const activeRunItems = computed(() => activeRun.value?.items ?? [])
const crawlDays = computed(() => activeCrawl.value?.days ?? [])
const failedCrawlDays = computed(() => crawlDays.value.filter((day) => day.status.includes("failed")))
const crawlProgress = computed(() => activeCrawl.value?.planned_days ? Math.min(100, Math.round(((activeCrawl.value.success_days + activeCrawl.value.skipped_days) / activeCrawl.value.planned_days) * 100)) : 0)
const latestBatch = computed(() => collectionBatches.value[0] ?? null)
const dailyRunning = computed(() => latestBatch.value?.status === "running")
const batchProgress = computed(() => latestBatch.value?.progress_percent ?? 0)
const batchSuccessRate = computed(() => latestBatch.value?.success_rate ?? 0)
const visibleReviewRuns = computed(() => reviewRuns.value.slice(0, 5))
const visibleAskRuns = computed(() => askRuns.value.slice(0, 5))
const latestReviewRun = computed(() => reviewRuns.value[0] ?? null)
const latestAskRun = computed(() => askRuns.value[0] ?? null)
const reviewRunning = computed(() => reviewRuns.value.some((run) => run.status === "queued" || run.status === "running"))
const askRunning = computed(() => askRuns.value.some((run) => run.status === "queued" || run.status === "running"))
const recentFeedbackFailures = computed(() => [...reviewRuns.value, ...askRuns.value].filter((run) => run.status === "failed").length)
const currentViewLoading = computed(() => {
  if (taskView.value === "daily") return crawlLoading.value
  if (taskView.value === "feedback") return reviewLoading.value || askLoading.value
  return loading.value
})
const taskViewDescription = computed(() => {
  if (taskView.value === "daily") return "经营数据按日期和数据集入库，失败项可在批次中继续追查。"
  if (taskView.value === "feedback") return "评价与问答分开执行增量采集，只补充数据库中还没有的新内容。"
  return "用于检查接口准备情况和字段映射，不会直接写入正式经营数据。"
})

function contractLabel(item: ImportCandidate): string {
  const contract = item.request_contract
  const params = Object.entries(contract.query_params)
    .filter(([key]) => ["dateType", "dateRange", "startTime", "endTime", "page", "pageSize"].includes(key))
    .map(([key, value]) => `${key}=${String(value)}`)
  return params.join(" | ") || contract.url
}

async function loadPlan(): Promise<void> {
  loading.value = true
  error.value = ""
  try {
    plan.value = await fetchDailyDryRun()
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : "导入计划暂不可用"
  } finally {
    loading.value = false
  }
}

async function loadDryRunRuns(): Promise<void> {
  runError.value = ""
  try {
    const payload = await fetchImportRuns()
    runs.value = payload.runs
    if (!activeRun.value && payload.runs[0]) {
      activeRun.value = await fetchImportRun(payload.runs[0].run_id)
    }
  } catch (exc) {
    runError.value = exc instanceof Error ? exc.message : "本地预览记录暂不可用"
  }
}

async function loadCrawlRuns(): Promise<void> {
  crawlLoading.value = true
  crawlError.value = ""
  try {
    const [payload, batches] = await Promise.all([fetchCrawlRuns(), fetchCollectionBatches(10)])
    crawlRuns.value = payload.runs
    collectionBatches.value = batches
    if (payload.runs[0]) {
      activeCrawl.value = await fetchCrawlRun(payload.runs[0].run_id)
    } else {
      activeCrawl.value = null
    }
  } catch (exc) {
    crawlError.value = exc instanceof Error ? exc.message : "采集任务记录暂不可用"
  } finally {
    crawlLoading.value = false
    syncCrawlPolling()
  }
}

async function loadReviewRuns(): Promise<void> {
  reviewLoading.value = true
  reviewError.value = ""
  try {
    reviewRuns.value = await fetchReviewRuns(10)
  } catch (exc) {
    reviewError.value = exc instanceof Error ? exc.message : "评价采集任务记录暂不可用"
  } finally {
    reviewLoading.value = false
    syncReviewPolling()
  }
}

function stopReviewPolling(): void {
  if (reviewPollTimer !== undefined) {
    window.clearInterval(reviewPollTimer)
    reviewPollTimer = undefined
  }
}

function syncReviewPolling(): void {
  stopReviewPolling()
  if (taskView.value !== "feedback" || document.visibilityState === "hidden" || !reviewRuns.value.some((run) => run.status === "queued" || run.status === "running")) return
  reviewPollTimer = window.setInterval(() => {
    if (document.visibilityState !== "hidden" && !reviewLoading.value) void loadReviewRuns()
  }, 4000)
}

async function collectNewReviews(): Promise<void> {
  if (dailyRunning.value) {
    reviewError.value = "日常经营采集正在占用浏览器，请等待当前批次结束后再采集评价。"
    return
  }
  reviewCollecting.value = true
  reviewError.value = ""
  try {
    await collectReviews("incremental")
    await loadReviewRuns()
  } catch (exc) {
    reviewError.value = exc instanceof Error ? exc.message : "评价采集任务创建失败"
  } finally {
    reviewCollecting.value = false
  }
}

async function loadAskRuns(): Promise<void> {
  askLoading.value = true
  askError.value = ""
  try {
    askRuns.value = await fetchAskRuns(10)
  } catch (exc) {
    askError.value = exc instanceof Error ? exc.message : "问大家采集任务记录暂不可用"
  } finally {
    askLoading.value = false
    syncAskPolling()
  }
}

function stopAskPolling(): void {
  if (askPollTimer !== undefined) {
    window.clearInterval(askPollTimer)
    askPollTimer = undefined
  }
}

function syncAskPolling(): void {
  stopAskPolling()
  if (taskView.value !== "feedback" || document.visibilityState === "hidden" || !askRuns.value.some((run) => run.status === "queued" || run.status === "running")) return
  askPollTimer = window.setInterval(() => {
    if (document.visibilityState !== "hidden" && !askLoading.value) void loadAskRuns()
  }, 4000)
}

async function collectNewAsks(): Promise<void> {
  if (dailyRunning.value) {
    askError.value = "日常经营采集正在占用浏览器，请等待当前批次结束后再采集问答。"
    return
  }
  askCollecting.value = true
  askError.value = ""
  try {
    await collectAsks("incremental")
    await loadAskRuns()
  } catch (exc) {
    askError.value = exc instanceof Error ? exc.message : "问大家采集任务创建失败"
  } finally {
    askCollecting.value = false
  }
}

async function collectDailyData(): Promise<void> {
  dailyCollecting.value = true
  crawlError.value = ""
  try {
    taskView.value = "daily"
    await startDailyCollection({ sessionSource: "drissionpage" })
    await loadCrawlRuns()
  } catch (exc) {
    crawlError.value = exc instanceof Error ? exc.message : "日常经营数据采集任务启动失败"
  } finally {
    dailyCollecting.value = false
  }
}

async function startBrowser(): Promise<void> {
  browserStarting.value = true
  crawlError.value = ""
  try {
    await startCollectionBrowser()
  } catch (exc) {
    crawlError.value = exc instanceof Error ? exc.message : "采集浏览器启动失败"
  } finally {
    browserStarting.value = false
  }
}

async function retryFailedBatch(batch: CollectionBatch): Promise<void> {
  const datasetNames = batch.failure_details.map((item) => item.dataset_key)
  if (!datasetNames.length) return
  retryingBatchId.value = batch.batch_id
  crawlError.value = ""
  try {
    taskView.value = "daily"
    await startDailyCollection({
      day: batch.business_day,
      datasetNames,
      sessionSource: "drissionpage",
      refreshExisting: true,
    })
    await Promise.all([loadCrawlRuns(), loadReviewRuns(), loadAskRuns()])
  } catch (exc) {
    crawlError.value = exc instanceof Error ? exc.message : "失败项重试任务启动失败"
  } finally {
    retryingBatchId.value = null
  }
}

function stopCrawlPolling(): void {
  if (crawlPollTimer !== undefined) {
    window.clearInterval(crawlPollTimer)
    crawlPollTimer = undefined
  }
}

function syncCrawlPolling(): void {
  stopCrawlPolling()
  if (taskView.value !== "daily" || document.visibilityState === "hidden" || (activeCrawl.value?.status !== "running" && latestBatch.value?.status !== "running")) return
  crawlPollTimer = window.setInterval(() => {
    if (document.visibilityState !== "hidden" && !crawlLoading.value) void loadCrawlRuns()
  }, 2500)
}

function handleVisibilityChange(): void {
  if (document.visibilityState === "hidden") {
    stopCrawlPolling()
    stopReviewPolling()
    stopAskPolling()
    return
  }
  syncCrawlPolling()
  syncReviewPolling()
  syncAskPolling()
}

watch(taskView, () => {
  syncCrawlPolling()
  syncReviewPolling()
  syncAskPolling()
})

async function refreshPage(): Promise<void> {
  await Promise.all([loadPlan(), loadCrawlRuns(), loadDryRunRuns(), loadReviewRuns(), loadAskRuns()])
}

async function refreshCurrentView(): Promise<void> {
  if (taskView.value === "daily") {
    await loadCrawlRuns()
    return
  }
  if (taskView.value === "feedback") {
    await Promise.all([loadReviewRuns(), loadAskRuns()])
    return
  }
  await Promise.all([loadPlan(), loadDryRunRuns()])
}

async function createRun(): Promise<void> {
  creating.value = true
  runError.value = ""
  try {
    activeRun.value = await createDryRunImportRun(plan.value?.day)
    await loadDryRunRuns()
  } catch (exc) {
    runError.value = exc instanceof Error ? exc.message : "生成本地预览失败"
  } finally {
    creating.value = false
  }
}

async function selectRun(run: ImportRun): Promise<void> {
  runError.value = ""
  try {
    activeRun.value = await fetchImportRun(run.run_id)
  } catch (exc) {
    runError.value = exc instanceof Error ? exc.message : "读取预览详情失败"
  }
}

async function selectCrawlRun(run: CrawlRun): Promise<void> {
  crawlError.value = ""
  try {
    activeCrawl.value = await fetchCrawlRun(run.run_id)
    syncCrawlPolling()
  } catch (exc) {
    crawlError.value = exc instanceof Error ? exc.message : "读取采集任务详情失败"
  }
}

function runStatusLabel(status: string): string {
  if (status === "preview_ready") return "预览就绪"
  if (status === "needs_mapping") return "待补映射"
  return status
}

function crawlStatusLabel(status: string): string {
  if (status === "running") return "采集中"
  if (status === "completed") return "已完成"
  if (status === "completed_with_errors") return "部分失败"
  if (status === "stopped") return "已停止"
  return status
}

function batchStatusLabel(status: string): string {
  if (status === "running") return "采集中"
  if (status === "completed") return "已完成"
  if (status === "completed_with_errors") return "部分失败"
  if (status === "failed") return "失败"
  return status
}

function taskTypeLabel(type: string): string {
  return {
    sycm_overview: "店铺经营总览",
    sycm_bybt: "百亿补贴",
    sycm_bybt_items: "百亿补贴商品明细（按日）",
    sycm_customer_overview: "客户概览",
    sycm_item_rankings: "商品排行",
    sycm_live: "直播经营",
    sycm_member_analysis: "会员分析",
    sycm_new_customer_discount: "新客折扣",
    sycm_shopping_gold: "购物金",
    sycm_traffic_source: "流量来源",
    mtop_content_overview: "内容效果",
    mtop_taojinbi: "淘金币",
    customer_service: "客服数据",
    cps_overview: "淘宝客 CPS",
    brandsearch_report: "品销宝品牌专区",
    taobao_flash_sale: "淘宝秒杀",
  }[type] || type
}

function datasetLabel(key: string): string {
  return {
    sycm_overviews: "店铺经营总览",
    sycm_bybt: "百亿补贴",
    sycm_customer_overviews: "客户概览",
    sycm_item_rankings: "商品排行",
    sycm_live: "直播经营",
    sycm_member_analysis: "会员分析",
    sycm_new_customer_discount: "新客折扣",
    sycm_shopping_gold: "购物金",
    sycm_traffic_sources: "流量来源",
    mtop_content_overviews: "内容效果",
    mtop_taojinbi: "淘金币",
    customer_service: "客服数据",
    cps_overviews: "淘宝客 CPS",
    brandsearch_reports: "品销宝品牌专区",
    taobao_flash_sales: "淘宝秒杀",
    taobao_flash_sale_items: "淘宝秒杀商品明细（按日）",
    taobao_operational_snapshots: "淘宝运营商品快照",
    alimama_campaigns: "推广计划",
    alimama_crowds: "推广人群",
    alimama_promotion_details: "推广商品与内容",
    alimama_adgroup_bidwords: "推广单元与关键词",
  }[key] || key
}

function formatTime(value: string | null | undefined): string {
  if (!value) return "--"
  return new Date(value).toLocaleString("zh-CN", { hour12: false })
}

function collectionErrorLabel(value: string): string {
  const text = value.toLowerCase()
  if (text.includes("未配置，且已登录采集浏览器不可用") || text.includes("sycm_cookie is required")) {
    return "环境会话未配置，且采集浏览器不可用。请启动 9222 浏览器并登录天猫商家后台后重试。"
  }
  if (text.includes("no chrome remote-debugging") || text.includes("无法连接 chrome") || text.includes("调试端口")) {
    return "采集浏览器未连接，请启动 9222 采集浏览器后重试。"
  }
  if (text.includes("not logged in") || text.includes("未登录") || text.includes("login")) {
    return "采集浏览器尚未登录，请先登录天猫商家后台后重试。"
  }
  if (text.includes("登录状态") || text.includes("完成登录后重试")) {
    return "对应采集页面仍未完成登录，请在新打开的采集标签页登录后再重试。"
  }
  if (text.includes("品牌数据银行页面未提供")) {
    return "品牌数据银行页面未拿到有效登录令牌，请在新打开的品牌数据银行页完成登录后重试。"
  }
  if (text.includes("utry report templates") || text.includes("missing reportid") || text.includes("u先")) {
    return "U先页面请求参数未捕获，请确认派样和复购页面都能正常打开并完成登录后重试。"
  }
  if (text.includes("m_h5_tk")) {
    return "当前浏览器会话缺少淘宝签名 Cookie，请打开评价管理页后再重试。"
  }
  if (text.includes("drissionpage is not installed")) {
    return "采集组件未安装 DrissionPage，请补齐后端依赖后重试。"
  }
  return value
}

function collectionStatusLabel(status: string): string {
  if (status === "queued") return "排队中"
  if (status === "running") return "采集中"
  if (status === "completed") return "已完成"
  if (status === "failed") return "失败"
  return status
}

function collectionModeLabel(mode: string, target: "review" | "ask"): string {
  if (mode === "incremental") return target === "review" ? "增量采集新评价" : "增量采集新问答"
  return target === "review" ? "历史评价补录" : "历史问答补录"
}

function dayStatusLabel(status: string): string {
  if (status === "ingested") return "已入库"
  if (status === "skipped_existing") return "已跳过"
  if (status === "fetch_failed") return "请求失败"
  if (status === "ingest_failed") return "解析失败"
  return status
}

function dayStatusClass(day: CrawlRunDay): string {
  return day.status.includes("failed") ? "failed" : day.status === "ingested" ? "ready" : "muted"
}

function itemStatusLabel(item: ImportRunItem): string {
  if (item.status === "preview_ready") return "可预览"
  if (item.status === "needs_mapping") return "待映射"
  return item.status
}

onMounted(() => {
  document.addEventListener("visibilitychange", handleVisibilityChange)
  void refreshPage()
})

onUnmounted(() => {
  document.removeEventListener("visibilitychange", handleVisibilityChange)
  stopCrawlPolling()
  stopReviewPolling()
  stopAskPolling()
})
</script>

<template>
  <section class="module-hero import-hero">
    <div>
      <p>数据管理 · 采集记录</p>
      <h2>采集任务</h2>
      <span>统一查看经营数据批次，以及评价与问答的增量采集状态。</span>
    </div>
    <div class="hero-actions">
      <button class="capture-refresh secondary-action" :disabled="currentViewLoading" title="刷新当前标签的数据" @click="refreshCurrentView">
        <History :size="16" :class="{ spinning: currentViewLoading }" />
        刷新
      </button>
      <button class="capture-refresh secondary-action" :disabled="browserStarting || dailyRunning" title="启动可见的 9222 采集浏览器，首次使用请完成网页登录" @click="startBrowser">
        <Play :size="16" :class="{ spinning: browserStarting }" />
        {{ browserStarting ? "启动浏览器中" : "启动采集浏览器" }}
      </button>
      <button class="capture-refresh" :disabled="dailyCollecting || dailyRunning" title="启动昨天的经营数据采集，浏览器未启动时会自动启动" @click="collectDailyData">
        <Play :size="16" :class="{ spinning: dailyCollecting }" />
        {{ dailyCollecting ? "启动中" : latestBatch?.status === "running" ? "日常采集中" : "开始日常采集" }}
      </button>
      <button class="capture-refresh" :disabled="dailyRunning || reviewCollecting || reviewLoading || reviewRunning" title="只采集数据库中还没有的新评价" @click="taskView = 'feedback'; collectNewReviews()">
        <RefreshCw :size="16" :class="{ spinning: reviewCollecting }" />
        {{ reviewCollecting ? "创建中" : reviewRunning ? "评价采集中" : "采集新评价" }}
      </button>
      <button class="capture-refresh" :disabled="dailyRunning || askCollecting || askLoading || askRunning" title="只采集数据库中还没有的新问答" @click="taskView = 'feedback'; collectNewAsks()">
        <RefreshCw :size="16" :class="{ spinning: askCollecting }" />
        {{ askCollecting ? "创建中" : askRunning ? "问答采集中" : "采集新问答" }}
      </button>
    </div>
  </section>

  <nav class="task-view-tabs" aria-label="采集任务视图">
    <button :class="{ active: taskView === 'daily' }" @click="taskView = 'daily'"><DatabaseZap :size="15" />日常采集</button>
    <button :class="{ active: taskView === 'feedback' }" @click="taskView = 'feedback'"><RefreshCw :size="15" />评价与问答</button>
    <button :class="{ active: taskView === 'contracts' }" @click="taskView = 'contracts'"><FileLock2 :size="15" />接口检查</button>
  </nav>
  <div class="task-view-context"><strong>{{ taskView === "daily" ? "日常经营数据" : taskView === "feedback" ? "用户反馈增量" : "开发接入检查" }}</strong><span>{{ taskViewDescription }}</span></div>

  <template v-if="taskView === 'daily'">
    <section v-if="crawlLoading && !activeCrawl && !collectionBatches.length" class="loading-panel">
      <LoaderCircle :size="28" class="spinning" />
      <span>正在读取日常采集任务</span>
    </section>

    <section v-else-if="crawlError && !activeCrawl && !collectionBatches.length" class="error-panel">
      <CircleAlert :size="24" />
      <div><strong>日常采集任务暂不可用</strong><p>{{ crawlError }}</p></div>
      <button @click="loadCrawlRuns">重试</button>
    </section>

    <template v-else>
    <section class="architecture-metrics">
      <article class="panel capture-stat">
        <span>最近批次</span>
        <strong>{{ latestBatch?.status ? batchStatusLabel(latestBatch.status) : "尚未运行" }}</strong>
        <small>{{ latestBatch ? `${latestBatch.business_day} · ${latestBatch.dataset_names.length} 个数据集` : "等待第一次采集" }}</small>
      </article>
      <article class="panel capture-stat">
        <span>已成功数据集</span>
        <strong>{{ number(latestBatch?.completed_count ?? 0) }} / {{ number(latestBatch?.total_count ?? 0) }}</strong>
        <small>已确认入库或平台明确无数据</small>
      </article>
      <article class="panel capture-stat">
        <span>失败数据集</span>
        <strong>{{ number(latestBatch?.failed_count ?? 0) }}</strong>
        <small>需要查看批次记录</small>
      </article>
      <article class="panel capture-stat">
        <span>成功率</span>
        <strong>{{ latestBatch ? `${batchSuccessRate}%` : "--" }}</strong>
        <small>{{ latestBatch?.status === "running" ? `执行进度 ${latestBatch.settled_count} / ${latestBatch.total_count}` : `执行进度 ${batchProgress}%` }}</small>
      </article>
    </section>

    <section class="panel architecture-panel daily-batch-panel">
      <div class="panel-heading">
        <div><p>批次记录</p><h2>最近采集批次</h2></div>
        <span v-if="latestBatch?.status === 'running'" class="live-label"><span></span> 自动刷新中</span>
        <DatabaseZap :size="18" />
      </div>

      <div v-if="crawlError" class="inline-error">{{ crawlError }}</div>

      <div v-if="collectionBatches.length" class="collection-batch-list">
        <article v-for="batch in collectionBatches" :key="batch.batch_id" class="collection-batch-row" :class="batch.status">
          <div class="batch-date"><strong>{{ batch.business_day }}</strong><span>{{ batch.trigger === 'schedule' ? '自动' : '手动' }}</span></div>
          <div class="batch-scope"><strong>{{ batch.dataset_names.length }} 个数据集</strong><small>{{ batch.dataset_names.map(datasetLabel).join(' · ') }}</small></div>
          <div class="batch-result"><em :class="batch.status">{{ batchStatusLabel(batch.status) }}</em><small>成功 {{ batch.completed_count }} · 失败 {{ batch.failed_count }} · 执行 {{ batch.settled_count }}/{{ batch.total_count }}</small></div>
          <div class="batch-time"><strong>{{ formatTime(batch.started_at) }}</strong><small>{{ batch.finished_at ? `结束 ${formatTime(batch.finished_at)}` : batch.current_dataset_label ? `当前：${batch.current_dataset_label}` : '后台执行中' }}</small></div>
          <details v-if="batch.failure_details.length" class="batch-failures">
            <summary>查看 {{ batch.failure_details.length }} 个失败项</summary>
            <div v-for="item in batch.failure_details" :key="item.dataset_key" class="batch-failure-row">
              <strong>{{ item.dataset_label }}</strong>
              <small>{{ collectionErrorLabel(item.error_message || "目标日期未完成入库") }}</small>
            </div>
            <button type="button" class="retry-failed" :disabled="dailyRunning || retryingBatchId === batch.batch_id" @click="retryFailedBatch(batch)">
              <RefreshCw :size="14" :class="{ spinning: retryingBatchId === batch.batch_id }" />
              {{ retryingBatchId === batch.batch_id ? "正在创建重试" : "重试失败项" }}
            </button>
          </details>
        </article>
      </div>
      <p v-else class="architecture-note">暂无采集批次。</p>

      <details v-if="activeCrawl" class="crawl-run-details">
        <summary>查看最近子任务：{{ taskTypeLabel(activeCrawl.task_type) }} · {{ crawlStatusLabel(activeCrawl.status) }}</summary>
        <div class="crawl-summary">
          <div><span>任务编号</span><strong>{{ activeCrawl.run_id }}</strong><small>{{ activeCrawl.mode }} · {{ crawlStatusLabel(activeCrawl.status) }}</small></div>
          <div><span>完成情况</span><strong>{{ activeCrawl.success_days }} / {{ activeCrawl.planned_days }}</strong><small>成功日期 / 计划日期</small></div>
          <div><span>店铺</span><strong>店铺 ID {{ activeCrawl.store_id }}</strong><small>{{ activeCrawl.finished_at ? formatTime(activeCrawl.finished_at) : "任务仍在运行" }}</small></div>
        </div>
        <div class="task-progress-meter"><div><span>任务完成度</span><strong>{{ crawlProgress }}%</strong></div><i><em :style="{ width: `${crawlProgress}%` }"></em></i></div>
        <div v-if="crawlDays.length" class="crawl-day-list"><div v-for="day in crawlDays" :key="day.item_id" class="crawl-day-row"><span>{{ day.business_day }}</span><strong :class="dayStatusClass(day)">{{ dayStatusLabel(day.status) }}</strong><small>{{ day.metric_count ? `${day.metric_count} 项指标` : "" }}</small><em v-if="day.error_message">{{ day.error_message }}</em></div></div>
        <div v-if="failedCrawlDays.length" class="crawl-warning"><CircleAlert :size="16" /><span>本次有 {{ failedCrawlDays.length }} 个日期未完成。</span></div>
      </details>

      <details v-if="crawlRuns.length" class="crawl-run-details">
        <summary>查看子任务记录（{{ crawlRuns.length }}）</summary>
        <div class="run-history-list">
          <button v-for="run in crawlRuns" :key="run.run_id" type="button" @click="selectCrawlRun(run)"><span>{{ taskTypeLabel(run.task_type) }}</span><strong>{{ crawlStatusLabel(run.status) }}</strong><small>{{ run.start_day }} · 成功 {{ run.success_days }} · 跳过 {{ run.skipped_days }} · 失败 {{ run.failed_days }}</small></button>
        </div>
      </details>
    </section>
    </template>
    </template>

    <template v-else-if="taskView === 'feedback'">
    <section class="feedback-summary" aria-label="评价与问答任务摘要">
      <article class="panel feedback-stat"><span>最近评价任务</span><strong>{{ latestReviewRun ? collectionStatusLabel(latestReviewRun.status) : "暂无任务" }}</strong><small>{{ latestReviewRun ? `${formatTime(latestReviewRun.started_at)} · 新增 ${number(latestReviewRun.inserted_count)}` : "点击上方按钮采集新评价" }}</small></article>
      <article class="panel feedback-stat"><span>最近问答任务</span><strong>{{ latestAskRun ? collectionStatusLabel(latestAskRun.status) : "暂无任务" }}</strong><small>{{ latestAskRun ? `${formatTime(latestAskRun.started_at)} · 新增 ${number(latestAskRun.inserted_count)}` : "点击上方按钮采集新问答" }}</small></article>
      <article class="panel feedback-stat"><span>最近失败任务</span><strong>{{ number(recentFeedbackFailures) }}</strong><small>最近加载的评价与问答记录</small></article>
      <article class="panel feedback-stat"><span>采集规则</span><strong>仅采集新增</strong><small>已存在记录不会重复写入</small></article>
    </section>
    <section class="feedback-task-grid">
    <section class="panel architecture-panel review-task-panel">
      <div class="panel-heading">
        <div><p>评价采集</p><h2>评价任务</h2></div>
        <button class="panel-icon-action" type="button" title="刷新评价任务" :disabled="reviewLoading" @click="loadReviewRuns"><RefreshCw :size="17" :class="{ spinning: reviewLoading }" /></button>
      </div>
      <div v-if="reviewError" class="inline-error">{{ reviewError }}</div>
      <div v-if="reviewRuns.length" class="review-task-list">
        <div v-for="run in visibleReviewRuns" :key="run.run_id" class="review-task-row">
          <div><strong>{{ collectionModeLabel(run.mode, "review") }}</strong><span>{{ formatTime(run.started_at) }}</span></div>
          <em :class="run.status === 'completed' ? 'ready' : run.status === 'failed' ? 'failed' : 'running'">{{ collectionStatusLabel(run.status) }}</em>
          <small v-if="run.status === 'completed'">新增 {{ run.inserted_count }} · 更新 {{ run.updated_count }} · 抓取 {{ run.fetched_count }}</small>
          <small v-else-if="run.error">{{ collectionErrorLabel(run.error) }}</small>
          <small v-else>后台执行中</small>
        </div>
      </div>
      <p v-else class="architecture-note">暂无评价采集任务。</p>
    </section>
    <section class="panel architecture-panel review-task-panel">
      <div class="panel-heading">
        <div><p>问大家采集</p><h2>买家问答任务</h2></div>
        <button class="panel-icon-action" type="button" title="刷新问答任务" :disabled="askLoading" @click="loadAskRuns"><RefreshCw :size="17" :class="{ spinning: askLoading }" /></button>
      </div>
      <div v-if="askError" class="inline-error">{{ askError }}</div>
      <div v-if="askRuns.length" class="review-task-list">
        <div v-for="run in visibleAskRuns" :key="run.run_id" class="review-task-row">
          <div><strong>{{ collectionModeLabel(run.mode, "ask") }}</strong><span>{{ formatTime(run.started_at) }}</span></div>
          <em :class="run.status === 'completed' ? 'ready' : run.status === 'failed' ? 'failed' : 'running'">{{ collectionStatusLabel(run.status) }}</em>
          <small v-if="run.status === 'completed'">新增 {{ run.inserted_count }} · 更新 {{ run.updated_count }} · 抓取 {{ run.fetched_count }}</small>
          <small v-else-if="run.error">{{ collectionErrorLabel(run.error) }}</small>
          <small v-else>后台执行中</small>
        </div>
      </div>
      <p v-else class="architecture-note">暂无买家问答采集任务。</p>
    </section>
    </section>
    </template>

    <template v-else>
    <section v-if="error && !plan" class="error-panel">
      <CircleAlert :size="24" />
      <div><strong>接口准备信息暂不可用</strong><p>{{ error }}</p></div>
      <button @click="loadPlan">重试</button>
    </section>

    <section v-else-if="plan" class="panel architecture-panel">
      <div class="panel-heading">
        <div><p>准备检查</p><h2>下一批导入接口</h2></div>
        <CheckCircle2 :size="18" />
      </div>
      <div class="dry-run-toolbar">
        <span>{{ plan.day }} · {{ selected.length }} 个可用接口 · {{ deferred.length }} 个待补接口</span>
        <button class="secondary-action small-action" :disabled="creating" @click="createRun">
          <DatabaseZap :size="14" :class="{ spinning: creating }" />
          生成本地预览
        </button>
      </div>
      <div class="import-candidate-list">
        <article v-for="item in selected" :key="item.function">
          <div class="task-icon ready"><CheckCircle2 :size="18" /></div>
          <div>
            <div class="task-title">
              <h3>{{ item.function }}</h3>
              <span class="ready">{{ item.priority }} · {{ item.request_contract.method }}</span>
            </div>
            <p>{{ item.legacy_path }}</p>
            <small>{{ contractLabel(item) }}</small>
          </div>
        </article>
      </div>
      <div v-if="runError" class="inline-error">{{ runError }}</div>
    </section>

    <section v-else-if="loading" class="loading-panel">
      <LoaderCircle :size="24" class="spinning" /><span>正在读取接口准备信息</span>
    </section>

    <section v-if="activeRun" class="panel architecture-panel">
      <div class="panel-heading">
        <div><p>本地预览</p><h2>最近一次接口检查</h2></div>
        <FileLock2 :size="18" />
      </div>
      <div class="run-summary">
        <div><span>预览编号</span><strong>{{ activeRun.run_id }}</strong><small>{{ activeRun.day }} · {{ runStatusLabel(activeRun.status) }}</small></div>
        <div><span>候选 / 延后</span><strong>{{ activeRun.selected_count }} / {{ activeRun.deferred_count }}</strong><small>{{ activeRun.mode }}</small></div>
        <div><span>生成时间</span><strong>{{ formatTime(activeRun.created_at) }}</strong><small>{{ activeRun.source }}</small></div>
      </div>
      <div v-if="activeRunItems.length" class="run-item-list">
        <div v-for="item in activeRunItems" :key="item.item_id" class="run-item-row">
          <span>#{{ item.item_order }}</span>
          <strong>{{ item.function_name }}</strong>
          <small>{{ item.method }} · {{ item.target_table }} · {{ itemStatusLabel(item) }}</small>
          <em>{{ item.risk_notes.join(" / ") }}</em>
        </div>
      </div>
      <div v-if="runs.length" class="run-history-list">
        <button v-for="run in runs" :key="run.run_id" type="button" @click="selectRun(run)">
          <span>{{ run.day }}</span>
          <strong>{{ runStatusLabel(run.status) }}</strong>
          <small>{{ run.run_id }}</small>
        </button>
      </div>
    </section>

    <section v-if="plan?.deferred.length" class="panel architecture-panel">
      <div class="panel-heading">
        <div><p>待补接口</p><h2>暂缓接入的请求</h2></div>
        <FileLock2 :size="18" />
      </div>
      <div class="deferred-grid">
        <div v-for="item in deferred" :key="item.function">
          <strong>{{ item.function }}</strong>
          <span>{{ item.priority }} · {{ item.legacy_path }}</span>
        </div>
      </div>
    </section>
    </template>
</template>

<style scoped>
.task-view-tabs { display: flex; gap: 4px; margin: 0; border-bottom: 1px solid #dfe9e3; }
.task-view-tabs button { display: inline-flex; min-height: 36px; align-items: center; gap: 7px; border: 0; border-bottom: 2px solid transparent; padding: 0 12px; color: #7b8b82; background: transparent; font: inherit; font-size: 12px; cursor: pointer; }
.task-view-tabs button.active { border-bottom-color: #16845b; color: #166f4e; font-weight: 700; }
.task-view-context { display: flex; align-items: center; gap: 10px; margin: 0 0 14px; border-bottom: 1px solid #e7eee9; padding: 10px 12px; color: #7d8d84; background: #f8fbf9; font-size: 11px; }
.task-view-context strong { flex: 0 0 auto; color: #315b47; font-size: 11px; }
.feedback-summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-bottom: 14px; }
.feedback-stat { display: grid; min-height: 88px; align-content: center; gap: 5px; padding: 14px 16px; }
.feedback-stat span, .feedback-stat small { color: #89968f; font-size: 10px; }
.feedback-stat strong { color: #284b3a; font-size: 18px; }
.feedback-task-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.feedback-task-grid .review-task-panel { margin-top: 0; }
.panel-icon-action { display: inline-grid; width: 30px; height: 30px; place-items: center; border: 1px solid #d8e5dc; border-radius: 4px; color: #16845b; background: #fff; cursor: pointer; }
.panel-icon-action:disabled { cursor: not-allowed; opacity: .5; }
.review-task-panel { margin-top: 14px; }
.daily-batch-panel { overflow: hidden; }
.collection-batch-list { display: grid; }
.collection-batch-row { display: grid; grid-template-columns: 120px minmax(240px, 1fr) 120px 210px; min-height: 72px; align-items: center; gap: 16px; border-bottom: 1px solid #e9efeb; padding: 10px 16px; }
.collection-batch-row:last-child { border-bottom: 0; }
.collection-batch-row > div { display: grid; min-width: 0; gap: 4px; }
.collection-batch-row strong { color: #354d40; font-size: 12px; }
.collection-batch-row span, .collection-batch-row small { overflow: hidden; color: #89968f; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.batch-date span { width: fit-content; border-radius: 8px; padding: 2px 6px; color: #557765; background: #eef5f1; }
.batch-result em { width: fit-content; border-radius: 10px; padding: 3px 7px; font-size: 10px; font-style: normal; }
.batch-result em.completed { color: #167752; background: #eaf7ef; }
.batch-result em.running { color: #84631d; background: #fff6df; }
.batch-result em.completed_with_errors, .batch-result em.failed { color: #a84c43; background: #fff0ed; }
.batch-failures { grid-column: 2 / -1; border-top: 1px solid #f0e2df; padding-top: 8px; }
.batch-failures summary { color: #a84c43; font-size: 11px; cursor: pointer; }
.batch-failure-row { display: grid; grid-template-columns: 150px minmax(0, 1fr); gap: 10px; align-items: start; padding: 7px 0; }
.batch-failure-row strong { color: #624843; font-size: 11px; }
.batch-failure-row small { overflow: visible; color: #9d6b64; font-size: 10px; white-space: normal; }
.retry-failed { display: inline-flex; align-items: center; gap: 5px; margin: 2px 0 4px; border: 1px solid #e5b9b0; border-radius: 4px; padding: 6px 9px; color: #a44d43; background: #fff8f6; font: inherit; font-size: 10px; cursor: pointer; }
.retry-failed:disabled { cursor: not-allowed; opacity: .55; }
.crawl-run-details { border-top: 1px solid #e9efeb; padding: 0 16px; }
.crawl-run-details summary { padding: 13px 0; color: #527161; font-size: 11px; font-weight: 650; cursor: pointer; }
.crawl-run-details .crawl-summary, .crawl-run-details .task-progress-meter, .crawl-run-details .crawl-day-list, .crawl-run-details .crawl-warning, .crawl-run-details .run-history-list { margin-bottom: 14px; }
.review-task-list { display: grid; gap: 0; }
.review-task-row { display: grid; grid-template-columns: minmax(220px, 1.2fr) 90px minmax(180px, 1fr); align-items: center; gap: 14px; border-bottom: 1px solid #edf2ee; padding: 13px 16px; }
.review-task-row:last-child { border-bottom: 0; }
.review-task-row > div { display: grid; gap: 4px; }
.review-task-row strong { color: #405449; font-size: 12px; }
.review-task-row span, .review-task-row small { color: #8a9a91; font-size: 10px; }
.review-task-row em { width: fit-content; border-radius: 999px; padding: 4px 8px; font-size: 10px; font-style: normal; }
.review-task-row em.ready { color: #176b4b; background: #eff8f2; }
.review-task-row em.running { color: #9a713b; background: #fff7e8; }
.review-task-row em.failed { color: #a44d4d; background: #fff0f0; }
@media (max-width: 1050px) { .collection-batch-row { grid-template-columns: 110px minmax(200px, 1fr) 110px; } .batch-time { grid-column: 2 / 4; } .batch-failures { grid-column: 1 / -1; } }
@media (max-width: 1050px) { .feedback-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 900px) { .feedback-task-grid { grid-template-columns: 1fr; } }
@media (max-width: 760px) { .task-view-tabs { overflow-x: auto; } .task-view-tabs button { flex: 0 0 auto; } .task-view-context { align-items: flex-start; flex-direction: column; gap: 3px; } .feedback-summary { grid-template-columns: 1fr 1fr; } .collection-batch-row { grid-template-columns: 1fr 1fr; gap: 10px; } .batch-time { grid-column: 1 / -1; } .review-task-row { grid-template-columns: 1fr; gap: 7px; } }
@media (max-width: 480px) { .feedback-summary { grid-template-columns: 1fr; } }
</style>
