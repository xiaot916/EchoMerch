<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import {
  CircleAlert,
  CircleCheck,
  DatabaseZap,
  Inbox,
  LoaderCircle,
  MessagesSquare,
  MessageSquarePlus,
  Play,
  RefreshCw,
  Settings2,
} from "lucide-vue-next"
import { RouterLink } from "vue-router"

import {
  collectAsks,
  collectReviews,
  fetchAskRuns,
  fetchCollectionBatches,
  fetchCrawlRun,
  fetchCrawlRuns,
  fetchReviewRuns,
  startDailyCollection,
  startCollectionBrowser,
} from "@/api"
import { usePolling } from "@/composables/usePolling"
import {
  batchStatusLabel,
  collectionErrorLabel,
  collectionModeLabel,
  collectionStatusLabel,
  collectionTimeLabel,
  crawlStatusLabel,
  datasetLabel,
  dayStatusLabel,
  dayStatusClass,
  taskTypeLabel,
} from "@/lib/collectionLabels"
import { number } from "@/lib/format"
import type {
  CrawlRun,
  CrawlRunDetail,
  CrawlRunDay,
  CollectionBatch,
  ReviewCollectionRun,
} from "@/types"

// ---------------------------------------------------------------------------
// 数据
// ---------------------------------------------------------------------------
const taskView = ref<"daily" | "feedback">("daily")

// 日常采集
const activeCrawl = ref<CrawlRunDetail | null>(null)
const crawlRuns = ref<CrawlRun[]>([])
const collectionBatches = ref<CollectionBatch[]>([])
const crawlLoading = ref(false)
const crawlError = ref("")
const dailyCollecting = ref(false)
const browserStarting = ref(false)
const retryingBatchId = ref<string | null>(null)

// 评价 / 问答
const reviewRuns = ref<ReviewCollectionRun[]>([])
const askRuns = ref<ReviewCollectionRun[]>([])
const reviewLoading = ref(false)
const askLoading = ref(false)
const reviewCollecting = ref(false)
const askCollecting = ref(false)
const reviewError = ref("")
const askError = ref("")

// ---------------------------------------------------------------------------
// 派生状态
// ---------------------------------------------------------------------------
const latestBatch = computed(() => collectionBatches.value[0] ?? null)
const dailyRunning = computed(() => latestBatch.value?.status === "running")
const batchProgress = computed(() => latestBatch.value?.progress_percent ?? 0)
const batchSuccessRate = computed(() => latestBatch.value?.success_rate ?? 0)

const crawlDays = computed<CrawlRunDay[]>(() => activeCrawl.value?.days ?? [])
const failedCrawlDays = computed(() => crawlDays.value.filter((day) => day.status.includes("failed")))
const crawlProgress = computed(() =>
  activeCrawl.value?.planned_days
    ? Math.min(100, Math.round(((activeCrawl.value.success_days + activeCrawl.value.skipped_days) / activeCrawl.value.planned_days) * 100))
    : 0,
)

const reviewRunning = computed(() => reviewRuns.value.some((run) => run.status === "queued" || run.status === "running"))
const askRunning = computed(() => askRuns.value.some((run) => run.status === "queued" || run.status === "running"))
const visibleReviewRuns = computed(() => reviewRuns.value.slice(0, 5))
const visibleAskRuns = computed(() => askRuns.value.slice(0, 5))
const latestReviewRun = computed(() => reviewRuns.value[0] ?? null)
const latestAskRun = computed(() => askRuns.value[0] ?? null)
const recentFeedbackFailures = computed(
  () => [...reviewRuns.value, ...askRuns.value].filter((run) => run.status === "failed").length,
)

const feedbackBusy = computed(() => dailyRunning.value || reviewRunning.value || askRunning.value)
const anyRunning = computed(() => dailyRunning.value || reviewRunning.value || askRunning.value)

const currentViewLoading = computed(() => {
  if (taskView.value === "daily") return crawlLoading.value
  return reviewLoading.value || askLoading.value
})

// ---------------------------------------------------------------------------
// 数据加载
// ---------------------------------------------------------------------------
async function loadCrawlRuns(): Promise<void> {
  crawlLoading.value = true
  crawlError.value = ""
  try {
    const [payload, batches] = await Promise.all([fetchCrawlRuns(), fetchCollectionBatches(10)])
    crawlRuns.value = payload.runs
    collectionBatches.value = batches
    activeCrawl.value = payload.runs[0] ? await fetchCrawlRun(payload.runs[0].run_id) : null
  } catch (exc) {
    crawlError.value = exc instanceof Error ? exc.message : "采集任务记录暂不可用"
  } finally {
    crawlLoading.value = false
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
  }
}

// ---------------------------------------------------------------------------
// 后台轮询（用可复用组合式函数替代三套手写的 setInterval）
// ---------------------------------------------------------------------------
const dailyPoll = usePolling({
  intervalMs: 2500,
  tick: () => loadCrawlRuns(),
})
const reviewPoll = usePolling({
  intervalMs: 4000,
  tick: () => loadReviewRuns(),
})
const askPoll = usePolling({
  intervalMs: 4000,
  tick: () => loadAskRuns(),
})

function syncPolling(): void {
  dailyPoll.setRunning(activeCrawl.value?.status === "running" || dailyRunning.value)
  reviewPoll.setRunning(reviewRunning.value)
  askPoll.setRunning(askRunning.value)
}

// ---------------------------------------------------------------------------
// 操作
// ---------------------------------------------------------------------------
async function collectDailyData(): Promise<void> {
  dailyCollecting.value = true
  crawlError.value = ""
  try {
    taskView.value = "daily"
    await startDailyCollection({ sessionSource: "drissionpage" })
    await loadCrawlRuns()
    syncPolling()
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
    syncPolling()
  } catch (exc) {
    reviewError.value = exc instanceof Error ? exc.message : "评价采集任务创建失败"
  } finally {
    reviewCollecting.value = false
  }
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
    syncPolling()
  } catch (exc) {
    askError.value = exc instanceof Error ? exc.message : "问大家采集任务创建失败"
  } finally {
    askCollecting.value = false
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
    syncPolling()
  } catch (exc) {
    crawlError.value = exc instanceof Error ? exc.message : "失败项重试任务启动失败"
  } finally {
    retryingBatchId.value = null
  }
}

async function selectCrawlRun(run: CrawlRun): Promise<void> {
  crawlError.value = ""
  try {
    activeCrawl.value = await fetchCrawlRun(run.run_id)
    syncPolling()
  } catch (exc) {
    crawlError.value = exc instanceof Error ? exc.message : "读取采集任务详情失败"
  }
}

async function refreshCurrentView(): Promise<void> {
  if (taskView.value === "daily") {
    await loadCrawlRuns()
    syncPolling()
    return
  }
  await Promise.all([loadReviewRuns(), loadAskRuns()])
  syncPolling()
}

// ---------------------------------------------------------------------------
// 行 / 状态视觉
// ---------------------------------------------------------------------------
function runStatusTone(status: string): string {
  if (status === "completed") return "ready"
  if (status === "failed") return "failed"
  return "running"
}

function batchTone(batch: CollectionBatch): string {
  if (batch.status === "running") return "running"
  if (batch.status === "completed") return "ready"
  if (batch.status === "failed") return "failed"
  return "warn"
}

function batchDuration(batch: CollectionBatch): string {
  if (!batch.started_at) return ""
  const start = new Date(batch.started_at).getTime()
  const end = batch.finished_at ? new Date(batch.finished_at).getTime() : Date.now()
  const seconds = Math.max(0, Math.round((end - start) / 1000))
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return rest ? `${minutes}m ${rest}s` : `${minutes}m`
}

// 把一批失败数据集按"可重试的错误类型"归一，给失败行一个更直观的说明。
function failureHeadline(batch: CollectionBatch): string {
  if (!batch.failure_details.length) return ""
  const first = collectionErrorLabel(batch.failure_details[0].error_message || "目标日期未完成入库")
  const distinct = new Set(batch.failure_details.map((item) => collectionErrorLabel(item.error_message || "")))
  if (distinct.size > 1) return `${batch.failure_details.length} 项失败，原因不同：${first}`
  return `${batch.failure_details.length} 项失败：${first}`
}

// ---------------------------------------------------------------------------
// 生命周期
// ---------------------------------------------------------------------------
onMounted(() => {
  void loadCrawlRuns()
  void loadReviewRuns()
  void loadAskRuns()
  syncPolling()
})
</script>

<template>
  <!-- 顶部命令条：标题 + 当前运行状态 + 全局操作 -->
  <section class="module-hero import-hero imports-hero">
    <div class="imports-hero-copy">
      <p>数据管理 · 采集任务</p>
      <h2>采集任务</h2>
      <span>统一查看经营数据批次，以及评价与问答的增量采集状态。</span>
    </div>
    <div class="imports-hero-side">
      <div class="imports-live-chip" :class="{ active: anyRunning, idle: !anyRunning }">
        <span class="imports-live-dot" />
        {{ anyRunning ? "有任务正在后台执行" : "后台空闲" }}
      </div>
      <div class="hero-actions">
        <button class="capture-refresh secondary-action" :disabled="currentViewLoading" title="刷新当前标签的数据" @click="refreshCurrentView">
          <RefreshCw :size="16" :class="{ spinning: currentViewLoading }" />刷新
        </button>
        <button class="capture-refresh secondary-action" :disabled="browserStarting || dailyRunning" title="启动可见的 9222 采集浏览器，首次使用请完成网页登录" @click="startBrowser">
          <Play :size="16" :class="{ spinning: browserStarting }" />{{ browserStarting ? "启动浏览器中" : "启动采集浏览器" }}
        </button>
        <button class="capture-refresh" :disabled="dailyCollecting || dailyRunning" title="启动昨天的经营数据采集，浏览器未启动时会自动启动" @click="collectDailyData">
          <Play :size="16" :class="{ spinning: dailyCollecting }" />{{ dailyCollecting ? "启动中" : dailyRunning ? "日常采集中" : "开始日常采集" }}
        </button>
      </div>
    </div>
  </section>

  <!-- 视图切换 -->
  <nav class="task-view-tabs" aria-label="采集任务视图">
    <button :class="{ active: taskView === 'daily' }" @click="taskView = 'daily'"><DatabaseZap :size="15" />日常采集<em v-if="latestBatch && !dailyRunning">{{ number(latestBatch.completed_count) }} 成功 · {{ batchSuccessRate }}%</em></button>
    <button :class="{ active: taskView === 'feedback' }" @click="taskView = 'feedback'"><MessagesSquare :size="15" />评价与问答<em v-if="recentFeedbackFailures">{{ recentFeedbackFailures }} 失败</em></button>
    <RouterLink to="/imports/overview" class="task-view-link"><Settings2 :size="14" />数据完整性<Inbox :size="12" class="task-view-link-arrow" /></RouterLink>
  </nav>

  <!-- ============ 日常采集 ============ -->
  <template v-if="taskView === 'daily'">
    <div class="task-view-context"><strong>日常经营数据</strong><span>经营数据按日期和数据集入库，失败项可在批次中继续追查。</span></div>

    <section v-if="crawlLoading && !activeCrawl && !collectionBatches.length" class="loading-panel">
      <LoaderCircle :size="28" class="spinning" /><span>正在读取日常采集任务</span>
    </section>

    <section v-else-if="crawlError && !activeCrawl && !collectionBatches.length" class="error-panel">
      <CircleAlert :size="24" /><div><strong>日常采集任务暂不可用</strong><p>{{ crawlError }}</p></div><button @click="loadCrawlRuns">重试</button>
    </section>

    <template v-else>
      <!-- 批次概览 KPI -->
      <section class="architecture-metrics">
        <article class="panel capture-stat">
          <span>最近批次</span>
          <strong>{{ latestBatch ? batchStatusLabel(latestBatch.status) : "尚未运行" }}</strong>
          <small>{{ latestBatch ? `${latestBatch.business_day} · ${latestBatch.dataset_names.length} 个数据集` : "等待第一次采集" }}</small>
        </article>
        <article class="panel capture-stat">
          <span>已成功数据集</span>
          <strong>{{ number(latestBatch?.completed_count ?? 0) }} / {{ number(latestBatch?.total_count ?? 0) }}</strong>
          <small>已确认入库或平台明确无数据</small>
        </article>
        <article class="panel capture-stat">
          <span>失败数据集</span>
          <strong :class="{ 'capture-stat-danger': (latestBatch?.failed_count ?? 0) > 0 }">{{ number(latestBatch?.failed_count ?? 0) }}</strong>
          <small>{{ (latestBatch?.failed_count ?? 0) > 0 ? "需要查看批次记录并处理" : "最近批次无失败" }}</small>
        </article>
        <article class="panel capture-stat">
          <span>成功率</span>
          <strong>{{ latestBatch ? `${batchSuccessRate}%` : "--" }}</strong>
          <small>{{ latestBatch?.status === "running" ? `执行进度 ${latestBatch.settled_count} / ${latestBatch.total_count}` : `执行进度 ${batchProgress}%` }}</small>
        </article>
      </section>

      <!-- 批次记录表 -->
      <section class="panel architecture-panel daily-batch-panel">
        <div class="panel-heading">
          <div><p>批次记录</p><h2>最近采集批次</h2></div>
          <span v-if="latestBatch?.status === 'running'" class="live-label"><span></span> 自动刷新中</span>
          <DatabaseZap :size="18" />
        </div>

        <div v-if="crawlError" class="inline-error">{{ crawlError }}</div>

        <div v-if="collectionBatches.length" class="collection-batch-list">
          <div class="collection-batch-head"><span>业务日期</span><span>数据集范围</span><span>结果</span><span>时间 / 耗时</span><span>失败明细</span></div>
          <article v-for="batch in collectionBatches" :key="batch.batch_id" class="collection-batch-row" :class="batchTone(batch)">
            <div class="batch-date">
              <strong>{{ batch.business_day }}</strong>
              <span>{{ batch.trigger === "schedule" ? "自动" : "手动" }}</span>
            </div>
            <div class="batch-scope">
              <strong>{{ batch.dataset_names.length }} 个数据集</strong>
              <small :title="batch.dataset_names.map(datasetLabel).join(' · ')">{{ batch.dataset_names.map(datasetLabel).join(" · ") }}</small>
            </div>
            <div class="batch-result">
              <em :class="batchTone(batch)">{{ batchStatusLabel(batch.status) }}</em>
              <small>成功 {{ batch.completed_count }} · 失败 {{ batch.failed_count }} · 执行 {{ batch.settled_count }}/{{ batch.total_count }}</small>
            </div>
            <div class="batch-time">
              <strong>{{ collectionTimeLabel(batch.started_at) }}</strong>
              <small>{{ batch.finished_at ? `结束 ${collectionTimeLabel(batch.finished_at)} · 耗时 ${batchDuration(batch)}` : batch.current_dataset_label ? `当前：${batch.current_dataset_label}` : "后台执行中" }}</small>
            </div>
            <div class="batch-fail-cell">
              <button v-if="batch.failure_details.length" type="button" class="batch-fail-toggle">
                <CircleAlert :size="13" />{{ batch.failure_details.length }} 项失败
              </button>
              <span v-else class="batch-ok"><CircleCheck :size="13" />全部通过</span>
            </div>
            <details v-if="batch.failure_details.length" class="batch-failures">
              <summary>查看失败明细</summary>
              <div v-for="item in batch.failure_details" :key="item.dataset_key" class="batch-failure-row">
                <strong>{{ item.dataset_label || datasetLabel(item.dataset_key) }}</strong>
                <small>{{ collectionErrorLabel(item.error_message || "目标日期未完成入库") }}</small>
              </div>
              <p class="batch-fail-note">{{ failureHeadline(batch) }}</p>
              <button type="button" class="retry-failed" :disabled="dailyRunning || retryingBatchId === batch.batch_id" @click="retryFailedBatch(batch)">
                <RefreshCw :size="14" :class="{ spinning: retryingBatchId === batch.batch_id }" />{{ retryingBatchId === batch.batch_id ? "正在创建重试" : "重试失败项" }}
              </button>
            </details>
          </article>
        </div>
        <p v-else class="architecture-note">暂无采集批次。</p>

        <!-- 当前子任务（最近 crawl run） -->
        <div v-if="activeCrawl" class="crawl-run-block">
          <div class="crawl-run-heading">
            <div><p>当前子任务</p><h3>{{ taskTypeLabel(activeCrawl.task_type) }}</h3></div>
            <em class="crawl-run-status" :class="{ running: activeCrawl.status === 'running' }">{{ crawlStatusLabel(activeCrawl.status) }}</em>
          </div>
          <div class="crawl-summary">
            <div><span>任务编号</span><strong>{{ activeCrawl.run_id }}</strong><small>{{ activeCrawl.mode }} · 店铺 {{ activeCrawl.store_id }}</small></div>
            <div><span>完成情况</span><strong>{{ activeCrawl.success_days }} / {{ activeCrawl.planned_days }}</strong><small>成功日期 / 计划日期</small></div>
            <div><span>结束时间</span><strong>{{ activeCrawl.finished_at ? collectionTimeLabel(activeCrawl.finished_at) : "仍在运行" }}</strong><small v-if="activeCrawl.started_at">{{ collectionTimeLabel(activeCrawl.started_at) }} 开始</small></div>
          </div>
          <div class="task-progress-meter"><div><span>任务完成度</span><strong>{{ crawlProgress }}%</strong></div><i><em :style="{ width: `${crawlProgress}%` }"></em></i></div>
          <div v-if="crawlDays.length" class="crawl-day-list"><div v-for="day in crawlDays" :key="day.item_id" class="crawl-day-row"><span>{{ day.business_day }}</span><strong :class="dayStatusClass(day)">{{ dayStatusLabel(day.status) }}</strong><small>{{ day.metric_count ? `${day.metric_count} 项指标` : "" }}</small><em v-if="day.error_message" :title="day.error_message">{{ collectionErrorLabel(day.error_message) }}</em></div></div>
          <div v-if="failedCrawlDays.length" class="crawl-warning"><CircleAlert :size="16" /><span>本次有 {{ failedCrawlDays.length }} 个日期未完成。</span></div>
        </div>

        <!-- 子任务历史 -->
        <div v-if="crawlRuns.length" class="crawl-run-block">
          <div class="crawl-run-heading"><div><p>历史子任务</p><h3>采集记录（{{ crawlRuns.length }}）</h3></div></div>
          <div class="run-history-list">
            <button v-for="run in crawlRuns" :key="run.run_id" type="button" :class="{ active: activeCrawl?.run_id === run.run_id }" @click="selectCrawlRun(run)">
              <span>{{ taskTypeLabel(run.task_type) }}</span>
              <strong :class="runStatusTone(run.status) === 'ready' ? 'ready' : runStatusTone(run.status) === 'failed' ? 'failed' : 'muted'">{{ crawlStatusLabel(run.status) }}</strong>
              <small>{{ run.start_day }} · 成功 {{ run.success_days }} · 跳过 {{ run.skipped_days }} · 失败 {{ run.failed_days }}</small>
            </button>
          </div>
        </div>
      </section>
    </template>
  </template>

  <!-- ============ 评价与问答 ============ -->
  <template v-else>
    <div class="task-view-context"><strong>用户反馈增量</strong><span>评价与问答分开执行增量采集，只补充数据库中还没有的新内容。</span></div>

    <section v-if="reviewLoading && !reviewRuns.length && askLoading && !askRuns.length" class="loading-panel">
      <LoaderCircle :size="28" class="spinning" /><span>正在读取评价与问答任务</span>
    </section>

    <section v-else-if="(reviewError && !reviewRuns.length) || (askError && !askRuns.length)" class="error-panel">
      <CircleAlert :size="24" /><div><strong>反馈采集任务暂不可用</strong><p>{{ reviewError || askError }}</p></div><button @click="refreshCurrentView">重试</button>
    </section>

    <template v-else>
      <div v-if="dailyRunning" class="feedback-blocker"><DatabaseZap :size="16" /><span>日常经营采集正在占用浏览器，评价与问答增量采集需等待其结束后再启动。</span></div>

      <section class="feedback-actions">
        <button class="capture-refresh" :disabled="dailyRunning || reviewCollecting || reviewLoading || reviewRunning" title="只采集数据库中还没有的新评价" @click="collectNewReviews">
          <MessageSquarePlus :size="16" :class="{ spinning: reviewCollecting }" />{{ reviewCollecting ? "创建中" : reviewRunning ? "评价采集中" : "采集新评价" }}
        </button>
        <button class="capture-refresh" :disabled="dailyRunning || askCollecting || askLoading || askRunning" title="只采集数据库中还没有的新问答" @click="collectNewAsks">
          <MessageSquarePlus :size="16" :class="{ spinning: askCollecting }" />{{ askCollecting ? "创建中" : askRunning ? "问答采集中" : "采集新问答" }}
        </button>
      </section>

      <section class="feedback-summary" aria-label="评价与问答任务摘要">
        <article class="panel feedback-stat">
          <span>最近评价任务</span>
          <strong>{{ latestReviewRun ? collectionStatusLabel(latestReviewRun.status) : "暂无任务" }}</strong>
          <small>{{ latestReviewRun ? `${collectionTimeLabel(latestReviewRun.started_at)} · 新增 ${number(latestReviewRun.inserted_count)}` : "点击上方按钮采集新评价" }}</small>
        </article>
        <article class="panel feedback-stat">
          <span>最近问答任务</span>
          <strong>{{ latestAskRun ? collectionStatusLabel(latestAskRun.status) : "暂无任务" }}</strong>
          <small>{{ latestAskRun ? `${collectionTimeLabel(latestAskRun.started_at)} · 新增 ${number(latestAskRun.inserted_count)}` : "点击上方按钮采集新问答" }}</small>
        </article>
        <article class="panel feedback-stat">
          <span>最近失败任务</span>
          <strong :class="{ 'feedback-stat-danger': recentFeedbackFailures > 0 }">{{ number(recentFeedbackFailures) }}</strong>
          <small>最近加载的评价与问答记录</small>
        </article>
        <article class="panel feedback-stat">
          <span>采集规则</span>
          <strong>仅采集新增</strong>
          <small>已存在记录不会重复写入</small>
        </article>
      </section>

      <section class="feedback-task-grid">
        <section class="panel architecture-panel review-task-panel">
          <div class="panel-heading">
            <div><p>评价采集</p><h2>评价任务</h2></div>
            <div class="panel-heading-actions">
              <button class="panel-icon-action" type="button" title="刷新评价任务" :disabled="reviewLoading" @click="loadReviewRuns"><RefreshCw :size="17" :class="{ spinning: reviewLoading }" /></button>
            </div>
          </div>
          <div v-if="reviewError" class="inline-error">{{ reviewError }}</div>
          <div v-if="reviewRuns.length" class="review-task-list">
            <div v-for="run in visibleReviewRuns" :key="run.run_id" class="review-task-row">
              <div class="review-task-main">
                <strong>{{ collectionModeLabel(run.mode, "review") }}</strong>
                <span>{{ collectionTimeLabel(run.started_at) }}{{ run.finished_at ? ` · 结束 ${collectionTimeLabel(run.finished_at)}` : "" }}</span>
              </div>
              <em :class="runStatusTone(run.status)">{{ collectionStatusLabel(run.status) }}</em>
              <div class="review-task-detail">
                <small v-if="run.status === 'completed'">新增 {{ run.inserted_count }} · 更新 {{ run.updated_count }} · 抓取 {{ run.fetched_count }}</small>
                <small v-else-if="run.error" class="review-task-error">{{ collectionErrorLabel(run.error) }}</small>
                <small v-else>后台执行中</small>
              </div>
            </div>
          </div>
          <p v-else class="architecture-note">暂无评价采集任务。</p>
        </section>

        <section class="panel architecture-panel review-task-panel">
          <div class="panel-heading">
            <div><p>问大家采集</p><h2>买家问答任务</h2></div>
            <div class="panel-heading-actions">
              <button class="panel-icon-action" type="button" title="刷新问答任务" :disabled="askLoading" @click="loadAskRuns"><RefreshCw :size="17" :class="{ spinning: askLoading }" /></button>
            </div>
          </div>
          <div v-if="askError" class="inline-error">{{ askError }}</div>
          <div v-if="askRuns.length" class="review-task-list">
            <div v-for="run in visibleAskRuns" :key="run.run_id" class="review-task-row">
              <div class="review-task-main">
                <strong>{{ collectionModeLabel(run.mode, "ask") }}</strong>
                <span>{{ collectionTimeLabel(run.started_at) }}{{ run.finished_at ? ` · 结束 ${collectionTimeLabel(run.finished_at)}` : "" }}</span>
              </div>
              <em :class="runStatusTone(run.status)">{{ collectionStatusLabel(run.status) }}</em>
              <div class="review-task-detail">
                <small v-if="run.status === 'completed'">新增 {{ run.inserted_count }} · 更新 {{ run.updated_count }} · 抓取 {{ run.fetched_count }}</small>
                <small v-else-if="run.error" class="review-task-error">{{ collectionErrorLabel(run.error) }}</small>
                <small v-else>后台执行中</small>
              </div>
            </div>
          </div>
          <p v-else class="architecture-note">暂无买家问答采集任务。</p>
        </section>
      </section>
    </template>
  </template>
</template>

<style scoped>
/* ---- 顶部命令条 ---- */
.imports-hero { min-height: 132px; align-items: stretch; }
.imports-hero-copy { min-width: 0; }
.imports-hero-side { display: flex; flex: 0 0 auto; flex-direction: column; align-items: flex-end; justify-content: space-between; gap: 12px; }
.imports-live-chip { display: inline-flex; align-items: center; gap: 7px; border: 1px solid #dce8e1; border-radius: 999px; padding: 4px 11px; color: #6f8078; background: #f7faf8; font-size: 10px; font-weight: 650; }
.imports-live-chip.active { border-color: #bfe3cf; color: #167a55; background: #eef9f3; }
.imports-live-dot { width: 7px; height: 7px; border-radius: 50%; background: #9fb2a8; }
.imports-live-chip.active .imports-live-dot { background: #27ad77; box-shadow: 0 0 0 3px rgba(39, 173, 119, .18); }

/* ---- 视图切换 ---- */
.task-view-tabs { display: flex; align-items: center; gap: 4px; margin: 0; border-bottom: 1px solid #dfe9e3; }
.task-view-tabs > button { display: inline-flex; min-height: 36px; align-items: center; gap: 7px; border: 0; border-bottom: 2px solid transparent; padding: 0 12px; color: #7b8b82; background: transparent; font: inherit; font-size: 12px; cursor: pointer; }
.task-view-tabs > button em { font-style: normal; color: #9aa89f; font-size: 10px; font-weight: 500; }
.task-view-tabs > button.active { border-bottom-color: #16845b; color: #166f4e; font-weight: 700; }
.task-view-tabs > button.active em { color: #4a8a6f; }
.task-view-link { display: inline-flex; margin-left: auto; align-items: center; gap: 6px; min-height: 36px; padding: 0 12px; color: #6f8078; font-size: 11px; text-decoration: none; white-space: nowrap; }
.task-view-link:hover { color: #16845b; }
.task-view-link-arrow { opacity: .6; }

.task-view-context { display: flex; align-items: center; gap: 10px; margin: 0 0 14px; border-bottom: 1px solid #e7eee9; padding: 10px 12px; color: #7d8d84; background: #f8fbf9; font-size: 11px; }
.task-view-context strong { flex: 0 0 auto; color: #315b47; font-size: 11px; }

/* ---- KPI / 面板基线（沿用共享 token，仅做主题自适应） ---- */
.capture-stat strong { color: #284b3a; }
.capture-stat-danger { color: #c04444 !important; }

/* ---- 批次表 ---- */
.collection-batch-list { display: grid; }
.collection-batch-head, .collection-batch-row { display: grid; grid-template-columns: 120px minmax(240px, 1fr) 150px minmax(190px, 200px) 130px; align-items: center; gap: 14px; padding: 10px 16px; }
.collection-batch-head { min-height: 30px; border-bottom: 1px solid #dfe8e3; color: #89968f; font-size: 10px; }
.collection-batch-row { min-height: 72px; border-bottom: 1px solid #e9efeb; position: relative; }
.collection-batch-row:last-child { border-bottom: 0; }
.collection-batch-row > div { display: grid; min-width: 0; gap: 4px; }
.collection-batch-row > .batch-result, .collection-batch-row > .batch-time { align-items: start; }
.collection-batch-row strong { color: #354d40; font-size: 12px; }
.collection-batch-row span, .collection-batch-row small { overflow: hidden; color: #89968f; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.batch-date span { width: fit-content; border-radius: 8px; padding: 2px 6px; color: #557765; background: #eef5f1; }
.batch-result em { width: fit-content; border-radius: 10px; padding: 3px 7px; font-size: 10px; font-style: normal; }
.batch-result em.ready { color: #167752; background: #eaf7ef; }
.batch-result em.running { color: #84631d; background: #fff6df; }
.batch-result em.warn, .batch-result em.failed { color: #a84c43; background: #fff0ed; }
.batch-time small { white-space: normal; overflow: visible; }
.batch-fail-cell { display: grid; gap: 6px; align-content: center; }
.batch-fail-toggle { display: inline-flex; width: fit-content; align-items: center; gap: 5px; border: 1px solid #e5b9b0; border-radius: 4px; padding: 5px 8px; color: #a44d43; background: #fff8f6; font: inherit; font-size: 10px; cursor: pointer; }
.batch-fail-toggle:hover { background: #fdeee9; }
.batch-ok { display: inline-flex; width: fit-content; align-items: center; gap: 5px; border-radius: 4px; padding: 5px 8px; color: #167752; background: #eaf7ef; font-size: 10px; }
.batch-failures { grid-column: 1 / -1; margin-top: 6px; border: 1px solid #f0e2df; border-radius: 6px; background: #fffafa; padding: 10px 14px; }
.batch-failures[open] { border-color: #e3b8ae; }
.batch-failures summary { color: #a84c43; font-size: 11px; cursor: pointer; }
.batch-failure-row { display: grid; grid-template-columns: 150px minmax(0, 1fr); gap: 10px; align-items: start; padding: 7px 0; border-bottom: 1px dashed #f3ded9; }
.batch-failure-row:last-of-type { border-bottom: 0; }
.batch-failure-row strong { color: #624843; font-size: 11px; }
.batch-failure-row small { overflow: visible; color: #9d6b64; font-size: 10px; white-space: normal; }
.batch-fail-note { margin: 8px 0 6px; color: #8a5a52; font-size: 10px; }
.retry-failed { display: inline-flex; align-items: center; gap: 5px; margin-top: 2px; border: 1px solid #e5b9b0; border-radius: 4px; padding: 6px 9px; color: #a44d43; background: #fff8f6; font: inherit; font-size: 10px; cursor: pointer; }
.retry-failed:disabled { cursor: not-allowed; opacity: .55; }

/* ---- 当前子任务 / 历史子任务 ---- */
.crawl-run-block { border-top: 1px solid #e9efeb; padding: 14px 16px 18px; }
.crawl-run-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 12px; }
.crawl-run-heading p { margin: 0 0 4px; color: #89968f; font-size: 10px; }
.crawl-run-heading h3 { margin: 0; color: #284b3a; font-size: 14px; font-weight: 680; }
.crawl-run-status { font-style: normal; font-size: 11px; color: #35608d; }
.crawl-run-status.running { color: #84631d; }
.crawl-summary { margin-top: 14px; }
.crawl-summary div { display: grid; gap: 3px; }
.crawl-summary span, .crawl-summary small { color: #89968f; font-size: 10px; }
.crawl-summary strong { color: #354d40; font-size: 13px; font-weight: 650; word-break: break-all; }
.crawl-day-row { display: grid; grid-template-columns: 120px 100px 100px minmax(0, 1fr); gap: 12px; align-items: center; border-bottom: 1px solid #eef2ef; padding: 9px 0; }
.crawl-day-row:last-child { border-bottom: 0; }
.crawl-day-row span, .crawl-day-row small { color: #89968f; font-size: 11px; }
.crawl-day-row small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.crawl-day-row strong { color: #354d40; font-size: 11px; font-weight: 650; }
.crawl-day-row strong.ready { color: #167752; }
.crawl-day-row strong.failed { color: #a84c43; }
.crawl-day-row strong.muted { color: #8a9890; }
.crawl-day-row em { overflow: hidden; font-style: normal; color: #9d6b64; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.crawl-warning { margin-top: 12px; }
.run-history-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 8px; margin-top: 12px; }
.run-history-list button { display: grid; gap: 3px; align-content: start; border: 1px solid #dfe8e3; border-radius: 6px; padding: 10px 12px; text-align: left; background: #fbfdfc; cursor: pointer; }
.run-history-list button:hover { border-color: #bfe0cf; background: #f4faf6; }
.run-history-list button.active { border-color: #16845b; box-shadow: inset 0 0 0 1px #16845b; background: #eef9f3; }
.run-history-list button span { color: #405449; font-size: 12px; font-weight: 650; }
.run-history-list button strong { color: #89968f; font-size: 10px; }
.run-history-list button strong.ready { color: #167752; }
.run-history-list button strong.failed { color: #a84c43; }
.run-history-list button strong.muted { color: #8a9890; }
.run-history-list button small { color: #89968f; font-size: 10px; }

/* ---- 反馈阻塞提示 ---- */
.feedback-blocker { display: flex; align-items: center; gap: 10px; border: 1px solid #ead5ab; border-radius: 6px; padding: 11px 14px; color: #8f661e; background: #fdf8eb; font-size: 11px; }
.feedback-blocker svg { flex: 0 0 auto; }

/* ---- 反馈操作 ---- */
.feedback-actions { display: flex; flex-wrap: wrap; gap: 9px; margin-bottom: 14px; }

/* ---- 反馈摘要 ---- */
.feedback-summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-bottom: 14px; }
.feedback-stat { display: grid; min-height: 88px; align-content: center; gap: 5px; padding: 14px 16px; }
.feedback-stat span, .feedback-stat small { color: #89968f; font-size: 10px; }
.feedback-stat strong { color: #284b3a; font-size: 18px; }
.feedback-stat-danger { color: #c04444; }

/* ---- 反馈任务卡 ---- */
.feedback-task-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.panel-heading-actions { display: flex; align-items: center; gap: 8px; }
.panel-icon-action { display: inline-grid; width: 30px; height: 30px; place-items: center; border: 1px solid #d8e5dc; border-radius: 4px; color: #16845b; background: #fff; cursor: pointer; }
.panel-icon-action:disabled { cursor: not-allowed; opacity: .5; }
.review-task-list { display: grid; }
.review-task-row { display: grid; grid-template-columns: minmax(180px, 1.1fr) 90px minmax(150px, 1fr); align-items: center; gap: 14px; border-bottom: 1px solid #edf2ee; padding: 13px 0; }
.review-task-row:last-child { border-bottom: 0; }
.review-task-main { display: grid; gap: 3px; min-width: 0; }
.review-task-main strong { color: #405449; font-size: 12px; }
.review-task-main span { color: #8a9a91; font-size: 10px; }
.review-task-detail { min-width: 0; }
.review-task-detail small { display: block; overflow: hidden; color: #8a9a91; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.review-task-detail small.review-task-error { color: #a44d4d; white-space: normal; }
.review-task-row em { width: fit-content; border-radius: 999px; padding: 4px 8px; font-size: 10px; font-style: normal; }
.review-task-row em.ready { color: #176b4b; background: #eff8f2; }
.review-task-row em.running { color: #9a713b; background: #fff7e8; }
.review-task-row em.failed { color: #a44d4d; background: #fff0f0; }

/* ---- 响应式 ---- */
@media (max-width: 1050px) {
  .collection-batch-head { display: none; }
  .collection-batch-row { grid-template-columns: 110px minmax(180px, 1fr) 120px; }
  .collection-batch-row > .batch-time { grid-column: 1 / -1; }
  .collection-batch-row > .batch-fail-cell { grid-column: 1 / -1; }
}
@media (max-width: 900px) {
  .feedback-task-grid { grid-template-columns: 1fr; }
}
@media (max-width: 760px) {
  .task-view-tabs { overflow-x: auto; }
  .task-view-link { display: none; }
  .task-view-tabs > button { flex: 0 0 auto; }
  .task-view-context { align-items: flex-start; flex-direction: column; gap: 3px; }
  .imports-hero { flex-direction: column; }
  .imports-hero-side { align-items: stretch; }
  .imports-hero-side .hero-actions { flex-direction: column; align-items: stretch; }
  .imports-hero-side .capture-refresh { justify-content: center; }
  .feedback-summary { grid-template-columns: 1fr 1fr; }
  .collection-batch-row { grid-template-columns: 1fr 1fr; gap: 10px; }
  .review-task-row { grid-template-columns: 1fr; gap: 7px; }
}
@media (max-width: 480px) {
  .feedback-summary { grid-template-columns: 1fr; }
}
</style>
