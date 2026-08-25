<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { Activity, AlertTriangle, ArrowDownRight, BarChart3, Database, Eye, KeyRound, Lightbulb, RefreshCw, Search, ShieldCheck, TrendingDown, TrendingUp } from "lucide-vue-next"
import BusinessChart from "@/components/BusinessChart.vue"
import EmptyState from "@/components/EmptyState.vue"
import { fetchMarketInsights } from "@/api"
import type { MarketCompetitiveSignal, MarketDemandSignal, MarketInsightResponse, MarketRanking } from "@/types"

const snapshot = ref<MarketInsightResponse | null>(null)
const loading = ref(false)
const error = ref("")
const startDate = ref("")
const endDate = ref("")
const rankType = ref<"all" | "shop" | "item" | "content">("all")
const keywordType = ref<"all" | "core" | "search" | "trend" | "modify">("all")
const query = ref("")
const rankTypeLabel: Record<string, string> = { shop: "店铺", item: "商品", content: "内容" }
const keywordTypeLabel: Record<string, string> = { core: "核心词", search: "搜索词", trend: "趋势词", modify: "修饰词" }

async function load(): Promise<void> {
  loading.value = true; error.value = ""
  try {
    snapshot.value = await fetchMarketInsights({ startDate: startDate.value || undefined, endDate: endDate.value || undefined, rankType: rankType.value, keywordType: keywordType.value, query: query.value.trim() || undefined, limit: 100 })
    if (!startDate.value) startDate.value = snapshot.value.range_start
    if (!endDate.value) endDate.value = snapshot.value.range_end
  } catch (cause) { error.value = cause instanceof Error ? cause.message : "市场洞察暂不可用" } finally { loading.value = false }
}
function applyFilters(): void { void load() }
function number(value: number | null | undefined): string { return value == null ? "暂无" : new Intl.NumberFormat("zh-CN").format(value) }
function percent(value: number | null | undefined): string { return value == null ? "暂无" : `${value.toFixed(1)}%` }
function cleanText(value: string | null | undefined): string { return value || "暂无名称" }
function rankingTitle(item: MarketRanking): string { return cleanText(item.rank_type === "shop" ? item.shop_name : item.content_title || item.entity_name) }
function rankChange(item: MarketRanking): string { if (item.rank_change == null) return "暂无变化"; if (item.rank_change === 0) return "排名不变"; return item.rank_change > 0 ? `上升 ${item.rank_change} 位` : `下降 ${Math.abs(item.rank_change)} 位` }
function directionLabel(item: MarketDemandSignal): string { if (item.direction === "rising") return `上升 ${item.rank_change || 0} 位`; if (item.direction === "falling") return `下降 ${Math.abs(item.rank_change || 0)} 位`; if (item.direction === "new") return "新进入样本"; return "排名稳定" }

const risingTotal = computed(() => Object.values(snapshot.value?.summary.rising_counts || {}).reduce((total, value) => total + value, 0))
const fallingTotal = computed(() => Object.values(snapshot.value?.summary.falling_counts || {}).reduce((total, value) => total + value, 0))
const coverageText = computed(() => snapshot.value ? `${snapshot.value.range_start} 至 ${snapshot.value.range_end}` : "")
const overallConfidence = computed(() => {
  if (!snapshot.value) return { label: "暂无", detail: "等待数据", tone: "coral" as const }
  const covered = snapshot.value.coverage.reduce((total, item) => total + item.covered_days, 0)
  if (!covered || snapshot.value.coverage.some((item) => item.status === "empty")) return { label: "低", detail: "关键数据集为空", tone: "coral" as const }
  if (snapshot.value.data_quality_flags.length || snapshot.value.summary.coverage_rate < 80) return { label: "中", detail: `${snapshot.value.data_quality_flags.length} 项数据风险`, tone: "amber" as const }
  return { label: "高", detail: "覆盖完整，可做描述性判断", tone: "teal" as const }
})
const kpis = computed(() => {
  const summary = snapshot.value?.summary; if (!summary) return []
  return [
    { label: "可验证需求词", value: number(summary.high_opportunity_count), detail: `${number(summary.relevant_keyword_count)} 个相关词中筛选`, icon: Lightbulb, tone: "teal" as const },
    { label: "市场排名异动", value: number(summary.rank_mover_count), detail: `上升 ${number(risingTotal.value)} · 下滑 ${number(fallingTotal.value)}`, icon: Activity, tone: "blue" as const },
    { label: "内容 / 直播样本", value: number(summary.content_count), detail: "观察主题与货品组织", icon: Eye, tone: "amber" as const },
    { label: "分析置信度", value: overallConfidence.value.label, detail: `${percent(summary.coverage_rate)} · ${overallConfidence.value.detail}`, icon: ShieldCheck, tone: overallConfidence.value.tone },
  ]
})
const trendOption = computed(() => {
  const data = snapshot.value?.daily_metrics || []
  return { tooltip: { trigger: "axis", valueFormatter: (value: unknown) => value == null ? "暂无" : `${Number(value).toFixed(2)}%` }, legend: { top: 0, textStyle: { color: "#66786f", fontSize: 11 } }, grid: { left: 10, right: 16, top: 38, bottom: 10, containLabel: true }, xAxis: { type: "category", data: data.map((item) => item.stat_date.slice(5)), axisLabel: { color: "#819087", fontSize: 10 }, axisLine: { lineStyle: { color: "#dfe8e2" } } }, yAxis: { type: "value", axisLabel: { color: "#819087", fontSize: 10, formatter: "{value}%" }, splitLine: { lineStyle: { color: "#edf2ee" } } }, series: [{ name: "样本平均点击率", type: "line", smooth: true, data: data.map((item) => item.average_click_rate), symbolSize: 6, itemStyle: { color: "#218b66" }, lineStyle: { width: 2.5 }, areaStyle: { color: "rgba(33,139,102,.08)" } }, { name: "样本平均支付转化", type: "line", smooth: true, data: data.map((item) => item.average_pay_conversion_rate), symbolSize: 6, itemStyle: { color: "#d18a43" }, lineStyle: { width: 2.2 } }] }
})
const marketSamples = computed(() => (snapshot.value?.rankings || []).slice(0, 30))
const contentRankings = computed(() => (snapshot.value?.rankings || []).filter((item) => item.rank_type === "content").slice(0, 6))
const competitiveSignals = computed(() => snapshot.value?.competitive_signals || [])
const demandSignals = computed(() => snapshot.value?.demand_signals || [])
const keywordSegments = computed(() => snapshot.value?.keyword_segments || [])
onMounted(() => { void load() })
</script>

<template>
  <section class="market-hero module-workbench-hero">
    <div><p>市场分析 / 平台观察</p><h2>市场洞察</h2><span>先看结论，再决定是否下钻明细。</span></div>
    <div class="market-hero-actions"><small v-if="snapshot">{{ coverageText }}</small><button type="button" class="capture-refresh" :disabled="loading" @click="load"><RefreshCw :size="16" :class="{ spinning: loading }" />刷新</button></div>
  </section>
  <section v-if="loading && !snapshot" class="market-state"><RefreshCw :size="24" class="spinning" /><span>正在读取市场数据</span></section>
  <section v-else-if="error" class="market-state market-error"><AlertTriangle :size="22" /><span>{{ error }}</span><button type="button" @click="load">重试</button></section>
  <template v-else-if="snapshot">
    <section class="market-kpis">
      <article v-for="item in kpis" :key="item.label" class="market-kpi"><component :is="item.icon" :size="17" /><div><span>{{ item.label }}</span><strong>{{ item.value }}</strong><small>{{ item.detail }}</small></div></article>
    </section>
    <section class="market-meta panel"><div><Database :size="15" /><strong>{{ snapshot.summary.latest_rank_date || "暂无" }} 最新快照</strong><span>排行 {{ snapshot.summary.ranking_rows }} 条 · 搜索词 {{ snapshot.summary.keyword_rows }} 条</span></div><span class="market-boundary-pill">平台信号，不等于本店 GMV</span></section>

    <section class="market-signal-grid">
      <article class="panel market-panel market-demand-panel"><div class="panel-heading"><div><p>需求信号</p><h2>正在上升或新进入的词</h2></div><TrendingUp :size="17" /></div><div class="demand-list"><article v-for="item in demandSignals.slice(0, 6)" :key="`${item.keyword_type}-${item.keyword}`"><span class="direction-chip" :class="item.direction">{{ directionLabel(item) }}</span><div><strong>{{ item.keyword }}</strong><small>{{ keywordTypeLabel[item.keyword_type] || item.keyword_type }} · 出现 {{ item.days_seen }} 天</small></div><div class="demand-metrics"><span><b>{{ percent(item.click_rate) }}</b>点击</span><span><b>{{ percent(item.pay_conversion_midpoint) }}</b>转化</span></div></article><div v-if="!demandSignals.length" class="market-empty">暂无需求变化</div></div></article>
      <article class="panel market-panel market-competition-panel"><div class="panel-heading"><div><p>竞争信号</p><h2>需要拆解的市场样本</h2></div><BarChart3 :size="17" /></div><div class="competition-list"><article v-for="item in competitiveSignals.slice(0, 6)" :key="`${item.rank_type}-${item.entity_id}-${item.current_rank}-${item.direction}`"><span :class="item.direction"><TrendingUp v-if="item.direction === 'rising'" :size="13" /><TrendingDown v-else :size="13" /></span><div><strong>{{ cleanText(item.name) }}</strong><small>{{ rankTypeLabel[item.rank_type] || item.rank_type }} · 当前第 {{ item.current_rank }} 名</small></div></article><div v-if="!competitiveSignals.length" class="market-empty">暂无排名异动</div></div></article>
    </section>

    <section class="panel market-panel market-trend-panel"><div class="panel-heading"><div><p>需求趋势</p><h2>搜索样本点击与支付转化</h2></div><span class="panel-action">缺失日不按 0 补齐</span></div><BusinessChart :option="trendOption" :height="230" ariaLabel="市场搜索词样本平均点击率和支付转化趋势" /></section>

    <details class="market-details">
      <summary><span>查看更多市场明细</span><small>词分层、内容排行、头部店铺与商品、筛选</small></summary>
      <section class="market-detail-grid">
        <article class="panel market-panel"><div class="panel-heading"><div><p>需求结构</p><h2>搜索词分层</h2></div><KeyRound :size="17" /></div><div class="segment-list"><div v-for="item in keywordSegments" :key="item.keyword_type" class="segment-row"><div><strong>{{ keywordTypeLabel[item.keyword_type] || item.keyword_type }}</strong><small>{{ number(item.keyword_count) }} 个词 · {{ cleanText(item.top_keyword) }}</small></div><span><b>{{ percent(item.average_click_rate) }}</b><small>点击</small></span><span><b>{{ percent(item.average_pay_conversion_rate) }}</b><small>转化</small></span><span><b>{{ number(item.high_opportunity_count) }}</b><small>机会词</small></span></div><div v-if="!keywordSegments.length" class="market-empty">暂无分层数据</div></div></article>
        <article class="panel market-panel"><div class="panel-heading"><div><p>内容排行</p><h2>市场正在关注什么</h2></div><Eye :size="17" /></div><div class="market-content-list"><article v-for="item in contentRankings" :key="`${item.rank_no}-${item.entity_id}`"><b>#{{ item.rank_no }}</b><div><strong>{{ cleanText(item.content_title || item.entity_name) }}</strong><small>{{ cleanText(item.shop_name) }} · 观看 {{ item.live_views_range || "暂无" }} · 点击 {{ item.goods_clicks_range || "暂无" }}</small></div></article><div v-if="!contentRankings.length" class="market-empty">暂无内容排行</div></div></article>
      </section>
      <section class="panel market-panel market-sample-panel">
        <div class="market-sample-heading"><div><p>市场样本</p><h2>排行结果</h2><small>共 {{ number(marketSamples.length) }} 条当前筛选结果</small></div><Search :size="17" /></div>
        <div class="market-toolbar market-toolbar-compact"><label><span>开始</span><input v-model="startDate" type="date" /></label><label><span>结束</span><input v-model="endDate" type="date" /></label><label><span>排行</span><select v-model="rankType"><option value="all">全部</option><option value="shop">店铺</option><option value="item">商品</option><option value="content">内容</option></select></label><label><span>词类</span><select v-model="keywordType"><option value="all">全部</option><option value="core">核心词</option><option value="search">搜索词</option><option value="trend">趋势词</option><option value="modify">修饰词</option></select></label><label class="market-search"><span>搜索</span><div><Search :size="14" /><input v-model="query" placeholder="店铺、商品或搜索词" @keyup.enter="applyFilters" /></div></label><button type="button" class="capture-refresh" :disabled="loading" @click="applyFilters">查询</button></div>
        <div class="market-table-wrap market-sample-table"><table><thead><tr><th>类型</th><th>排名</th><th>样本</th><th>所属店铺</th><th>变化</th><th>买家区间</th><th>访客区间</th></tr></thead><tbody><tr v-for="item in marketSamples" :key="`${item.rank_type}-${item.rank_no}-${item.entity_id}`"><td><span class="sample-type" :class="item.rank_type">{{ rankTypeLabel[item.rank_type] || item.rank_type }}</span></td><td><strong>#{{ item.rank_no }}</strong></td><td class="market-name">{{ rankingTitle(item) }}</td><td>{{ item.rank_type === "shop" ? "—" : cleanText(item.shop_name) }}</td><td><span :class="{ 'market-up': (item.rank_change || 0) > 0, 'market-down': (item.rank_change || 0) < 0 }">{{ rankChange(item) }}</span></td><td>{{ item.paid_buyers_range || "暂无" }}</td><td>{{ item.visitors_range || "暂无" }}</td></tr><tr v-if="!marketSamples.length"><td colspan="7" class="market-empty">当前筛选没有匹配的市场样本</td></tr></tbody></table></div>
      </section>
      <section class="market-boundary"><span><ArrowDownRight :size="14" />口径与边界</span><p v-for="item in [...snapshot.diagnostics, ...snapshot.data_quality_flags]" :key="item">{{ item }}</p></section>
    </details>
  </template>
  <EmptyState v-else title="暂无市场洞察数据" detail="当前本地库没有市场排行或搜索词快照，页面不会使用模拟数据填充。" :icon="Database" />
</template>

<style scoped>
.market-hero { align-items: center; }.market-state { display: flex; align-items: center; justify-content: center; gap: 10px; min-height: 180px; border: 1px solid #e1e9e4; border-radius: 10px; background: #fff; color: #63766c; }.market-error { color: #a85f50; }.market-error button { border: 1px solid #d7e2db; border-radius: 6px; padding: 7px 12px; background: #fff; color: #316d55; cursor: pointer; }.market-status { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-top: 14px; padding: 13px 16px; }.market-status > div { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }.market-status svg { color: #278d68; }.market-status strong { color: #304a3e; font-size: 12px; }.market-status span, .market-status small { color: #73847b; font-size: 10px; }
.market-command-grid, .market-insight-grid, .market-signal-grid, .market-table-grid { display: grid; gap: 14px; margin-top: 14px; }.market-command-grid { grid-template-columns: minmax(0, 1.45fr) minmax(300px, .55fr); }.market-insight-grid { grid-template-columns: minmax(0, 1.2fr) minmax(350px, .8fr); }.market-signal-grid, .market-table-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }.market-command-grid > .panel, .market-insight-grid > .panel, .market-signal-grid > .panel, .market-table-grid > .panel { min-width: 0; padding: 17px; }.decision-list { display: grid; gap: 8px; margin-top: 10px; }.decision-card { display: grid; grid-template-columns: 35px minmax(0, 1fr); gap: 11px; border: 1px solid #e3ebe6; border-radius: 8px; padding: 12px; background: #fbfdfc; }.decision-priority { display: grid; width: 32px; height: 28px; place-items: center; border-radius: 6px; background: #dff2e9; color: #167a55; font-size: 10px; font-weight: 750; }.decision-card > div { min-width: 0; }.decision-title { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }.decision-title em { color: #278661; font-size: 9px; font-style: normal; font-weight: 650; }.decision-title strong { color: #2d493c; font-size: 12px; }.decision-title small { margin-left: auto; border-radius: 999px; padding: 2px 6px; font-size: 8px; }.confidence-high { background: #e1f3ea; color: #1c7d59; }.confidence-medium { background: #fff3dd; color: #9b6b26; }.confidence-low { background: #fff0eb; color: #ae6655; }.decision-card p { margin: 5px 0 8px; color: #5e7268; font-size: 10px; line-height: 1.5; }.decision-card dl { display: grid; gap: 4px; margin: 0; }.decision-card dl div { display: grid; grid-template-columns: 32px minmax(0, 1fr); gap: 6px; }.decision-card dt { color: #90a098; font-size: 9px; }.decision-card dd { margin: 0; color: #667b70; font-size: 9px; line-height: 1.45; }
.audit-score { display: flex; align-items: center; gap: 12px; margin: 14px 0; border-radius: 8px; padding: 12px; background: #eef7f2; }.audit-score > strong { display: grid; width: 48px; height: 48px; place-items: center; border: 1px solid #cfe7da; border-radius: 50%; color: #207b59; font-size: 20px; }.audit-score div { display: grid; gap: 3px; }.audit-score b { color: #385447; font-size: 11px; }.audit-score span { color: #71857a; font-size: 9px; }.coverage-list { display: grid; gap: 5px; }.coverage-list > div { display: grid; grid-template-columns: 18px minmax(0, 1fr) auto; gap: 7px; align-items: center; border-bottom: 1px solid #ebf0ed; padding: 8px 0; }.coverage-list svg { color: #258461; }.coverage-list span { display: grid; gap: 2px; }.coverage-list b { color: #435b50; font-size: 10px; }.coverage-list small { color: #84938b; font-size: 9px; }.coverage-list em { border-radius: 999px; padding: 3px 7px; background: #e6f4ed; color: #21805d; font-size: 8px; font-style: normal; }.coverage-list em.partial, .coverage-list em.empty { background: #fff2e5; color: #aa6d35; }.audit-flags { margin-top: 10px; border-left: 2px solid #d69a64; padding-left: 9px; }.audit-flags p { margin: 3px 0; color: #8b6b55; font-size: 9px; line-height: 1.45; }.audit-boundary, .panel-footnote { margin: 10px 0 0; color: #768980; font-size: 9px; line-height: 1.55; }
.segment-list { display: grid; gap: 2px; margin-top: 10px; }.segment-row { display: grid; grid-template-columns: minmax(0, 1.4fr) repeat(3, minmax(62px, .65fr)); gap: 8px; align-items: center; border-bottom: 1px solid #ebf0ed; padding: 12px 0; }.segment-row > div { min-width: 0; display: grid; gap: 3px; }.segment-row strong { color: #344f42; font-size: 11px; }.segment-row small { overflow: hidden; color: #83928a; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }.segment-row > span { display: grid; gap: 2px; text-align: right; }.segment-row b { color: #2f745a; font-size: 11px; }.segment-row > span small { overflow: visible; white-space: normal; }.demand-list, .competition-list { display: grid; margin-top: 8px; }.demand-list > article { display: grid; grid-template-columns: 72px minmax(0, 1fr) 150px; gap: 9px; align-items: center; border-bottom: 1px solid #ebf0ed; padding: 10px 0; }.direction-chip { justify-self: start; border-radius: 999px; padding: 4px 7px; background: #eef2ef; color: #78887f; font-size: 8px; }.direction-chip.rising { background: #e0f3ea; color: #187b56; }.direction-chip.new { background: #e8eefc; color: #5270b5; }.direction-chip.falling { background: #fff0eb; color: #ad6654; }.demand-list article > div:nth-child(2) { min-width: 0; display: grid; gap: 3px; }.demand-list strong, .competition-list strong { overflow: hidden; color: #344f42; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }.demand-list small, .demand-list p, .competition-list small, .competition-list p { margin: 0; color: #7d8d84; font-size: 9px; line-height: 1.45; }.demand-metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 5px; }.demand-metrics span { display: grid; gap: 2px; color: #8a9991; font-size: 8px; text-align: right; }.demand-metrics b { color: #356f58; font-size: 10px; }.competition-list > article { display: grid; grid-template-columns: 26px minmax(0, 1fr); gap: 8px; border-bottom: 1px solid #ebf0ed; padding: 10px 0; }.competition-list > article > span { display: grid; width: 24px; height: 24px; place-items: center; border-radius: 50%; }.competition-list > article > span.rising { background: #e0f3ea; color: #187b56; }.competition-list > article > span.falling { background: #fff0eb; color: #ad6654; }.competition-list article div { min-width: 0; display: grid; gap: 3px; }
.market-content-panel, .market-toolbar-panel { margin-top: 14px; padding: 17px; }.market-content-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 9px; margin-top: 9px; }.market-content-card { display: grid; grid-template-columns: 31px minmax(0, 1fr); gap: 9px; border: 1px solid #e3ebe6; border-radius: 7px; padding: 11px; background: #fbfdfc; }.market-content-card > span { display: grid; width: 29px; height: 29px; place-items: center; border-radius: 6px; background: #e4f2eb; color: #247f5f; font-size: 9px; font-weight: 700; }.market-content-card div { min-width: 0; display: grid; gap: 4px; }.market-content-card strong { overflow: hidden; color: #344f42; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }.market-content-card small, .market-content-card p { margin: 0; color: #819087; font-size: 8px; line-height: 1.45; }.market-toolbar { display: grid; grid-template-columns: 130px 130px 130px 140px minmax(170px, 1fr) auto; gap: 9px; align-items: end; margin-top: 10px; }.market-toolbar label { display: grid; gap: 5px; color: #71837a; font-size: 9px; }.market-toolbar input, .market-toolbar select { width: 100%; min-height: 34px; border: 1px solid #d9e4dd; border-radius: 6px; padding: 0 9px; background: #fff; color: #30483d; font: inherit; font-size: 10px; }.market-search > div { display: flex; align-items: center; gap: 6px; min-height: 34px; border: 1px solid #d9e4dd; border-radius: 6px; padding: 0 9px; background: #fff; }.market-search input { min-height: 27px; border: 0; padding: 0; outline: 0; }.market-table-wrap { overflow: auto; margin-top: 8px; }.market-table-wrap table { width: 100%; min-width: 540px; border-collapse: collapse; }.market-table-wrap th, .market-table-wrap td { border-bottom: 1px solid #ebf0ed; padding: 9px 7px; color: #5b6f65; font-size: 9px; text-align: left; white-space: nowrap; }.market-table-wrap th { color: #87968e; font-weight: 500; }.market-table-wrap td strong { color: #365245; }.market-name { max-width: 230px; overflow: hidden; color: #304d40 !important; text-overflow: ellipsis; }.market-up { color: #187b56; }.market-down { color: #ad6654; }.market-tag { border-radius: 999px; padding: 3px 7px; background: #edf1ef; color: #7d8c84; font-size: 8px; }.market-tag.active { background: #e0f3ea; color: #187b56; }.market-empty { padding: 28px 8px !important; color: #8c9b93 !important; text-align: center !important; font-size: 10px; }.market-boundary { display: grid; gap: 3px; margin: 14px 0 20px; border-top: 1px solid #e1e8e3; padding-top: 12px; color: #7b8c83; font-size: 9px; }.market-boundary span { display: inline-flex; align-items: center; gap: 5px; color: #61776b; }.market-boundary p { margin: 0; }
@media (max-width: 1120px) { .market-command-grid, .market-insight-grid, .market-signal-grid, .market-table-grid { grid-template-columns: 1fr; }.market-toolbar { grid-template-columns: repeat(3, minmax(0, 1fr)); }.market-content-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } } @media (max-width: 680px) { .market-status { align-items: flex-start; flex-direction: column; }.market-toolbar { grid-template-columns: 1fr; }.market-content-grid { grid-template-columns: 1fr; }.demand-list > article { grid-template-columns: 1fr; }.demand-metrics { justify-self: stretch; }.demand-metrics span { text-align: left; }.segment-row { grid-template-columns: minmax(0, 1.3fr) repeat(3, minmax(48px, .6fr)); }.decision-title small { margin-left: 0; } }

/* Compact market workspace: keep decisions visible and move evidence detail behind disclosure. */
.market-hero { min-height: 108px; }
.market-hero-actions { display: flex; align-items: center; gap: 12px; }
.market-hero-actions small { color: #829188; font-size: 10px; }
.market-state { min-height: 160px; }
.market-kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-top: 12px; }
.market-kpi { display: flex; align-items: flex-start; gap: 10px; min-width: 0; border: 1px solid #e3eae6; border-radius: 9px; padding: 13px 14px; background: #fff; }
.market-kpi > svg { flex: 0 0 auto; margin-top: 2px; color: #348164; }
.market-kpi > div { min-width: 0; display: grid; grid-template-columns: 1fr auto; gap: 3px 10px; align-items: baseline; width: 100%; }
.market-kpi span { color: #718279; font-size: 10px; }
.market-kpi strong { color: #2f4b3e; font-size: 18px; font-weight: 680; }
.market-kpi small { grid-column: 1 / -1; overflow: hidden; color: #94a099; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.market-meta { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 10px; padding: 10px 14px; }
.market-meta > div { display: flex; align-items: center; flex-wrap: wrap; gap: 7px; color: #718279; font-size: 10px; }
.market-meta svg { color: #348164; }.market-meta strong { color: #395347; }
.market-boundary-pill { border-radius: 999px; padding: 4px 8px; background: #f3f6f4; color: #7e8d85; font-size: 9px; white-space: nowrap; }
.market-focus-grid, .market-signal-grid, .market-detail-grid, .market-table-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-top: 10px; }
.market-panel { min-width: 0; padding: 15px; }
.market-focus-grid .panel-heading h2, .market-signal-grid .panel-heading h2, .market-details .panel-heading h2 { font-size: 14px; }
.decision-list { gap: 6px; margin-top: 8px; }
.decision-card { grid-template-columns: 30px minmax(0, 1fr); gap: 9px; border: 0; border-top: 1px solid #edf1ef; border-radius: 0; padding: 10px 0; background: transparent; }
.decision-card:first-child { border-top: 0; padding-top: 3px; }
.decision-priority { width: 28px; height: 25px; }
.decision-title strong { font-size: 11px; }
.decision-title small { margin-left: 0; }
.decision-card p { margin: 4px 0; font-size: 9px; }
.decision-action { display: block; color: #3d745d; font-size: 9px; line-height: 1.45; }
.audit-score { display: grid; grid-template-columns: 42px minmax(0, 1fr); gap: 10px; margin: 9px 0 5px; padding: 10px; }
.audit-score > strong { width: 40px; height: 40px; font-size: 17px; }
.audit-score > span { align-self: center; color: #6f8278; font-size: 10px; }
.coverage-list > div { padding: 7px 0; }
.market-signal-grid { align-items: start; }
.demand-list, .competition-list { margin-top: 5px; }
.demand-list > article { grid-template-columns: 66px minmax(0, 1fr) 112px; padding: 9px 0; }
.demand-metrics { grid-template-columns: repeat(2, 1fr); }
.competition-list > article { align-items: center; padding: 9px 0; }
.market-trend-panel { margin-top: 10px; }
.market-details { margin: 10px 0 20px; border: 1px solid #dfe7e2; border-radius: 10px; background: #f8faf9; }
.market-details > summary { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 13px 15px; color: #365347; cursor: pointer; list-style: none; }
.market-details > summary::-webkit-details-marker { display: none; }
.market-details > summary span { font-size: 11px; font-weight: 650; }
.market-details > summary small { color: #89978f; font-size: 9px; }
.market-details[open] > summary { border-bottom: 1px solid #e1e8e4; }
.market-details > section { margin-left: 10px; margin-right: 10px; }
.market-detail-grid { margin-top: 10px; }
.market-content-list { display: grid; margin-top: 7px; }
.market-content-list article { display: grid; grid-template-columns: 28px minmax(0, 1fr); gap: 8px; align-items: center; border-bottom: 1px solid #ebf0ed; padding: 9px 0; }
.market-content-list b { color: #25805e; font-size: 9px; }.market-content-list div { min-width: 0; display: grid; gap: 3px; }
.market-content-list strong { overflow: hidden; color: #365045; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.market-content-list small { overflow: hidden; color: #84938b; font-size: 8px; text-overflow: ellipsis; white-space: nowrap; }
.market-toolbar-panel { margin-top: 10px; }
.market-toolbar { grid-template-columns: 125px 125px 125px 135px minmax(160px, 1fr) auto; }
.market-table-grid { margin-top: 10px; }
.market-boundary { margin: 10px 10px 16px !important; }
@media (max-width: 1100px) { .market-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }.market-focus-grid, .market-signal-grid, .market-detail-grid, .market-table-grid { grid-template-columns: 1fr; }.market-toolbar { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 680px) { .market-hero-actions, .market-meta { align-items: flex-start; flex-direction: column; }.market-kpis { grid-template-columns: 1fr 1fr; }.market-focus-grid, .market-signal-grid { grid-template-columns: 1fr; }.demand-list > article { grid-template-columns: 1fr; }.demand-metrics { justify-self: stretch; }.market-toolbar { grid-template-columns: 1fr; }.market-details > summary { align-items: flex-start; flex-direction: column; } }

.market-sample-panel { margin-top: 10px; }
.market-sample-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.market-sample-heading > div { display: grid; gap: 2px; }.market-sample-heading p, .market-sample-heading h2 { margin: 0; }
.market-sample-heading p { color: #87968e; font-size: 9px; }.market-sample-heading h2 { color: #2f4b3e; font-size: 14px; }.market-sample-heading small { color: #93a098; font-size: 9px; }
.market-toolbar-compact { grid-template-columns: 118px 118px 105px 105px minmax(220px, 1fr) auto; margin-top: 12px; border-top: 1px solid #e8eeea; border-bottom: 1px solid #e8eeea; padding: 10px 0; }
.market-sample-table { margin-top: 0; }
.market-sample-table table { min-width: 900px; }
.market-sample-table th, .market-sample-table td { padding-block: 11px; }
.market-sample-table tbody tr:hover { background: #f8fbf9; }
.sample-type { display: inline-flex; min-width: 38px; justify-content: center; border-radius: 999px; padding: 3px 7px; background: #edf3f0; color: #567166; font-size: 8px; }
.sample-type.shop { background: #e7f3ed; color: #217957; }.sample-type.item { background: #edf1fa; color: #5770a9; }.sample-type.content { background: #fff1e5; color: #a46b36; }
@media (max-width: 900px) { .market-toolbar-compact { grid-template-columns: repeat(2, minmax(0, 1fr)); }.market-toolbar-compact .market-search { grid-column: 1 / -1; }.market-toolbar-compact button { justify-self: start; } }
</style>
