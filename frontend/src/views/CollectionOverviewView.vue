<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue"
import {
  AlertTriangle,
  CalendarClock,
  Check,
  CircleAlert,
  Clock3,
  Database,
  LoaderCircle,
  MonitorUp,
  Play,
  RefreshCw,
  RotateCcw,
  ServerCog,
} from "lucide-vue-next"

import { fetchCollectionHealth, fetchCollectionOverview, startCollectionBrowser, startDailyCollection, updateCollectionSchedule } from "@/api"
import { useAuth } from "@/composables/useAuth"
import type { BrowserHealth, CollectionOverview, DatasetCoverage, PlatformSessionStatus } from "@/types"
import { number } from "@/lib/format"

const { can } = useAuth()
const overview = ref<CollectionOverview | null>(null)
const health = ref<BrowserHealth | null>(null)
const loading = ref(false)
const starting = ref(false)
const launchingBrowser = ref(false)
const savingSchedule = ref(false)
const error = ref("")
const actionError = ref("")
const actionNotice = ref("")
const startingDatasets = ref<string[]>([])
const selectedDay = ref("")
const filter = ref<"all" | "attention" | "complete">("all")
const scheduleEnabled = ref(false)
const scheduleTime = ref("07:30")
const scheduleSource = ref("drissionpage")
let pollTimer: number | undefined
let healthAbortController: AbortController | undefined

const canManage = computed(() => can("data.manage"))
const datasets = computed(() => overview.value?.datasets ?? [])
const attentionDatasets = computed(() => datasets.value.filter((item) => !["complete", "no_data"].includes(item.status)))
const visibleDatasets = computed(() => {
  if (filter.value === "attention") return attentionDatasets.value
  if (filter.value === "complete") return datasets.value.filter((item) => ["complete", "no_data"].includes(item.status))
  return datasets.value
})
const running = computed(() => overview.value?.latest_batch?.status === "running")
const browserReady = computed(() => health.value?.browser_connected ?? false)
const sycmSessionReady = computed(() => platformStatus("sycm")?.authenticated ?? false)
const batchCoverageMessage = computed(() => {
  const batch = overview.value?.latest_batch
  if (!batch || batch.status === "running" || !batch.failed_count) return ""
  if (overview.value?.coverage_percent === 100) {
    return "当前目标日数据已经全部到达；最近批次的异常是原始执行记录，相关数据已由后续补采补齐。"
  }
  return `最近批次有 ${batch.failed_count} 个异常项，当前仍有 ${attentionDatasets.value.length} 个数据集需要补采或核查。`
})

function syncSchedule(): void {
  const schedule = overview.value?.schedule
  if (!schedule) return
  scheduleEnabled.value = schedule.enabled
  scheduleTime.value = schedule.run_time
  scheduleSource.value = schedule.session_source
}

async function load(day = selectedDay.value): Promise<void> {
  loading.value = true
  error.value = ""
  healthAbortController?.abort()
  healthAbortController = new AbortController()
  const healthTimeout = window.setTimeout(() => healthAbortController?.abort(), 5000)
  const healthRequest = fetchCollectionHealth(healthAbortController.signal)
    .then((result) => {
      health.value = result
    })
    .catch((requestError) => {
      if (requestError instanceof DOMException && requestError.name === "AbortError") return
      // Browser/session health is supplementary; it must not hide data coverage.
    })
    .finally(() => window.clearTimeout(healthTimeout))
  try {
    overview.value = await fetchCollectionOverview(day || undefined)
    selectedDay.value = overview.value.target_day
    syncSchedule()
    syncPolling()
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : "采集数据状态暂不可用"
  } finally {
    loading.value = false
  }
  void healthRequest
}

async function collect(datasetNames?: string[], refreshExisting = false): Promise<void> {
  const requestedDatasets = [...(datasetNames ?? attentionDatasets.value.map((item) => item.key))]
  if (!requestedDatasets.length) {
    actionError.value = "当前目标日没有可补采的数据集。请先刷新完整性状态。"
    return
  }
  starting.value = true
  startingDatasets.value = requestedDatasets
  actionError.value = ""
  actionNotice.value = ""
  try {
    if (!browserReady.value) {
      const launched = await launchBrowser(false)
      if (!launched) return
      if (!sycmSessionReady.value) {
        actionNotice.value = "已打开生意参谋登录页。请先完成登录，再重新点击采集；未登录时不会创建后台批次。"
        return
      }
    }
    const batch = await startDailyCollection({ day: selectedDay.value, datasetNames: requestedDatasets, sessionSource: "drissionpage", refreshExisting, resumeFromLatest: true })
    actionNotice.value = `已创建补采批次 ${batch.batch_id}，目标日 ${selectedDay.value}，正在后台处理。`
    await load()
  } catch (requestError) {
    actionError.value = requestError instanceof Error ? requestError.message : "采集任务启动失败"
    try {
      health.value = await fetchCollectionHealth()
    } catch {
      // Preserve the actionable collection error if the follow-up health read fails.
    }
  } finally {
    starting.value = false
    startingDatasets.value = []
  }
}

async function launchBrowser(showNotice = true): Promise<boolean> {
  launchingBrowser.value = true
  actionError.value = ""
  if (showNotice) actionNotice.value = ""
  try {
    health.value = await startCollectionBrowser()
    if (showNotice) {
      actionNotice.value = sycmSessionReady.value
        ? "已进入生意参谋并确认登录状态。"
        : "已打开生意参谋登录页，请完成登录后再开始采集。"
    }
    return true
  } catch (requestError) {
    const message = requestError instanceof Error ? requestError.message : "采集浏览器启动失败"
    actionError.value = message
    return false
  } finally {
    launchingBrowser.value = false
  }
}

async function collectAttention(): Promise<void> {
  // Partial datasets need a refresh so workers do not skip the whole day
  // merely because one of their companion tables already exists.
  await collect(attentionDatasets.value.map((item) => item.key), true)
}

function isDatasetStarting(key: string): boolean {
  return startingDatasets.value.includes(key)
}

async function saveSchedule(): Promise<void> {
  if (!overview.value) return
  savingSchedule.value = true
  actionError.value = ""
  try {
    overview.value.schedule = await updateCollectionSchedule({
      enabled: scheduleEnabled.value,
      runTime: scheduleTime.value,
      datasetNames: overview.value.datasets.map((item) => item.key),
      sessionSource: scheduleSource.value,
    })
    syncSchedule()
  } catch (requestError) {
    actionError.value = requestError instanceof Error ? requestError.message : "自动采集设置保存失败"
  } finally {
    savingSchedule.value = false
  }
}

function stopPolling(): void {
  if (pollTimer !== undefined) {
    window.clearInterval(pollTimer)
    pollTimer = undefined
  }
}

function syncPolling(): void {
  stopPolling()
  if (!running.value || document.visibilityState === "hidden") return
  pollTimer = window.setInterval(() => {
    if (document.visibilityState !== "hidden" && !loading.value) void load()
  }, 4000)
}

function handleVisibilityChange(): void {
  if (document.visibilityState === "hidden") stopPolling()
  else syncPolling()
}

function statusLabel(item: DatasetCoverage): string {
  if (item.status === "no_data") return item.collection_mode === "coverage_snapshot" ? "无在线商品" : "平台无数据"
  return { complete: "完整", partial: "部分缺失", missing: "未到达", failed: "采集失败", collecting: "采集中" }[item.status] || item.status
}

function statusDetail(item: DatasetCoverage): string {
  const coveragePrefix = item.collection_mode === "coverage_snapshot" ? "覆盖快照 · " : ""
  if (item.status === "complete") return item.collection_mode === "coverage_snapshot" ? `${coveragePrefix}${number(item.row_count)} 行已覆盖` : `${number(item.row_count)} 行已入库`
  if (item.status === "no_data") return item.collection_mode === "coverage_snapshot" ? "覆盖完成 · 当天没有在线商品" : "接口已返回，目标日期无业务数据"
  if (item.status === "partial") return item.error_message || `${coveragePrefix}${item.present_tables}/${item.expected_tables} 张表已到达`
  if (item.status === "failed") return [`目标日 ${selectedDay.value || "当前日期"} 未入库`, item.error_message || "最近一次采集失败"].join("；")
  if (item.status === "collecting") return "后台 Worker 正在处理"
  return item.error_message || (item.latest_date ? `最近数据停在 ${item.latest_date}；目标日 ${selectedDay.value || "当前日期"} 尚未入库` : "尚未采集到数据")
}

function tableProgress(item: DatasetCoverage): string {
  return `${item.present_tables}/${item.expected_tables}`
}

function isDailyPromotionDetail(item: DatasetCoverage): boolean {
  return ["sycm_bybt_items", "taobao_flash_sale_items"].includes(item.key)
}

function platformStatus(code: string): PlatformSessionStatus | undefined {
  return health.value?.platforms.find((item) => item.code === code)
}

function platformTone(item: PlatformSessionStatus): string {
  if (item.authenticated) return "ready"
  return item.page_detected ? "warning" : "offline"
}

function batchStatus(): string {
  const batch = overview.value?.latest_batch
  if (!batch) return "尚未运行"
  if (batch.status === "running") return "正在采集"
  if (batch.status === "completed") return "已完成"
  return "部分异常"
}

function formatTime(value: string | null | undefined): string {
  if (!value) return "--"
  return new Date(value).toLocaleString("zh-CN", { hour12: false })
}

onMounted(() => {
  document.addEventListener("visibilitychange", handleVisibilityChange)
  void load()
})
onUnmounted(() => {
  document.removeEventListener("visibilitychange", handleVisibilityChange)
  stopPolling()
  healthAbortController?.abort()
})
</script>

<template>
  <section class="module-hero collection-command-hero">
    <div>
      <p>数据采集与完整性</p>
      <h2>{{ selectedDay || "昨天" }} 数据到达情况</h2>
      <span>按业务数据集核对表级完整性。缺失、部分缺失、接口无数据和采集失败分别记录。</span>
    </div>
    <div class="hero-actions">
      <label class="collection-day-picker"><span>业务日期</span><input v-model="selectedDay" type="date" :disabled="loading || running" @change="load(selectedDay)" /></label>
      <button class="capture-refresh secondary-action" :disabled="loading" title="刷新数据状态" @click="load()"><RefreshCw :size="16" :class="{ spinning: loading }" />刷新</button>
      <button class="capture-refresh secondary-action" :disabled="!canManage || launchingBrowser" :title="browserReady ? '打开生意参谋并重新检查登录状态' : '启动独立采集浏览器'" @click="launchBrowser()"><LoaderCircle v-if="launchingBrowser" :size="16" class="spinning" /><MonitorUp v-else :size="16" />{{ launchingBrowser ? "检查中" : browserReady ? "检查平台登录" : "启动采集浏览器" }}</button>
      <button class="capture-refresh" :disabled="!canManage || starting || running || !attentionDatasets.length" title="采集缺失或异常的数据集" @click="collectAttention"><LoaderCircle v-if="starting" :size="16" class="spinning" /><Play v-else :size="16" />{{ starting ? "正在准备补采" : running ? "采集中" : `补采异常项 ${attentionDatasets.length}` }}</button>
    </div>
  </section>

  <section v-if="loading && !overview" class="loading-panel"><LoaderCircle :size="28" class="spinning" /><span>正在核对数据完整性</span></section>
  <section v-else-if="error && !overview" class="error-panel"><CircleAlert :size="24" /><div><strong>完整性状态不可用</strong><p>{{ error }}</p></div><button @click="load()">重试</button></section>

  <template v-else-if="overview">
    <div v-if="actionError" class="collection-alert" role="alert"><AlertTriangle :size="16" /><span>{{ actionError }}</span></div>
    <div v-if="actionNotice" class="collection-alert collection-context-note" role="status" aria-live="polite"><CircleAlert :size="16" /><span>{{ actionNotice }}</span></div>
    <section class="collection-kpi-grid">
      <article class="panel collection-kpi primary"><div><span>数据到达率</span><strong>{{ overview.coverage_percent }}%</strong></div><div class="coverage-track"><i :style="{ width: `${overview.coverage_percent}%` }" /></div><small>{{ overview.complete_count }} 个完整 · {{ overview.no_data_count }} 个平台无数据 · 共 {{ overview.total_datasets }} 个</small></article>
      <article class="panel collection-kpi"><AlertTriangle :size="18" /><div><span>需要处理</span><strong>{{ overview.partial_count + overview.missing_count + overview.failed_count }}</strong></div><small>部分缺失 {{ overview.partial_count }} · 未到达 {{ overview.missing_count }} · 失败 {{ overview.failed_count }}</small></article>
      <article class="panel collection-kpi"><ServerCog :size="18" /><div><span>最近批次</span><strong>{{ batchStatus() }}</strong></div><small>{{ overview.latest_batch ? `${overview.latest_batch.completed_count} 成功 / ${overview.latest_batch.failed_count} 异常` : "等待首次从页面运行" }}</small></article>
      <article class="panel collection-kpi"><CalendarClock :size="18" /><div><span>每日自动采集</span><strong>{{ overview.schedule.enabled ? overview.schedule.run_time : "未开启" }}</strong></div><small>{{ overview.schedule.next_run_at ? `下次 ${formatTime(overview.schedule.next_run_at)}` : "保存设置后由后台定时触发" }}</small></article>
    </section>
    <section v-if="batchCoverageMessage" class="collection-alert collection-context-note"><CircleAlert :size="16" /><span>{{ batchCoverageMessage }}</span></section>

    <section class="collection-health-strip"><div><i class="status-dot" :class="browserReady ? 'ready' : 'offline'" /><strong>采集浏览器</strong><span>{{ health?.detail || "状态未知" }}</span></div><div><Clock3 :size="15" /><strong>最近批次</strong><span>{{ formatTime(overview.latest_batch?.started_at) }}</span></div><div><Database :size="15" /><strong>状态生成</strong><span>{{ formatTime(overview.generated_at) }}</span></div></section>
    <section v-if="health?.platforms.length" class="collection-platform-grid">
      <article v-for="item in health.platforms" :key="item.code" class="panel collection-platform-status">
        <i class="status-dot" :class="platformTone(item)" />
        <div><strong>{{ item.name }}</strong><span>{{ item.authenticated ? "已登录" : item.page_detected ? "等待登录" : "未打开" }}</span></div>
        <p>{{ item.detail }}</p>
      </article>
    </section>

    <section class="collection-workspace-grid">
      <article class="panel collection-dataset-panel">
        <div class="panel-heading collection-heading-row"><div><p>数据完整性</p><h2>业务数据集</h2></div><div class="collection-filter-tabs" role="tablist" aria-label="数据集状态筛选"><button :class="{ active: filter === 'all' }" @click="filter = 'all'">全部 {{ datasets.length }}</button><button :class="{ active: filter === 'attention' }" @click="filter = 'attention'">需处理 {{ attentionDatasets.length }}</button><button :class="{ active: filter === 'complete' }" @click="filter = 'complete'">已到达 {{ overview.complete_count + overview.no_data_count }}</button></div></div>
        <div class="collection-dataset-table"><div class="collection-dataset-head"><span>数据集</span><span>状态</span><span>表级到达</span><span>最近数据</span><span>操作</span></div><div v-for="item in visibleDatasets" :key="item.key" class="collection-dataset-row"><div class="dataset-name-cell"><strong>{{ item.label }}</strong><span :title="`${item.group} · ${item.description}`">{{ item.group }} · {{ item.description }}</span><small v-if="isDailyPromotionDetail(item)" class="dataset-mode-badge">每日批量明细 · 按业务日期逐日留存，不覆盖历史</small><small v-else-if="item.collection_mode === 'coverage_snapshot'" class="dataset-mode-badge">每日全量覆盖 · 在线商品、当前价与红线价覆盖当天完整集合</small><small v-if="isDatasetStarting(item.key)" class="collection-action-state" role="status">正在提交 {{ selectedDay }}</small></div><div><span class="dataset-status" :class="item.status">{{ statusLabel(item) }}</span><small class="collection-status-detail" :class="{ 'has-error': !!item.error_message }" :title="statusDetail(item)">{{ statusDetail(item) }}</small></div><div class="table-arrival-cell"><strong>{{ tableProgress(item) }}</strong><span class="table-arrival-label">张表已处理</span><span v-for="table in item.tables" :key="table.table" :title="table.table"><Check v-if="table.present" :size="12" /><CircleAlert v-else :size="12" />{{ table.row_count }} 行<span v-if="table.status === 'no_data'"> · 平台无数据</span></span></div><div><strong>{{ item.latest_date || "--" }}</strong><small>{{ item.last_attempt_at ? `尝试 ${formatTime(item.last_attempt_at)}` : "无采集记录" }}</small></div><div class="dataset-action-cell"><button :disabled="!canManage || starting || running || item.status === 'no_data'" :title="item.status === 'complete' ? '重新采集此数据集' : item.status === 'partial' ? '重新执行并补齐缺失表' : item.status === 'no_data' ? '平台已明确返回无数据，无需补采' : '补采此数据集'" @click="collect([item.key], ['complete', 'partial'].includes(item.status))"><LoaderCircle v-if="isDatasetStarting(item.key)" :size="15" class="spinning" /><RotateCcw v-else :size="15" />{{ isDatasetStarting(item.key) ? "提交中" : item.status === "complete" ? "重采" : item.status === "partial" ? "补齐" : item.status === "no_data" ? "无需补采" : "补采" }}</button></div></div></div>
      </article>

      <aside class="collection-side-stack">
        <article class="panel collection-schedule-panel"><div class="panel-heading"><div><p>自动任务</p><h2>每日采集昨天</h2></div><CalendarClock :size="18" /></div><div class="schedule-enable-row"><div><strong>启用每日任务</strong><span>到点后自动创建昨天的采集批次</span></div><label class="toggle-control"><input v-model="scheduleEnabled" type="checkbox" :disabled="!canManage" /><i /></label></div><label class="schedule-field"><span>执行时间</span><input v-model="scheduleTime" type="time" :disabled="!canManage" /></label><label class="schedule-field"><span>会话来源</span><select v-model="scheduleSource" :disabled="!canManage"><option value="drissionpage">已登录采集浏览器</option><option value="env">环境变量</option></select></label><div class="schedule-meta"><div><span>时区</span><strong>{{ overview.schedule.timezone }}</strong></div><div><span>上次触发</span><strong>{{ overview.schedule.last_triggered_day || "--" }}</strong></div><div><span>采集范围</span><strong>全部 {{ overview.total_datasets }} 个数据集</strong></div></div><button class="schedule-save" :disabled="!canManage || savingSchedule" @click="saveSchedule"><Check :size="16" />{{ savingSchedule ? "保存中" : "保存自动任务" }}</button></article>
        <article class="panel collection-trend-panel"><div class="panel-heading"><div><p>最近 7 天</p><h2>数据到达率</h2></div><Database :size="18" /></div><div class="coverage-day-list"><div v-for="day in overview.recent_days" :key="day.day"><span>{{ day.day.slice(5) }}</span><div><i :style="{ width: `${day.coverage_percent}%` }" /></div><strong :class="{ attention: day.attention > 0 }">{{ day.coverage_percent }}%</strong></div></div></article>
      </aside>
    </section>
  </template>
</template>
