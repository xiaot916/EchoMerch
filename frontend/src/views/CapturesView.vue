<script setup lang="ts">
import { computed, onMounted } from "vue"
import { CheckCircle2, Database, FileLock2, RefreshCw, Route, ShieldCheck } from "lucide-vue-next"

import EmptyState from "@/components/EmptyState.vue"
import { useCaptureSummary } from "@/composables/useCaptureSummary"
import { number } from "@/lib/format"

const { summary, loading, error, hasSummary, ensureCaptureSummary, loadCaptureSummary } = useCaptureSummary()

const familyLabels: Record<string, string> = {
  sycm_analytics: "生意参谋分析",
  qianniu_platform: "千牛平台",
  qianniu_coupon: "优惠券/权益",
  mtop: "MTop 传输",
  websocket: "实时流",
  platform_api: "平台通用",
}

const adapterPlan = [
  { family: "sycm_analytics", title: "SYCM 只读分析适配器", status: "候选已发现", icon: CheckCircle2, tone: "ready" },
  { family: "qianniu_coupon", title: "优惠券任务适配器", status: "发现中", icon: FileLock2, tone: "queued" },
  { family: "mtop", title: "MTop 传输封装", status: "待定契约", icon: Route, tone: "queued" },
  { family: "websocket", title: "实时流样本", status: "待定结构", icon: ShieldCheck, tone: "queued" },
]

const observationTotal = computed(() =>
  summary.value?.families.reduce((total, item) => total + item.observations, 0) ?? 0,
)
const familyPeak = computed(() => Math.max(...(summary.value?.families.map((item) => item.observations) ?? [1]), 1))

function familyCount(family: string): number {
  return summary.value?.families.find((item) => item.family === family)?.observations ?? 0
}

function dateRange(): string {
  if (!summary.value?.first_date) return "--"
  if (summary.value.first_date === summary.value.last_date) return summary.value.first_date
  return `${summary.value.first_date} 至 ${summary.value.last_date}`
}

function importedAt(): string {
  if (!summary.value?.imported_at) return "--"
  return new Date(summary.value.imported_at).toLocaleString("zh-CN", { hour12: false })
}

onMounted(() => {
  void ensureCaptureSummary()
})
</script>

<template>
  <section class="capture-hero">
    <div>
      <p>本地采集实验室</p>
      <h2>Reqable 离线接口样本</h2>
      <span>当前只读取本地分析库，保留接口族、路径候选、字段形状和导入统计。</span>
    </div>
    <button class="capture-refresh" :disabled="loading" @click="loadCaptureSummary">
      <RefreshCw :size="16" :class="{ spinning: loading }" />
      刷新
    </button>
  </section>

  <section v-if="error" class="panel capture-error">
    <Database :size="22" />
    <div><strong>抓包分析库暂不可用</strong><span>{{ error }}</span></div>
  </section>

  <template v-else-if="hasSummary && summary">
    <section class="capture-metrics">
      <article class="panel capture-stat">
        <span>样本文件</span><strong>{{ number(summary.file_count) }}</strong><small>{{ dateRange() }}</small>
      </article>
      <article class="panel capture-stat">
        <span>接口族观察</span><strong>{{ number(observationTotal) }}</strong><small>按候选路径聚合</small>
      </article>
      <article class="panel capture-stat">
        <span>按日请求体</span><strong>{{ number(summary.daily_requests.reduce((total, item) => total + item.files, 0)) }}</strong><small>业务日期参数</small>
      </article>
      <article class="panel capture-stat">
        <span>最近导入</span><strong>{{ importedAt() }}</strong><small>本地 SQLite</small>
      </article>
    </section>

    <section class="content-grid capture-grid">
      <article class="panel capture-family-panel">
        <div class="panel-heading"><div><p>接口族分布</p><h2>本地样本归类</h2></div><Route :size="18" /></div>
        <div class="capture-family-list">
          <div v-for="item in summary.families" :key="item.family">
            <span>{{ familyLabels[item.family] ?? item.family }}</span>
            <div class="capture-mini-bar"><i :style="{ width: `${(item.observations / familyPeak) * 100}%` }"></i></div>
            <strong>{{ number(item.observations) }}</strong>
          </div>
        </div>
      </article>

      <article class="panel capture-family-panel">
        <div class="panel-heading"><div><p>按日参数</p><h2>请求体候选</h2></div><Database :size="18" /></div>
        <div v-if="summary.daily_requests.length" class="capture-family-list">
          <div v-for="item in summary.daily_requests" :key="`${item.business_date}-${item.date_mode}`">
            <span>{{ item.business_date || "未解析日期" }} · {{ item.date_mode }}</span>
            <strong>{{ number(item.files) }}</strong>
          </div>
        </div>
        <EmptyState v-else title="暂无按日请求体" detail="本地样本中还没有识别到明确的日维度参数。" :icon="Database" />
      </article>

      <article class="panel capture-adapter-panel">
        <div class="panel-heading"><div><p>落地路径</p><h2>后续适配器拆分</h2></div><ShieldCheck :size="18" /></div>
        <div class="adapter-list">
          <div v-for="item in adapterPlan" :key="item.family" class="adapter-row">
            <div class="task-icon" :class="item.tone"><component :is="item.icon" :size="18" /></div>
            <div><strong>{{ item.title }}</strong><span>{{ item.status }} · {{ number(familyCount(item.family)) }} 条观察</span></div>
          </div>
        </div>
      </article>
    </section>
  </template>

  <EmptyState v-else title="暂无本地抓包摘要" detail="当前还没有可展示的 Reqable 离线分析结果。" :icon="Database" />
</template>
