<script setup lang="ts">
import { computed, ref } from "vue"
import { CheckCircle2, ChevronDown, CircleAlert, CircleDashed, Database } from "lucide-vue-next"

import { useDashboard } from "@/composables/useDashboard"
import { shortDate } from "@/lib/format"
import type { DataCoverage } from "@/types"

const { dashboard } = useDashboard()
const expanded = ref(false)

const coverageRows = computed<DataCoverage[]>(() => dashboard.value?.coverage ?? [])
const latestDate = computed(() =>
  coverageRows.value.reduce((latest, item) =>
    (item.latest_date ?? "") > latest ? (item.latest_date ?? "") : latest,
  dashboard.value?.range_end || ""),
)
const counts = computed(() => {
  const rows = coverageRows.value
  return {
    complete: rows.filter((item) => item.status === "complete").length,
    partial: rows.filter((item) => item.status === "partial").length,
    empty: rows.filter((item) => item.status === "empty").length,
    total: rows.length,
  }
})
const hasIssues = computed(() => counts.value.partial > 0 || counts.value.empty > 0)
const overallTone = computed(() => {
  if (!counts.value.total) return "unknown"
  if (counts.value.empty > 0) return "danger"
  if (counts.value.partial > 0) return "warning"
  return "ok"
})
const headline = computed(() => {
  if (!counts.value.total) return "数据覆盖状态未知"
  if (!hasIssues.value) return `全部 ${counts.value.total} 个数据集覆盖完整`
  const parts: string[] = []
  if (counts.value.partial) parts.push(`${counts.value.partial} 个覆盖不完整`)
  if (counts.value.empty) parts.push(`${counts.value.empty} 个无数据`)
  return parts.join("、")
})

function missingLabel(item: DataCoverage): string {
  const missing = item.missing_dates?.length ?? 0
  const noData = item.no_data_dates?.length ?? 0
  const bits: string[] = []
  if (missing) bits.push(`缺 ${missing} 天`)
  if (noData) bits.push(`${noData} 天无数据`)
  return bits.join(" · ") || "—"
}

function statusIcon(status: DataCoverage["status"]) {
  if (status === "complete") return CheckCircle2
  if (status === "partial") return CircleAlert
  return CircleDashed
}
</script>

<template>
  <section
    v-if="coverageRows.length"
    class="freshness-strip"
    :class="`freshness-${overallTone}`"
    :aria-label="`数据新鲜度：${headline}`"
  >
    <button type="button" class="freshness-summary" @click="expanded = !expanded">
      <Database :size="15" class="freshness-icon" />
      <strong>数据最新至 {{ shortDate(latestDate) }}</strong>
      <span class="freshness-detail" :class="{ 'has-issues': hasIssues }">{{ headline }}</span>
      <span v-if="!hasIssues" class="freshness-ok-range">
        {{ dashboard?.period.covered_days ?? "—" }}/{{ dashboard?.period.expected_days ?? "—" }} 天
      </span>
      <ChevronDown :size="15" class="freshness-chevron" :class="{ open: expanded }" />
    </button>

    <div v-if="expanded" class="freshness-list">
      <div v-for="item in coverageRows" :key="item.dataset" class="freshness-row" :class="`row-${item.status}`">
        <component :is="statusIcon(item.status)" :size="14" class="freshness-row-icon" />
        <span class="freshness-row-name">{{ item.dataset }}</span>
        <span class="freshness-row-days">{{ item.covered_days }}/{{ item.expected_days }} 天</span>
        <span class="freshness-row-latest">最新 {{ item.latest_date ? shortDate(item.latest_date) : "—" }}</span>
        <span v-if="item.status !== 'complete'" class="freshness-row-missing">{{ missingLabel(item) }}</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.freshness-strip { border: 1px solid var(--line); border-radius: var(--radius-md); background: var(--surface); box-shadow: var(--shadow-sm); overflow: hidden; }
.freshness-summary { display: flex; align-items: center; gap: var(--space-2); width: 100%; border: 0; padding: var(--space-2) var(--space-3); color: var(--text-muted); background: transparent; font-size: var(--font-size-xs); text-align: left; cursor: pointer; }
.freshness-summary:hover { background: var(--canvas); }
.freshness-summary strong { color: var(--text); font-weight: 600; white-space: nowrap; }
.freshness-icon { flex: 0 0 auto; color: var(--text-subtle); }
.freshness-ok .freshness-icon { color: var(--positive); }
.freshness-warning .freshness-icon { color: var(--warning); }
.freshness-danger .freshness-icon { color: var(--danger); }
.freshness-detail { color: var(--text-subtle); }
.freshness-detail.has-issues { color: var(--warning); }
.freshness-danger .freshness-detail.has-issues { color: var(--danger); }
.freshness-ok-range { margin-left: auto; color: var(--text-subtle); font-variant-numeric: tabular-nums; }
.freshness-chevron { color: var(--text-subtle); transition: transform .15s ease; }
.freshness-chevron.open { transform: rotate(180deg); }

.freshness-list { display: grid; border-top: 1px solid var(--line); padding: var(--space-2) var(--space-3) var(--space-3); gap: var(--space-1); }
.freshness-row { display: grid; grid-template-columns: 16px minmax(120px, 1.4fr) auto auto minmax(0, 1fr); align-items: center; gap: var(--space-2); padding: 3px 0; font-size: var(--font-size-xs); }
.freshness-row-icon { justify-self: center; }
.row-complete .freshness-row-icon { color: var(--positive); }
.row-partial .freshness-row-icon { color: var(--warning); }
.row-empty .freshness-row-icon { color: var(--danger); }
.freshness-row-name { color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.freshness-row-days, .freshness-row-latest { color: var(--text-muted); font-variant-numeric: tabular-nums; white-space: nowrap; }
.freshness-row-missing { color: var(--text-subtle); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

@media (max-width: 760px) {
  .freshness-row { grid-template-columns: 16px minmax(0, 1fr) auto; }
  .freshness-row-latest, .freshness-row-missing { display: none; }
  .freshness-ok-range { display: none; }
}
</style>
