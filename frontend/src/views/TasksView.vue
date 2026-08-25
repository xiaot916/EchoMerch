<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { CalendarClock, CheckCircle2, Database, FileLock2, ShieldCheck } from "lucide-vue-next"

import { useCapabilities } from "@/composables/useCapabilities"
import { fetchCrawlRuns } from "@/api"
import type { CrawlRun } from "@/types"

const { capabilities, ensureCapabilities } = useCapabilities()
const crawlRuns = ref<CrawlRun[]>([])
const crawlError = ref("")
const latestCrawl = computed(() => crawlRuns.value[0] ?? null)
const latestProgress = computed(() => {
  const run = latestCrawl.value
  if (!run || !run.planned_days) return 0
  return Math.min(100, Math.round(((run.success_days + run.skipped_days) / run.planned_days) * 100))
})

const modules = [
  { title: "历史数据分析", status: "运行中", detail: "当前只读查询已启用，所有请求都通过只读适配器执行。", icon: CheckCircle2, tone: "ready" },
  { title: "Reqable 离线分析", status: "运行中", detail: "本地 SQLite 已接入抓包摘要，用于验证接口族、字段路径和后续按日采集契约。", icon: Database, tone: "ready" },
  { title: "脚本采集执行", status: "已接入", detail: "经营数据、评价和问大家均由后台 Worker 执行，网页只负责创建任务和展示状态。", icon: CheckCircle2, tone: "ready" },
  { title: "批量营销操作", status: "待设计", detail: "建券等动作将提供预览、二次确认、幂等键和逐条执行结果。", icon: FileLock2, tone: "queued" },
  { title: "定时任务", status: "已接入", detail: "每日采集由独立调度器创建批次，并通过任务记录避免同一天重复执行。", icon: CalendarClock, tone: "ready" },
]

const moduleLabels: Record<string, string> = {
  "analytics.dashboard": "经营概览 API",
  "analytics.products": "商品分析 API",
  "analytics.traffic": "流量归因 API",
  "analytics.promotions": "推广计划 API",
  "captures.offline_analysis": "Reqable 离线分析",
  "contracts.catalog": "接口契约中心",
  "imports.daily_dry_run": "按日导入干跑",
  "operations.control_center": "批量操作中心",
  "crawler.execution": "爬虫执行",
  "coupon.batch_create": "批量建券",
  "tmall.browser_automation": "天猫浏览器自动化",
  "captures.request_replay": "抓包请求回放",
  scheduled_jobs: "定时任务",
}

function moduleLabel(code: string): string {
  return moduleLabels[code] ?? code
}

function crawlStatusLabel(status: string): string {
  if (status === "running") return "采集中"
  if (status === "completed") return "已完成"
  if (status === "completed_with_errors") return "部分失败"
  if (status === "stopped") return "已停止"
  return status
}

async function loadCrawlRuns(): Promise<void> {
  crawlError.value = ""
  try {
    crawlRuns.value = (await fetchCrawlRuns(5)).runs
  } catch (exc) {
    crawlError.value = exc instanceof Error ? exc.message : "采集任务暂不可用"
  }
}

onMounted(() => {
  void ensureCapabilities()
  void loadCrawlRuns()
})
</script>

<template>
  <section class="tasks-intro">
    <div><p>自动化运行区</p><h2>采集任务与安全边界</h2><span>网页可以创建只读采集任务，实际抓取由后台 Worker 执行；营销写操作仍保持关闭。</span></div>
    <div class="tasks-intro-icon"><ShieldCheck :size="30" /></div>
  </section>

  <section class="panel task-live-panel">
    <div class="panel-heading">
      <div><p>运行概况</p><h2>最近采集任务</h2></div>
      <RouterLink class="panel-link" to="/imports">查看明细</RouterLink>
    </div>
    <div v-if="latestCrawl" class="task-live-grid">
      <div><span>状态</span><strong :class="latestCrawl.status === 'running' ? 'ready' : latestCrawl.status === 'completed_with_errors' ? 'warning' : ''">{{ crawlStatusLabel(latestCrawl.status) }}</strong></div>
      <div><span>日期范围</span><strong>{{ latestCrawl.start_day }} 至 {{ latestCrawl.end_day }}</strong></div>
      <div><span>完成情况</span><strong>{{ latestCrawl.success_days }} 成功 · {{ latestCrawl.skipped_days }} 跳过 · {{ latestCrawl.failed_days }} 失败</strong></div>
    </div>
    <div v-if="latestCrawl" class="task-progress-meter"><div><span>日期完成度</span><strong>{{ latestProgress }}%</strong></div><i><em :style="{ width: `${latestProgress}%` }"></em></i></div>
    <p v-else-if="crawlError" class="architecture-note">{{ crawlError }}</p>
    <p v-else class="architecture-note">当前还没有采集任务记录。准备开始后，任务进度会显示在这里。</p>
  </section>

  <section class="task-roadmap">
    <article v-for="module in modules" :key="module.title" class="task-module panel">
      <div class="task-icon" :class="module.tone"><component :is="module.icon" :size="21" /></div>
      <div><div class="task-title"><h3>{{ module.title }}</h3><span :class="module.tone">{{ module.status }}</span></div><p>{{ module.detail }}</p></div>
    </article>
  </section>

  <section class="panel task-principles">
    <div class="panel-heading"><div><p>后续接入规则</p><h2>先可追踪，再自动化</h2></div><FileLock2 :size="18" /></div>
    <div class="principle-grid">
      <div><strong>01</strong><span>浏览器或 API 凭据加密存储，不进入代码和日志。</span></div>
      <div><strong>02</strong><span>每次执行生成任务记录、日志和可审计的状态变化。</span></div>
      <div><strong>03</strong><span>批量动作必须预览和确认，支持失败项定位与重试。</span></div>
    </div>
  </section>

  <section v-if="capabilities" class="content-grid capability-grid">
    <article class="panel capability-panel">
      <div class="panel-heading"><div><p>已启用能力</p><h2>当前可用模块</h2></div><CheckCircle2 :size="18" /></div>
      <div class="capability-list">
        <span v-for="item in capabilities.enabled_modules" :key="item">{{ moduleLabel(item) }}</span>
      </div>
    </article>
    <article class="panel capability-panel">
      <div class="panel-heading"><div><p>安全关闭</p><h2>暂不暴露的能力</h2></div><FileLock2 :size="18" /></div>
      <div class="capability-list muted">
        <span v-for="item in capabilities.disabled_modules" :key="item">{{ moduleLabel(item) }}</span>
      </div>
    </article>
  </section>

  <section v-if="capabilities" class="panel safety-panel">
    <div class="panel-heading"><div><p>系统护栏</p><h2>这一阶段的硬边界</h2></div><ShieldCheck :size="18" /></div>
    <div class="safety-list">
      <div v-for="(rule, index) in capabilities.safety_rules" :key="rule"><strong>{{ String(index + 1).padStart(2, "0") }}</strong><span>{{ rule }}</span></div>
    </div>
  </section>
</template>
