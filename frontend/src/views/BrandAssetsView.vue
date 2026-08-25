<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import { BarChart3, LoaderCircle, RefreshCw, ShieldCheck, UsersRound } from "lucide-vue-next"

import BusinessChart from "@/components/BusinessChart.vue"
import EmptyState from "@/components/EmptyState.vue"
import { fetchBrandAssetSummary, fetchBrandAssetsBrands } from "@/api"
import type { BrandAssetSummary, BrandRecord } from "@/types"
import { currency, number } from "@/lib/format"

const brands = ref<BrandRecord[]>([])
const summary = ref<BrandAssetSummary | null>(null)
const selectedBrandId = ref("")
const endDate = ref(new Date(Date.now() - 86400000).toISOString().slice(0, 10))
const startDate = ref(new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10))
const loading = ref(true)
const refreshing = ref(false)
const error = ref("")

const hasBrand = computed(() => brands.value.length > 0)
const latestDay = computed(() => summary.value?.latest_day || "--")
const latestDimensions = computed(() => summary.value?.dimensions || [])
const channelRows = computed(() => latestDimensions.value.filter((row) => row["维度类型"] === "channel"))
const touchRows = computed(() => latestDimensions.value
  .filter((row) => row["维度类型"] === "touch")
  .sort((left, right) => metricNumber(right["成交金额"]) - metricNumber(left["成交金额"]))
  .slice(0, 6))

function metricNumber(value: unknown): number {
  if (value === null || value === undefined || value === "") return 0
  const parsed = Number(String(value).replace(/,/g, "").replace(/%$/, ""))
  return Number.isFinite(parsed) ? parsed : 0
}

function displayNumber(value: unknown): string {
  return value === null || value === undefined || value === "" ? "--" : number(metricNumber(value))
}

function displayCurrency(value: unknown): string {
  return value === null || value === undefined || value === "" ? "--" : currency(metricNumber(value))
}

function displayPercent(value: unknown): string {
  if (value === null || value === undefined || value === "") return "--"
  return `${(metricNumber(value) * 100).toFixed(2)}%`
}

const kpis = computed(() => {
  const overview = summary.value?.overview || {}
  return [
    { label: "消费者数", value: displayNumber(overview["消费者数"]), detail: "最新统计日", icon: UsersRound },
    { label: "成交金额", value: displayCurrency(overview["成交金额"]), detail: "最新统计日", icon: BarChart3 },
    { label: "成交人数", value: displayNumber(overview["成交人数"]), detail: "最新统计日", icon: UsersRound },
    { label: "会员成交金额", value: displayCurrency(overview["会员成交金额"]), detail: "最新统计日", icon: BarChart3 },
  ]
})

const trendOption = computed(() => {
  const rows = summary.value?.overview_trend || []
  return {
    color: ["#5b8def", "#35a979"],
    tooltip: { trigger: "axis", valueFormatter: (value: number) => number(Number(value)) },
    legend: { bottom: 0, data: ["消费者数", "成交金额"], textStyle: { color: "#718179", fontSize: 11 } },
    grid: { left: 64, right: 68, top: 24, bottom: 48 },
    xAxis: { type: "category", data: rows.map((row) => String(row["业务日期"] || "").slice(5)), boundaryGap: false, axisLabel: { color: "#829188" } },
    yAxis: [
      { type: "value", name: "消费者", axisLabel: { formatter: (value: number) => number(value), color: "#829188" }, splitLine: { lineStyle: { color: "#edf1ef" } } },
      { type: "value", name: "金额", axisLabel: { formatter: (value: number) => `¥${number(value)}`, color: "#829188" }, splitLine: { show: false } },
    ],
    series: [
      { name: "消费者数", type: "line", yAxisIndex: 0, smooth: true, showSymbol: false, data: rows.map((row) => metricNumber(row["消费者数"])) },
      { name: "成交金额", type: "line", yAxisIndex: 1, smooth: true, showSymbol: false, data: rows.map((row) => metricNumber(row["成交金额"])) },
    ],
  }
})

const stageChart = computed(() => {
  const rows = [...(summary.value?.stages || [])].sort((left, right) => metricNumber(right["消费者数"]) - metricNumber(left["消费者数"]))
  return {
    color: ["#35a979"],
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (value: number) => number(Number(value)) },
    grid: { left: 92, right: 28, top: 20, bottom: 28 },
    xAxis: { type: "value", splitLine: { lineStyle: { color: "#edf1ef" } } },
    yAxis: { type: "category", data: rows.map((row) => row["资产阶段名称"] || "--").reverse() },
    series: [{ name: "消费者数", type: "bar", barMaxWidth: 22, data: rows.map((row) => metricNumber(row["消费者数"])).reverse() }],
  }
})

const channelChart = computed(() => {
  const rows = [...channelRows.value].sort((left, right) => metricNumber(right["成交金额"]) - metricNumber(left["成交金额"]))
  return {
    color: ["#5b8def"],
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (value: number) => currency(Number(value)) },
    grid: { left: 92, right: 28, top: 20, bottom: 28 },
    xAxis: { type: "value", splitLine: { lineStyle: { color: "#edf1ef" } } },
    yAxis: { type: "category", data: rows.map((row) => row["维度名称"] || "--").reverse() },
    series: [{ name: "成交金额", type: "bar", barMaxWidth: 22, data: rows.map((row) => metricNumber(row["成交金额"])).reverse() }],
  }
})

function errorText(value: unknown): string {
  return value instanceof Error ? value.message : "品牌资产数据读取失败。"
}

async function loadSummary(): Promise<void> {
  if (!selectedBrandId.value) {
    summary.value = null
    return
  }
  refreshing.value = true
  error.value = ""
  try {
    summary.value = await fetchBrandAssetSummary(selectedBrandId.value, startDate.value, endDate.value)
  } catch (requestError) {
    summary.value = null
    error.value = errorText(requestError)
  } finally {
    refreshing.value = false
  }
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ""
  try {
    brands.value = await fetchBrandAssetsBrands()
    selectedBrandId.value = selectedBrandId.value || brands.value[0]?.brand_id || ""
    await loadSummary()
  } catch (requestError) {
    error.value = errorText(requestError)
  } finally {
    loading.value = false
  }
}

watch(selectedBrandId, () => { if (!loading.value) void loadSummary() })
onMounted(() => { void load() })
</script>

<template>
  <section class="brand-assets-page">
    <header class="brand-assets-heading">
      <div><h1>品牌资产</h1><span v-if="summary">{{ summary.brand.brand_name }} · 数据截止 {{ latestDay }}</span></div>
      <button class="brand-refresh" type="button" :disabled="loading || refreshing" @click="load"><RefreshCw :size="16" :class="{ spinning: loading || refreshing }" />刷新</button>
    </header>

    <section class="brand-assets-toolbar" aria-label="品牌资产筛选">
      <label><span>品牌</span><select v-model="selectedBrandId" :disabled="!hasBrand"><option value="">请选择品牌</option><option v-for="brand in brands" :key="brand.brand_id" :value="brand.brand_id">{{ brand.brand_name }}</option></select></label>
      <label><span>开始日期</span><input v-model="startDate" type="date" /></label>
      <label><span>结束日期</span><input v-model="endDate" type="date" /></label>
      <button class="brand-query" type="button" :disabled="!selectedBrandId || refreshing" @click="loadSummary"><BarChart3 :size="16" />查询</button>
    </section>

    <section v-if="loading" class="brand-loading"><LoaderCircle :size="24" class="spinning" /><span>正在读取…</span></section>
    <section v-else-if="error" class="brand-error"><ShieldCheck :size="22" /><div><strong>页面暂不可用</strong><p>{{ error }}</p></div><button type="button" @click="load">重试</button></section>
    <section v-else-if="!hasBrand" class="brand-empty-panel"><div><strong>暂无品牌数据</strong><p>导入品牌资产数据后，此处会显示对应品牌的资产和成交数据。</p></div></section>

    <template v-else-if="summary">
      <section v-if="summary.data_status !== 'available'" class="brand-empty-panel"><div><strong>当前筛选范围暂无数据</strong><p>请调整日期范围后重试。</p></div></section>
      <template v-else>
        <section class="brand-kpi-grid"><article v-for="item in kpis" :key="item.label"><component :is="item.icon" :size="17" /><span>{{ item.label }}</span><strong>{{ item.value }}</strong><small>{{ item.detail }} · {{ latestDay }}</small></article></section>

        <section class="brand-analysis-grid">
          <article class="brand-panel"><header><h2>消费者与成交趋势</h2><span>{{ summary.start_date }} 至 {{ summary.end_date }}</span></header><BusinessChart v-if="summary.overview_trend.length" :option="trendOption" ariaLabel="品牌消费者与成交金额趋势图" :height="320" /><EmptyState v-else title="暂无趋势数据" detail="当前日期范围没有品牌概览记录。" /></article>
          <article class="brand-panel"><header><h2>消费者分层</h2><span>{{ latestDay }}</span></header><BusinessChart v-if="summary.stages.length" :option="stageChart" ariaLabel="品牌消费者分层图" :height="320" /><EmptyState v-else title="暂无分层数据" detail="当前日期范围没有消费者分层记录。" /></article>
        </section>

        <section class="brand-analysis-grid">
          <article class="brand-panel"><header><h2>成交渠道</h2><span>{{ latestDay }}</span></header><BusinessChart v-if="channelRows.length" :option="channelChart" ariaLabel="品牌成交渠道图" :height="280" /><EmptyState v-else title="暂无渠道数据" detail="当前日期范围没有渠道成交记录。" /></article>
          <article class="brand-panel"><header><h2>主要触点</h2><span>按成交金额排序</span></header><div v-if="touchRows.length" class="touch-table"><div class="touch-row touch-head"><span>触点</span><span>成交人数</span><span>成交金额</span></div><div v-for="row in touchRows" :key="String(row['维度编码'])" class="touch-row"><strong>{{ row["维度名称"] || "--" }}</strong><span>{{ displayNumber(row["成交人数"]) }}</span><em>{{ displayCurrency(row["成交金额"]) }}</em></div></div><EmptyState v-else title="暂无触点数据" detail="当前日期范围没有触点成交记录。" /></article>
        </section>

        <section class="brand-stage-table-panel">
          <header><h2>分层明细</h2><span>最新统计日</span></header>
          <div class="stage-table"><div class="stage-row stage-head"><span>人群</span><span>消费者数</span><span>占比</span><span>成交人数</span><span>成交金额</span></div><div v-for="row in summary.stages" :key="String(row['资产阶段编码'])" class="stage-row"><strong>{{ row["资产阶段名称"] || "--" }}</strong><span>{{ displayNumber(row["消费者数"]) }}</span><span>{{ displayPercent(row["消费者占比"]) }}</span><span>{{ displayNumber(row["成交人数"]) }}</span><em>{{ displayCurrency(row["成交金额"]) }}</em></div></div>
        </section>
      </template>
    </template>
  </section>
</template>

<style scoped>
.brand-assets-page { display: grid; gap: 16px; padding: 4px 2px 28px; color: #263b30; }
.brand-assets-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; }
.brand-assets-heading h1 { margin: 0; color: #20342a; font-size: 24px; font-weight: 750; }
.brand-assets-heading span { display: block; margin-top: 7px; color: #7e8e85; font-size: 12px; }
.brand-refresh, .brand-query { display: inline-flex; align-items: center; justify-content: center; gap: 7px; min-height: 34px; border: 1px solid #bedaca; border-radius: 5px; padding: 0 13px; color: #176b4b; background: #eff9f3; font-size: 12px; font-weight: 650; cursor: pointer; }
.brand-refresh:disabled, .brand-query:disabled { cursor: not-allowed; opacity: .55; }
.brand-assets-toolbar { display: flex; align-items: flex-end; gap: 12px; padding: 13px 15px; border: 1px solid #dce8e1; border-radius: 6px; background: #fff; }
.brand-assets-toolbar label { display: grid; gap: 6px; min-width: 170px; }
.brand-assets-toolbar label span { color: #73837a; font-size: 11px; }
.brand-assets-toolbar select, .brand-assets-toolbar input { min-height: 34px; border: 1px solid #ccdcd2; border-radius: 4px; padding: 0 10px; color: #32483d; background: #fbfdfc; font: inherit; font-size: 12px; }
.brand-query { margin-left: auto; color: #fff; border-color: #237b58; background: #237b58; }
.brand-loading, .brand-error, .brand-empty-panel { display: flex; align-items: center; gap: 14px; min-height: 112px; border: 1px solid #dce8e1; border-radius: 6px; padding: 22px; background: #fff; }
.brand-loading { justify-content: center; color: #6f8176; }
.brand-error { border-color: #ebcccc; color: #a44d4d; background: #fffafa; }
.brand-error p, .brand-empty-panel p { margin: 5px 0 0; color: #7f8c84; font-size: 12px; line-height: 1.55; }
.brand-error button { margin-left: auto; border: 0; color: #176b4b; background: transparent; font-weight: 650; cursor: pointer; }
.brand-empty-panel strong { color: #30473a; font-size: 15px; }
.brand-kpi-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 1px; overflow: hidden; border: 1px solid #dce8e1; border-radius: 6px; background: #dce8e1; }
.brand-kpi-grid article { display: grid; grid-template-columns: auto 1fr; align-items: center; column-gap: 8px; min-height: 92px; padding: 13px 15px; background: #fff; }
.brand-kpi-grid svg { grid-row: span 2; color: #21845f; }
.brand-kpi-grid span { color: #7a8b81; font-size: 11px; }
.brand-kpi-grid strong { color: #30473a; font-size: 20px; line-height: 1.2; }
.brand-kpi-grid small { grid-column: 2; color: #9aa69f; font-size: 10px; }
.brand-analysis-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.brand-panel, .brand-stage-table-panel { overflow: hidden; border: 1px solid #dce8e1; border-radius: 6px; background: #fff; }
.brand-panel > header, .brand-stage-table-panel > header { display: flex; min-height: 58px; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 16px; border-bottom: 1px solid #e9efeb; }
.brand-panel h2, .brand-stage-table-panel h2 { margin: 0; color: #263b30; font-size: 16px; }
.brand-panel header span, .brand-stage-table-panel header span { color: #899a90; font-size: 11px; }
.touch-table, .stage-table { display: grid; }
.touch-row, .stage-row { display: grid; align-items: center; min-height: 46px; padding: 0 16px; border-bottom: 1px solid #edf2ee; color: #53655c; font-size: 12px; }
.touch-row { grid-template-columns: minmax(0, 1fr) 100px 120px; }
.stage-row { grid-template-columns: minmax(0, 1.2fr) repeat(3, minmax(90px, .8fr)) minmax(120px, 1fr); }
.touch-row:last-child, .stage-row:last-child { border-bottom: 0; }
.touch-row strong, .stage-row strong { color: #34483d; font-weight: 650; }
.touch-row em, .stage-row em { color: #176b4b; font-style: normal; font-weight: 650; }
.touch-head, .stage-head { min-height: 38px; color: #8a988f; background: #fbfdfc; font-size: 11px; }
@media (max-width: 900px) { .brand-assets-heading, .brand-assets-toolbar { align-items: stretch; flex-direction: column; } .brand-query { margin-left: 0; } .brand-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .brand-analysis-grid { grid-template-columns: 1fr; } }
@media (max-width: 620px) { .brand-kpi-grid { grid-template-columns: 1fr; } .brand-assets-toolbar label { min-width: 0; } .stage-table { overflow-x: auto; } .stage-row { min-width: 610px; } .touch-row { grid-template-columns: minmax(0, 1fr) 80px 100px; } }
</style>
