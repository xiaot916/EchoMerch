<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import {
  BarChart3,
  CircleDollarSign,
  Gauge,
  MousePointerClick,
  Package,
  ShieldCheck,
  Target,
  TrendingUp,
  UsersRound,
  Zap,
} from "lucide-vue-next"

import {
  fetchBigScreenPromotionRoi,
  fetchBigScreenSummary,
  fetchBigScreenTraffic,
  fetchBigScreenTrends,
} from "@/api"
import BusinessChart from "@/components/BusinessChart.vue"
import {
  baseCategoryAxis,
  baseValueAxis,
  chartPalette,
  withChartTheme,
} from "@/lib/echartsTheme"
import type { EChartsCoreOption } from "echarts/core"
import type {
  BigScreenPromoRoiItem,
  BigScreenSummary,
  BigScreenTrendPoint,
  BigScreenTrafficSource,
} from "@/types"
import { currency, number, ratio, shortDate } from "@/lib/format"

// ── 状态 ────────────────────────────────────────────────────
const summary = ref<BigScreenSummary>()
const trends = ref<BigScreenTrendPoint[]>([])
const trafficSources = ref<BigScreenTrafficSource[]>([])
const promoRoi = ref<BigScreenPromoRoiItem[]>([])
const loading = ref(true)
const error = ref("")

// ── 计算属性 ────────────────────────────────────────────────
const kpi = computed(() => summary.value?.kpi)
const dateLabel = computed(() =>
  summary.value ? `${shortDate(summary.value.range_start)} 至 ${shortDate(summary.value.range_end)}` : "加载中",
)
const growthFactor = computed(() => summary.value?.growth_factor)
const experienceScore = computed(() => summary.value?.experience_score)
const levelInfo = computed(() => summary.value?.level_info)

// 推广 ROI 颜色（涨红跌绿，遵循中国 A 股惯例）
const roiTone = (roiStr: string): string => {
  const roi = parseFloat(roiStr)
  if (isNaN(roi)) return "neutral"
  if (roi >= 1) return "up"
  if (roi >= 0.5) return "mid"
  return "down"
}

// ── 数据加载 ────────────────────────────────────────────────
onMounted(() => {
  const controller = new AbortController()
  const signal = controller.signal
  loading.value = true
  error.value = ""
  Promise.all([
    fetchBigScreenSummary(signal),
    fetchBigScreenTrends(signal),
    fetchBigScreenTraffic(signal),
    fetchBigScreenPromotionRoi(signal),
  ])
    .then(([summaryRes, trendsRes, trafficRes, promoRes]) => {
      if (signal.aborted) return
      summary.value = summaryRes
      trends.value = trendsRes.points
      trafficSources.value = trafficRes.sources
      promoRoi.value = promoRes.campaigns
    })
    .catch((e: unknown) => {
      if (signal.aborted) return
      error.value = e instanceof Error ? e.message : "加载数据失败"
    })
    .finally(() => {
      if (!signal.aborted) loading.value = false
    })
})

// ── 图表 option（经共享主题工厂统一风格）─────────────────────
const trendOption = computed<EChartsCoreOption>(() =>
  withChartTheme({
    legend: { bottom: 0, data: ["支付金额", "访客数", "推广花费", "推广成交"], textStyle: { color: "#718179", fontSize: 12 } },
    grid: { left: 56, right: 20, top: 24, bottom: 48 },
    xAxis: baseCategoryAxis({ data: trends.value.map((p) => shortDate(p.date)) }),
    yAxis: [
      baseValueAxis({
        name: "金额 (¥)",
        axisLabel: {
          color: "#849188",
          fontSize: 12,
          formatter: (v: number) => (v >= 10000 ? `${(v / 10000).toFixed(1)}万` : String(v)),
        },
      }),
      baseValueAxis({ name: "访客数", splitLine: { show: false } }),
    ],
    series: [
      {
        name: "支付金额",
        type: "bar",
        barMaxWidth: 18,
        yAxisIndex: 0,
        data: trends.value.map((p) => Number(p.paid_amount)),
        itemStyle: { color: "#16845b", borderRadius: [3, 3, 0, 0] },
      },
      {
        name: "推广花费",
        type: "bar",
        barMaxWidth: 18,
        yAxisIndex: 0,
        data: trends.value.map((p) => Number(p.promotion_cost)),
        itemStyle: { color: "#d0933b", borderRadius: [3, 3, 0, 0] },
      },
      {
        name: "推广成交",
        type: "bar",
        barMaxWidth: 18,
        yAxisIndex: 0,
        data: trends.value.map((p) => Number(p.promotion_paid_amount)),
        itemStyle: { color: "#c76d59", borderRadius: [3, 3, 0, 0] },
      },
      {
        name: "访客数",
        type: "line",
        yAxisIndex: 1,
        smooth: true,
        symbol: "circle",
        symbolSize: 4,
        lineStyle: { width: 2, color: "#4f7fd1" },
        itemStyle: { color: "#4f7fd1" },
        data: trends.value.map((p) => p.visitors),
      },
    ],
  }),
)

const trafficPieOption = computed<EChartsCoreOption>(() =>
  withChartTheme({
    tooltip: {
      trigger: "item",
      formatter: (params: { name: string; value: number; percent: number }) =>
        `${params.name}<br/>支付金额 ${currency(params.value)}<br/>占比 ${params.percent.toFixed(1)}%`,
    },
    series: [
      {
        type: "pie",
        radius: ["38%", "68%"],
        center: ["50%", "46%"],
        avoidLabelOverlap: true,
        label: {
          color: "#506158",
          fontSize: 12,
          formatter: (params: { name: string; percent: number }) =>
            `${params.name} ${params.percent.toFixed(1)}%`,
        },
        labelLine: { length: 10, length2: 6, lineStyle: { color: "#bcc9c1" } },
        data: trafficSources.value.map((s, i) => ({
          name: s.name,
          value: Number(s.paid_amount),
          itemStyle: { color: chartPalette[i % chartPalette.length] },
        })),
      },
    ],
  }),
)

// ── KPI 卡片配置 ─────────────────────────────────────────────
const kpiCards = computed(() => {
  if (!kpi.value) return []
  return [
    {
      label: "支付金额",
      value: currency(Number(kpi.value.paid_amount)),
      sub: `净 ${currency(Number(kpi.value.net_paid_amount))}`,
      icon: CircleDollarSign,
      accent: "#16845b",
    },
    {
      label: "访客数",
      value: number(kpi.value.visitors),
      sub: `买家 ${number(kpi.value.buyers)} · 转化率 ${ratio(Number(kpi.value.conversion_rate))}`,
      icon: MousePointerClick,
      accent: "#4f7fd1",
    },
    {
      label: "推广花费",
      value: currency(Number(kpi.value.promotion_cost)),
      sub: `推广成交 ${currency(Number(kpi.value.promotion_paid_amount))}`,
      icon: Target,
      accent: "#d0933b",
    },
    {
      label: "推广 ROI",
      value: kpi.value.promotion_roi,
      sub: Number(kpi.value.promotion_roi) >= 1 ? "高于盈亏线" : "低于盈亏线",
      icon: TrendingUp,
      accent: Number(kpi.value.promotion_roi) >= 1 ? "#27ae60" : "#c0392b",
      tone: roiTone(kpi.value.promotion_roi),
    },
  ]
})

const scoreLabels: Array<{ key: keyof NonNullable<BigScreenSummary["growth_factor"]>; label: string }> = [
  { key: "transaction_score", label: "交易分" },
  { key: "traffic_score", label: "流量分" },
  { key: "item_score", label: "商品分" },
  { key: "marketing_score", label: "营销分" },
  { key: "service_score", label: "服务分" },
]

const expLabels: Array<{ key: keyof NonNullable<BigScreenSummary["experience_score"]>; label: string }> = [
  { key: "total_score", label: "体验总分" },
  { key: "item_score", label: "商品" },
  { key: "logistics_score", label: "物流" },
  { key: "service_score", label: "服务" },
  { key: "refund_score", label: "退款" },
  { key: "dispute_score", label: "纠纷" },
]

function scoreTone(value: string | null): string {
  if (!value) return "neutral"
  const n = parseFloat(value)
  if (isNaN(n)) return "neutral"
  if (n >= 80) return "good"
  if (n >= 60) return "warn"
  return "bad"
}
</script>

<template>
  <div class="big-screen">
    <!-- 顶部栏 -->
    <header class="big-screen-header">
      <div>
        <h1>经营大屏</h1>
        <p>{{ dateLabel }} · 近 {{ summary?.days ?? "—" }} 天</p>
      </div>
      <div v-if="loading" class="big-screen-state loading"><Zap /> 加载中…</div>
      <div v-else-if="error" class="big-screen-state error">{{ error }}</div>
    </header>

    <!-- KPI 卡片行 -->
    <section class="big-screen-kpis">
      <article
        v-for="card in kpiCards"
        :key="card.label"
        class="big-screen-kpi"
        :style="{ borderLeftColor: card.accent }"
      >
        <div class="big-screen-kpi-head">
          <span>{{ card.label }}</span>
          <component :is="card.icon" class="big-screen-kpi-icon" />
        </div>
        <strong :class="`tone-${card.tone || 'neutral'}`">{{ card.value }}</strong>
        <small>{{ card.sub }}</small>
      </article>
    </section>

    <!-- 中间：趋势图 + 流量结构 -->
    <section class="big-screen-mid">
      <article class="big-screen-panel span-2">
        <div class="big-screen-panel-head">
          <BarChart3 class="big-screen-panel-icon" />
          <span>经营趋势</span>
        </div>
        <BusinessChart v-if="trends.length" :option="trendOption" ariaLabel="经营趋势：支付金额、访客数、推广花费与推广成交的日趋势图" :height="256" />
        <div v-else class="big-screen-empty">暂无趋势数据</div>
      </article>

      <article class="big-screen-panel">
        <div class="big-screen-panel-head">
          <Package class="big-screen-panel-icon" />
          <span>流量来源结构</span>
        </div>
        <BusinessChart v-if="trafficSources.length" :option="trafficPieOption" ariaLabel="流量来源结构：按支付金额占比的环形图" :height="256" />
        <div v-else class="big-screen-empty">暂无流量数据</div>
      </article>
    </section>

    <!-- 底部：评分 + 推广 ROI 排行 -->
    <section class="big-screen-bottom">
      <article class="big-screen-panel">
        <div class="big-screen-panel-head">
          <Gauge class="big-screen-panel-icon" />
          <span>增长因子评分</span>
        </div>
        <ul class="big-screen-scores">
          <li v-for="item in scoreLabels" :key="item.key">
            <span>{{ item.label }}</span>
            <strong :class="`score-${scoreTone((growthFactor as any)?.[item.key])}`">
              {{ (growthFactor as any)?.[item.key] ?? "—" }}
            </strong>
          </li>
        </ul>
      </article>

      <article class="big-screen-panel">
        <div class="big-screen-panel-head">
          <ShieldCheck class="big-screen-panel-icon" />
          <span>体验分</span>
        </div>
        <ul class="big-screen-scores">
          <li v-for="item in expLabels" :key="item.key">
            <span>{{ item.label }}</span>
            <strong :class="`score-${scoreTone((experienceScore as any)?.[item.key])}`">
              {{ (experienceScore as any)?.[item.key] ?? "—" }}
            </strong>
          </li>
        </ul>
        <div v-if="levelInfo" class="big-screen-level">
          <div><span>层级</span><strong>{{ levelInfo.level || "—" }}</strong></div>
          <div><span>排名百分位</span><strong>{{ levelInfo.rank_percentile || "—" }}</strong></div>
        </div>
      </article>

      <article class="big-screen-panel">
        <div class="big-screen-panel-head">
          <UsersRound class="big-screen-panel-icon" />
          <span>推广计划 ROI Top 10</span>
        </div>
        <div class="big-screen-roi-table">
          <table>
            <thead>
              <tr>
                <th class="align-left">计划</th>
                <th>花费</th>
                <th>成交</th>
                <th>ROI</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in promoRoi" :key="item.campaign_id">
                <td class="align-left" :title="item.campaign_name">{{ item.campaign_name }}</td>
                <td>{{ currency(Number(item.spend)) }}</td>
                <td>{{ currency(Number(item.paid_amount)) }}</td>
                <td :class="`tone-${roiTone(item.roi)}`"><b>{{ item.roi }}</b></td>
              </tr>
              <tr v-if="!promoRoi.length">
                <td colspan="4" class="big-screen-empty-cell">暂无推广数据</td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>
    </section>
  </div>
</template>

<style scoped>
.big-screen { display: grid; gap: var(--space-4); }

.big-screen-header { display: flex; align-items: center; justify-content: space-between; gap: var(--space-4); }
.big-screen-header h1 { margin: 0; color: var(--text); font-size: var(--font-size-xl); font-weight: 700; }
.big-screen-header p { margin: 2px 0 0; color: var(--text-subtle); font-size: var(--font-size-xs); }
.big-screen-state { display: flex; align-items: center; gap: var(--space-2); color: var(--text-subtle); font-size: var(--font-size-sm); }
.big-screen-state.error { color: var(--danger); }
.big-screen-state.loading svg { animation: big-screen-pulse 1.2s ease-in-out infinite; }
@keyframes big-screen-pulse { 50% { opacity: .35; } }

.big-screen-kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--space-3); }
.big-screen-kpi { display: grid; gap: var(--space-1); border: 1px solid var(--line); border-left: 4px solid var(--accent); border-radius: var(--radius-lg); padding: var(--space-4); background: var(--surface); box-shadow: var(--shadow-sm); }
.big-screen-kpi-head { display: flex; align-items: center; justify-content: space-between; color: var(--text-muted); font-size: var(--font-size-xs); }
.big-screen-kpi-icon { width: 16px; height: 16px; color: var(--text-subtle); }
.big-screen-kpi strong { color: var(--text); font-size: var(--font-size-xl); font-weight: 700; font-variant-numeric: tabular-nums; }
.big-screen-kpi small { color: var(--text-subtle); font-size: var(--font-size-xs); }
.big-screen-kpi .tone-up { color: #c0392b; }
.big-screen-kpi .tone-mid { color: var(--warning); }
.big-screen-kpi .tone-down { color: #27ae60; }

.big-screen-mid { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); gap: var(--space-4); }
.big-screen-bottom { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--space-4); }
.big-screen-panel { border: 1px solid var(--line); border-radius: var(--radius-lg); padding: var(--space-4); background: var(--surface); box-shadow: var(--shadow-sm); }
.big-screen-panel.span-2 { grid-column: span 2; }
.big-screen-panel-head { display: flex; align-items: center; gap: var(--space-2); margin-bottom: var(--space-2); color: var(--text); font-size: var(--font-size-sm); font-weight: 600; }
.big-screen-panel-icon { width: 16px; height: 16px; color: var(--text-subtle); }
.big-screen-empty { display: flex; align-items: center; justify-content: center; height: 256px; color: var(--text-subtle); font-size: var(--font-size-xs); }

.big-screen-scores { display: grid; gap: var(--space-2); margin: 0; padding: 0; list-style: none; }
.big-screen-scores li { display: flex; align-items: center; justify-content: space-between; font-size: var(--font-size-xs); }
.big-screen-scores li > span { color: var(--text-muted); }
.big-screen-scores strong { display: inline-flex; align-items: center; justify-content: center; min-width: 56px; padding: 2px var(--space-2); border-radius: var(--radius-sm); font-weight: 600; font-variant-numeric: tabular-nums; }
.big-screen-scores .score-good { color: var(--positive); background: var(--accent-soft); }
.big-screen-scores .score-warn { color: var(--warning); background: #fdf3e3; }
.big-screen-scores .score-bad { color: var(--danger); background: #fbecec; }
.big-screen-scores .score-neutral { color: var(--text-subtle); background: var(--canvas); }

.big-screen-level { display: grid; gap: var(--space-1); margin-top: var(--space-3); border-top: 1px solid var(--line); padding-top: var(--space-3); }
.big-screen-level > div { display: flex; align-items: center; justify-content: space-between; color: var(--text-muted); font-size: var(--font-size-xs); }
.big-screen-level strong { color: var(--text); font-weight: 600; }

.big-screen-roi-table { max-height: 240px; overflow-y: auto; }
.big-screen-roi-table table { width: 100%; border-collapse: collapse; font-size: var(--font-size-xs); }
.big-screen-roi-table th { border-bottom: 1px solid var(--line); padding: var(--space-1) 0; color: var(--text-subtle); font-weight: 500; text-align: right; }
.big-screen-roi-table td { border-bottom: 1px solid var(--canvas); padding: 6px 0; color: var(--text-muted); text-align: right; font-variant-numeric: tabular-nums; }
.big-screen-roi-table .align-left { text-align: left; }
.big-screen-roi-table td.align-left { max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text); }
.big-screen-roi-table .tone-up b { color: #c0392b; }
.big-screen-roi-table .tone-mid b { color: var(--warning); }
.big-screen-roi-table .tone-down b { color: #27ae60; }
.big-screen-empty-cell { padding: var(--space-6) 0; color: var(--text-subtle); text-align: center; }

@media (max-width: 1080px) {
  .big-screen-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .big-screen-mid { grid-template-columns: minmax(0, 1fr); }
  .big-screen-panel.span-2 { grid-column: auto; }
  .big-screen-bottom { grid-template-columns: minmax(0, 1fr); }
}

@media (max-width: 640px) {
  .big-screen-kpis { grid-template-columns: minmax(0, 1fr); }
}
</style>
