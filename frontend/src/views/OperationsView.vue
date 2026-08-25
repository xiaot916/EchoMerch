<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { Activity, AlertTriangle, CheckCircle2, FileLock2, LoaderCircle, RefreshCw, ShieldCheck, Workflow } from "lucide-vue-next"

import { fetchOperationSummary } from "@/api"
import { useDashboard } from "@/composables/useDashboard"
import type { OperationCenterSummary } from "@/types"
import { currency, number, ratio } from "@/lib/format"
import { dailyTrend } from "@/lib/analytics"

const { dashboard, ensureDashboard } = useDashboard()
const summary = ref<OperationCenterSummary | null>(null)
const loading = ref(false)
const error = ref("")
async function loadSummary(): Promise<void> {
  loading.value = true; error.value = ""
  try { summary.value = await fetchOperationSummary() } catch (exc) { error.value = exc instanceof Error ? exc.message : "经营工作台暂不可用" } finally { loading.value = false }
}
onMounted(() => {
  void loadSummary()
  void ensureDashboard()
})
const model = computed(() => dailyTrend(dashboard.value?.daily_metrics ?? []))
const latest = computed(() => {
  const metrics = dashboard.value?.daily_metrics ?? []
  return metrics.length ? metrics[metrics.length - 1] : undefined
})
const health = computed(() => {
  if (!dashboard.value) return { score: 0, label: "等待数据", tone: "neutral" }
  const trendScore = model.value.trend.direction === "up" ? 30 : model.value.trend.direction === "flat" ? 22 : 12
  const coverageScore = dashboard.value.period.missing_dates.length ? 12 : 25
  const conversionScore = dashboard.value.summary.conversion_rate >= 5 ? 25 : dashboard.value.summary.conversion_rate >= 3 ? 17 : 9
  const roiScore = dashboard.value.summary.promotion_roi >= 3 ? 20 : dashboard.value.summary.promotion_roi >= 1 ? 12 : 5
  const score = trendScore + coverageScore + conversionScore + roiScore
  return { score, label: score >= 80 ? "健康" : score >= 60 ? "需要关注" : "高风险", tone: score >= 80 ? "good" : score >= 60 ? "watch" : "risk" }
})
const actions = computed(() => {
  if (!dashboard.value) return []
  const list: Array<{ level: string; title: string; detail: string; link: string }> = []
  if (dashboard.value.period.missing_dates.length) list.push({ level: "warning", title: "店铺日报缺失", detail: `已入库 ${dashboard.value.daily_metrics.length}/${dashboard.value.period.expected_days} 天。`, link: "数据完整性" })
  if (dashboard.value.comparison.conversion_rate.change_percent !== null && dashboard.value.comparison.conversion_rate.change_percent < -5) list.push({ level: "warning", title: "支付转化率下降", detail: `环比下降 ${Math.abs(dashboard.value.comparison.conversion_rate.change_percent).toFixed(1)}%。`, link: "交易分析" })
  if (dashboard.value.summary.promotion_roi < 1 && dashboard.value.summary.promotion_plan_spend > 0) list.push({ level: "warning", title: "推广 ROI 低于 1", detail: `推广 ROI ${dashboard.value.summary.promotion_roi.toFixed(2)}x，推广花费 ${currency(dashboard.value.summary.promotion_plan_spend)}。`, link: "推广分析" })
  if (!list.length) list.push({ level: "positive", title: "暂无高优先级预警", detail: "数据覆盖、支付转化率和推广 ROI 未触发当前阈值。", link: "经营概览" })
  return list.slice(0, 3)
})
</script>

<template>
  <section class="business-page-heading operations-heading"><div><p>系统管理 / 操作中心</p><h1>操作中心</h1><span>经营预警与写操作安全状态</span></div><button class="capture-refresh" :disabled="loading" @click="loadSummary"><RefreshCw :size="16" :class="{ spinning: loading }" />刷新</button></section>
  <section v-if="loading && !summary" class="loading-panel"><LoaderCircle :size="28" class="spinning" /><span>正在读取工作台状态</span></section>
  <section v-else-if="error" class="error-panel"><FileLock2 :size="24" /><div><strong>工作台不可用</strong><p>{{ error }}</p></div><button @click="loadSummary">重试</button></section>
  <template v-else>
    <section v-if="dashboard" class="operations-health-grid"><article class="panel operations-health-card"><div class="operations-health-copy"><span>经营健康度</span><strong>{{ health.score }}</strong><em :class="`health-${health.tone}`"><CheckCircle2 v-if="health.tone === 'good'" :size="14" />{{ health.label }}</em><small>趋势 {{ model.trend.label }} · 覆盖 {{ dashboard.period.missing_dates.length ? "不完整" : "完整" }} · 转化 {{ ratio(dashboard.summary.conversion_rate) }}</small></div><div class="health-ring" :class="`ring-${health.tone}`" :style="{ '--health-angle': `${health.score * 3.6}deg` }"><div><b>{{ health.score }}</b><span>/ 100</span></div></div></article><article class="panel operations-latest-card"><div class="panel-heading"><div><p>最新有效日</p><h2>{{ latest?.stat_date || "暂无" }}</h2></div><Activity :size="18" /></div><div class="operations-latest-values"><div><span>支付金额</span><strong>{{ latest ? currency(latest.paid_amount) : "暂无" }}</strong></div><div><span>访客</span><strong>{{ latest ? number(latest.visitors) : "暂无" }}</strong></div><div><span>转化率</span><strong>{{ latest ? ratio(latest.conversion_rate) : "暂无" }}</strong></div></div></article></section>
    <section v-if="dashboard" class="panel operations-actions-panel"><div class="panel-heading"><div><p>经营预警</p><h2>当前状态</h2></div><span class="panel-action">最多 3 项</span></div><div class="operations-action-list"><article v-for="(action, index) in actions" :key="action.title" class="operations-action-row" :class="`action-${action.level}`"><span class="action-number">{{ String(index + 1).padStart(2, "0") }}</span><div><strong>{{ action.title }}</strong><p>{{ action.detail }}</p></div><span class="action-link">{{ action.link }} →</span></article></div></section>
    <section v-if="summary" class="operations-safety-grid"><article class="panel operations-safety-panel"><div class="panel-heading"><div><p>系统边界</p><h2>写操作安全状态</h2></div><ShieldCheck :size="18" /></div><div class="operations-mode"><strong>{{ summary.mode === "read_only" ? "只读模式" : "仅干跑模式" }}</strong><span>当前工作台只读取分析结果，不会直接修改平台数据。</span></div><div class="operation-flow"><span v-for="step in summary.required_flow" :key="step">{{ step }}</span></div></article><article class="panel operations-capability-panel"><div class="panel-heading"><div><p>能力清单</p><h2>当前可用状态</h2></div><Workflow :size="18" /></div><div class="operations-capability-list"><div v-for="item in summary.capabilities" :key="item.key"><div><strong>{{ item.title }}</strong><span>{{ item.risk_level }} 风险 · {{ item.mode }}</span></div><em :class="item.status === 'dry_run_only' ? 'capability-ready' : 'capability-planned'">{{ item.status === "dry_run_only" ? "可干跑" : "规划中" }}</em></div></div></article></section>
  </template>
</template>
