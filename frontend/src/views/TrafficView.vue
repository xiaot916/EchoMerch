<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import { ArrowLeft, ChevronRight, CircleAlert, Eye, MousePointerClick, Route, Target, UserPlus } from "lucide-vue-next"

import BusinessChart from "@/components/BusinessChart.vue"
import EmptyState from "@/components/EmptyState.vue"
import MetricCard from "@/components/MetricCard.vue"
import { fetchStores, fetchTrafficTree } from "@/api"
import { useDashboard } from "@/composables/useDashboard"
import { currency, number, ratio } from "@/lib/format"
import type { TrafficTreeNode } from "@/types"

type SourceSortKey = "paid_amount" | "visitors" | "conversion_rate"

const { dashboard } = useDashboard()
const trafficTree = ref<TrafficTreeNode[]>([])
const selectedId = ref("")
const sourceSort = ref<SourceSortKey>("paid_amount")
const loading = ref(true)
const error = ref("")

const flattenedNodes = computed(() => {
  const result: TrafficTreeNode[] = []
  const visit = (nodes: TrafficTreeNode[]): void => {
    for (const node of nodes) { result.push(node); visit(node.children) }
  }
  visit(trafficTree.value)
  return result
})
const nodeById = computed(() => new Map(flattenedNodes.value.map((node) => [node.id, node])))
const selectedNode = computed(() => nodeById.value.get(selectedId.value) || trafficTree.value[0])
const selectedRootId = computed(() => {
  const node = selectedNode.value
  if (!node) return ""
  return node.level === 1 ? node.id : trafficTree.value.find((root) => node.path[0] === root.name)?.id || ""
})
const selectedParent = computed(() => selectedNode.value?.parent_id ? nodeById.value.get(selectedNode.value.parent_id) : undefined)
const selectedPathNodes = computed(() => {
  const node = selectedNode.value
  if (!node) return []
  return node.path.map((_, index) => flattenedNodes.value.find((item) => item.level === index + 1 && item.path.slice(0, index + 1).join("/") === node.path.slice(0, index + 1).join("/"))).filter((item): item is TrafficTreeNode => Boolean(item))
})
const childRows = computed(() => [...(selectedNode.value?.children ?? [])].sort((left, right) => right.paid_amount - left.paid_amount))
const sortedRootSources = computed(() => [...trafficTree.value].sort((left, right) => right[sourceSort.value] - left[sourceSort.value]))

const totalTrafficPaidAmount = computed(() => trafficTree.value.reduce((total, item) => total + item.paid_amount, 0))
const totalVisitors = computed(() => trafficTree.value.reduce((total, item) => total + item.visitors, 0))
const totalBuyers = computed(() => trafficTree.value.reduce((total, item) => total + item.buyers, 0))
const totalNewVisitors = computed(() => trafficTree.value.reduce((total, item) => total + item.new_visitors, 0))
const sourceConversionRate = computed(() => totalVisitors.value ? totalBuyers.value / totalVisitors.value * 100 : 0)
const newVisitorRate = computed(() => totalVisitors.value ? totalNewVisitors.value / totalVisitors.value * 100 : 0)
const sourceUvValue = computed(() => totalVisitors.value ? totalTrafficPaidAmount.value / totalVisitors.value : 0)
const maxRootPaidAmount = computed(() => Math.max(...trafficTree.value.map((item) => item.paid_amount), 1))

const largestTrafficSource = computed(() => [...trafficTree.value].sort((left, right) => right.visitors - left.visitors)[0])
const highestConversionSource = computed(() => [...trafficTree.value].sort((left, right) => right.conversion_rate - left.conversion_rate)[0])
const highestNewVisitorSource = computed(() => [...trafficTree.value].sort((left, right) => newVisitorShare(right) - newVisitorShare(left))[0])
const highestUvSource = computed(() => [...trafficTree.value].sort((left, right) => right.uv_value - left.uv_value)[0])

const qualityOption = computed(() => ({
  color: ["#238c69"],
  tooltip: {
    trigger: "item",
    formatter: (params: { data: [number, number, number, string, number, number] }) => {
      const [newRate, conversion, visitors, name, paidAmount, buyers] = params.data
      return `${name}<br/>访客：${number(visitors)}<br/>新访客率：${ratio(newRate)}<br/>支付转化率：${ratio(conversion)}<br/>支付买家：${number(buyers)}<br/>归因成交：${currency(paidAmount)}`
    },
  },
  grid: { left: 70, right: 38, top: 28, bottom: 60 },
  xAxis: { type: "value", name: "新访客率", nameLocation: "middle", nameGap: 38, min: 0, max: 100, splitNumber: 5, nameTextStyle: { color: "#718078", fontSize: 10, fontWeight: 600 }, axisLabel: { color: "#7c8982", fontSize: 9, formatter: "{value}%" }, axisLine: { lineStyle: { color: "#b3beb8" } }, axisTick: { show: false }, splitLine: { lineStyle: { color: "#edf1ef" } } },
  yAxis: { type: "value", name: "支付转化率", nameLocation: "middle", nameGap: 48, min: 0, nameTextStyle: { color: "#718078", fontSize: 10, fontWeight: 600 }, axisLabel: { color: "#7c8982", fontSize: 9, formatter: "{value}%" }, axisLine: { lineStyle: { color: "#b3beb8" } }, axisTick: { show: false }, splitLine: { lineStyle: { color: "#edf1ef" } } },
  series: [{
    type: "scatter",
    symbolSize: (value: [number, number, number]) => Math.max(24, Math.min(58, Math.sqrt(value[2] || 1) / 6)),
    itemStyle: { color: "#279b73", opacity: 0.84, borderColor: "#fff", borderWidth: 1.5 },
    label: { show: true, position: "top", color: "#50635a", fontSize: 9, formatter: (params: { data: [number, number, number, string] }) => params.data[3] },
    data: trafficTree.value.map((item) => [newVisitorShare(item), item.conversion_rate, item.visitors, item.name, item.paid_amount, item.buyers]),
    markLine: { symbol: ["none", "none"], silent: true, lineStyle: { color: "#b8c9bf", type: "dashed" }, label: { color: "#68786f", fontSize: 9, backgroundColor: "rgba(255,255,255,.9)", padding: [2, 4] }, data: [{ xAxis: newVisitorRate.value, label: { formatter: `平均新客 ${newVisitorRate.value.toFixed(1)}%`, position: "insideEndTop" } }, { yAxis: sourceConversionRate.value, label: { formatter: `平均转化 ${sourceConversionRate.value.toFixed(1)}%`, position: "insideStartTop" } }] },
  }],
}))

function newVisitorShare(item: TrafficTreeNode): number { return item.visitors ? item.new_visitors / item.visitors * 100 : 0 }
function paidBarWidth(item: TrafficTreeNode): string { return `${Math.max(3, Math.min(100, item.paid_amount / maxRootPaidAmount.value * 100))}%` }
function selectNode(node: TrafficTreeNode): void { selectedId.value = node.id }
function selectParent(): void { if (selectedParent.value) selectNode(selectedParent.value) }

async function loadTree(): Promise<void> {
  if (!dashboard.value) return
  loading.value = true
  error.value = ""
  try {
    const stores = await fetchStores()
    trafficTree.value = await fetchTrafficTree(dashboard.value.range_start, dashboard.value.range_end, stores[0]?.store_id)
    if (!nodeById.value.has(selectedId.value)) selectedId.value = trafficTree.value[0]?.id || ""
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : "流量来源读取失败"
  } finally {
    loading.value = false
  }
}

watch(() => [dashboard.value?.range_start, dashboard.value?.range_end], () => { void loadTree() })
onMounted(() => { void loadTree() })
</script>

<template>
  <template v-if="dashboard">
    <section class="traffic-context-strip"><div><Route :size="16" /><strong>流量来源</strong><span>一级来源及下级来源明细。</span></div><em>{{ trafficTree.length }} 个一级来源 · {{ flattenedNodes.length }} 个来源节点</em></section>

    <section class="metrics-grid traffic-quality-metrics">
      <MetricCard label="来源访客" :value="number(totalVisitors)" detail="一级来源口径，存在跨来源重叠" :icon="Eye" tone="blue" scope="来源口径" />
      <MetricCard label="新访客率" :value="ratio(newVisitorRate)" :detail="`${number(totalNewVisitors)} 位新访客`" :icon="UserPlus" tone="teal" scope="一级加权" />
      <MetricCard label="支付转化率" :value="ratio(sourceConversionRate)" :detail="`${number(totalBuyers)} 位支付买家`" :icon="MousePointerClick" tone="amber" scope="一级加权" />
      <MetricCard label="平均 UV 价值" :value="currency(sourceUvValue)" detail="一级归因金额 / 来源访客" :icon="Target" tone="coral" scope="来源口径" />
    </section>

    <section v-if="loading" class="panel traffic-page-state"><span>正在读取流量来源…</span></section>
    <section v-else-if="error" class="panel traffic-page-state error"><CircleAlert :size="18" /><span>{{ error }}</span></section>

    <template v-else-if="trafficTree.length">
      <section class="traffic-workspace-grid">
        <article class="panel traffic-source-board">
          <div class="panel-heading traffic-board-heading"><div><p>一级来源表现</p><h2>来源规模与成交质量</h2></div><div class="traffic-sort-control" role="tablist" aria-label="一级来源排序"><button :class="{ active: sourceSort === 'paid_amount' }" @click="sourceSort = 'paid_amount'">成交金额</button><button :class="{ active: sourceSort === 'visitors' }" @click="sourceSort = 'visitors'">访客</button><button :class="{ active: sourceSort === 'conversion_rate' }" @click="sourceSort = 'conversion_rate'">转化率</button></div></div>
          <div class="traffic-source-table">
            <div class="traffic-source-row traffic-source-head"><span>一级来源</span><span>访客 / 新客</span><span>买家</span><span>转化率</span><span>归因成交</span><span>UV 价值</span></div>
            <button v-for="item in sortedRootSources" :key="item.id" type="button" class="traffic-source-row" :class="{ active: selectedRootId === item.id }" @click="selectNode(item)"><div class="traffic-source-name"><strong>{{ item.name }}</strong><div><i :style="{ width: paidBarWidth(item) }"></i></div><small>{{ item.children.length }} 个下级来源</small></div><div><strong>{{ number(item.visitors) }}</strong><small>新客 {{ ratio(newVisitorShare(item)) }}</small></div><strong>{{ number(item.buyers) }}</strong><strong>{{ ratio(item.conversion_rate) }}</strong><strong class="money">{{ currency(item.paid_amount) }}</strong><strong>{{ currency(item.uv_value) }}</strong></button>
          </div>
          <p class="traffic-source-note">一级来源之间可能重复覆盖同一访客或成交，本表用于来源间相对比较，不等同店铺总盘。</p>
        </article>

        <aside v-if="selectedNode" class="panel traffic-drilldown-panel">
          <div class="traffic-path-toolbar"><button v-if="selectedParent" type="button" title="返回上一级" @click="selectParent"><ArrowLeft :size="15" /></button><div class="traffic-breadcrumb"><button v-for="(node, index) in selectedPathNodes" :key="node.id" type="button" :class="{ active: node.id === selectedNode.id }" @click="selectNode(node)"><span v-if="index">/</span>{{ node.name }}</button></div><em>L{{ selectedNode.level }}</em></div>
          <div class="traffic-selected-heading"><div><span>当前来源</span><h2>{{ selectedNode.name }}</h2></div><strong>{{ selectedNode.derived_from_children ? "下级汇总" : "平台原始记录" }}</strong></div>
          <div class="traffic-selected-metrics"><div><span>归因成交</span><strong>{{ currency(selectedNode.paid_amount) }}</strong></div><div><span>访客</span><strong>{{ number(selectedNode.visitors) }}</strong></div><div><span>支付买家</span><strong>{{ number(selectedNode.buyers) }}</strong></div><div><span>支付转化率</span><strong>{{ ratio(selectedNode.conversion_rate) }}</strong></div><div><span>新访客率</span><strong>{{ ratio(newVisitorShare(selectedNode)) }}</strong></div><div><span>UV 价值</span><strong>{{ currency(selectedNode.uv_value) }}</strong></div></div>
          <div class="traffic-child-heading"><div><span>继续下钻</span><strong>{{ childRows.length ? `${childRows.length} 个下级来源` : "已经到最深层级" }}</strong></div></div>
          <div v-if="childRows.length" class="traffic-child-table"><button v-for="item in childRows" :key="item.id" type="button" @click="selectNode(item)"><div><strong>{{ item.name }}</strong><span>{{ number(item.visitors) }} 访客 · {{ ratio(item.conversion_rate) }}</span></div><div><strong>{{ currency(item.paid_amount) }}</strong><ChevronRight :size="14" /></div></button></div>
          <EmptyState v-else title="没有更细来源" detail="当前来源已经是平台提供的最深层级。" />
        </aside>
      </section>

      <section class="traffic-analysis-grid">
        <article class="panel traffic-quality-panel"><div class="panel-heading traffic-analysis-heading"><div><p>来源效率</p><h2>新客率与支付转化率</h2><span>气泡大小代表访客规模。</span></div><Target :size="18" /></div><BusinessChart :option="qualityOption" ariaLabel="一级来源新访客率与支付转化率气泡图" :height="330" /></article>
        <article class="panel traffic-insight-panel"><div class="panel-heading"><div><p>来源排名</p><h2>关键指标最高来源</h2></div><Route :size="18" /></div><div class="traffic-insight-list"><button v-if="largestTrafficSource" type="button" @click="selectNode(largestTrafficSource)"><span>访客数</span><strong>{{ largestTrafficSource.name }}</strong><small>{{ number(largestTrafficSource.visitors) }} 访客 · 新客 {{ ratio(newVisitorShare(largestTrafficSource)) }}</small><ChevronRight :size="15" /></button><button v-if="highestConversionSource" type="button" @click="selectNode(highestConversionSource)"><span>支付转化率</span><strong>{{ highestConversionSource.name }}</strong><small>{{ ratio(highestConversionSource.conversion_rate) }} · {{ number(highestConversionSource.buyers) }} 位买家</small><ChevronRight :size="15" /></button><button v-if="highestNewVisitorSource" type="button" @click="selectNode(highestNewVisitorSource)"><span>新访客率</span><strong>{{ highestNewVisitorSource.name }}</strong><small>{{ ratio(newVisitorShare(highestNewVisitorSource)) }} · {{ number(highestNewVisitorSource.new_visitors) }} 位新访客</small><ChevronRight :size="15" /></button><button v-if="highestUvSource" type="button" @click="selectNode(highestUvSource)"><span>UV 价值</span><strong>{{ highestUvSource.name }}</strong><small>{{ currency(highestUvSource.uv_value) }} / 访客</small><ChevronRight :size="15" /></button></div></article>
      </section>
    </template>
    <EmptyState v-else-if="!loading" title="暂无流量来源数据" detail="当前日期范围没有可用于诊断的来源记录。" />
  </template>
</template>

<style scoped>
.traffic-context-strip { display: flex; min-height: 44px; align-items: center; justify-content: space-between; gap: 16px; border: 1px solid #dfe6e3; border-radius: 5px; padding: 0 14px; color: #7c8982; background: #fff; font-size: 10px; }.traffic-context-strip > div { display: flex; min-width: 0; align-items: center; gap: 8px; }.traffic-context-strip svg { flex: 0 0 auto; color: #288c69; }.traffic-context-strip strong { flex: 0 0 auto; color: #34483e; font-size: 11px; }.traffic-context-strip span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.traffic-context-strip em { flex: 0 0 auto; color: #2b8062; font-style: normal; }.traffic-quality-metrics { margin-top: 0; }.traffic-page-state { display: flex; min-height: 180px; align-items: center; justify-content: center; gap: 8px; color: #7d8997; font-size: 11px; }.traffic-page-state.error { color: #b55648; }
.traffic-workspace-grid { display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(330px, .72fr); gap: 14px; align-items: start; }.traffic-source-board, .traffic-drilldown-panel { min-width: 0; }.traffic-board-heading { align-items: flex-end; }.traffic-sort-control { display: inline-flex; gap: 2px; padding: 3px; border-radius: 5px; background: #f1f4f3; }.traffic-sort-control button { min-height: 28px; border: 0; border-radius: 3px; padding: 0 9px; color: #7a8780; background: transparent; font-size: 10px; }.traffic-sort-control button.active { color: #fff; background: #288c69; }
.traffic-source-table { margin-top: 14px; overflow-x: auto; }.traffic-source-row { display: grid; width: 100%; min-width: 0; grid-template-columns: minmax(130px, 1.25fr) .72fr .48fr .55fr .8fr .55fr; align-items: center; gap: 8px; border: 0; border-bottom: 1px solid #edf1ef; padding: 0 6px; color: #5f6f67; background: transparent; font-size: 10px; text-align: right; font-variant-numeric: tabular-nums; }.traffic-source-row:not(.traffic-source-head) { min-height: 68px; cursor: pointer; }.traffic-source-row:not(.traffic-source-head):hover { background: #f8fbf9; }.traffic-source-row.active { background: #f0f8f4; box-shadow: inset 3px 0 #288c69; }.traffic-source-head { min-height: 34px; color: #98a39d; }.traffic-source-row > :first-child { text-align: left; }.traffic-source-row > strong, .traffic-source-row > div > strong { color: #42564c; font-size: 10px; }.traffic-source-row .money { color: #247b5d; }.traffic-source-row > div:not(.traffic-source-name) { display: grid; gap: 4px; }.traffic-source-row small { color: #98a39d; font-size: 8px; }
.traffic-source-name { display: grid; grid-template-columns: minmax(0, 1fr) 76px; align-items: center; gap: 5px 8px; }.traffic-source-name strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.traffic-source-name > div { height: 5px; overflow: hidden; border-radius: 4px; background: #e8efeb; }.traffic-source-name i { display: block; height: 100%; border-radius: inherit; background: #3bad82; }.traffic-source-name small { grid-column: 1 / -1; }.traffic-source-note { margin: 12px 0 0; color: #99a49e; font-size: 9px; line-height: 1.5; }
.traffic-drilldown-panel { display: flex; flex-direction: column; }.traffic-path-toolbar { display: flex; min-height: 30px; align-items: center; gap: 8px; }.traffic-path-toolbar > button { display: grid; width: 28px; height: 28px; flex: 0 0 auto; place-items: center; border: 1px solid #dce5e0; border-radius: 4px; color: #557065; background: #fff; }.traffic-breadcrumb { display: flex; min-width: 0; flex: 1; align-items: center; overflow: hidden; }.traffic-breadcrumb button { display: inline-flex; min-width: 0; align-items: center; gap: 5px; border: 0; padding: 0 3px; overflow: hidden; color: #84918a; background: transparent; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }.traffic-breadcrumb button.active { color: #267b5d; font-weight: 700; }.traffic-path-toolbar em { border-radius: 3px; padding: 3px 5px; color: #547164; background: #edf4f0; font-size: 8px; font-style: normal; }
.traffic-selected-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-top: 13px; border-bottom: 1px solid #edf1ef; padding-bottom: 13px; }.traffic-selected-heading span { color: #98a39d; font-size: 9px; }.traffic-selected-heading h2 { margin: 5px 0 0; color: #2d4338; font-size: 17px; }.traffic-selected-heading > strong { border: 1px solid #d9e9e1; border-radius: 4px; padding: 4px 6px; color: #288c69; background: #f2f9f5; font-size: 8px; font-weight: 650; }.traffic-selected-metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); margin-top: 13px; border: 1px solid #e5ebe8; border-radius: 4px; overflow: hidden; background: #e5ebe8; gap: 1px; }.traffic-selected-metrics > div { display: grid; gap: 5px; padding: 10px; background: #fbfcfc; }.traffic-selected-metrics span { color: #98a39d; font-size: 8px; }.traffic-selected-metrics strong { color: #3f554a; font-size: 11px; }
.traffic-child-heading { margin-top: 15px; border-bottom: 1px solid #edf1ef; padding-bottom: 8px; }.traffic-child-heading > div { display: flex; align-items: center; justify-content: space-between; gap: 10px; }.traffic-child-heading span { color: #7f8d85; font-size: 9px; }.traffic-child-heading strong { color: #496056; font-size: 10px; }.traffic-child-table { display: grid; max-height: 150px; overflow-y: auto; }.traffic-child-table button { display: grid; min-height: 54px; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 10px; border: 0; border-bottom: 1px solid #edf1ef; padding: 7px 2px; background: transparent; text-align: left; }.traffic-child-table button:hover { background: #f8fbf9; }.traffic-child-table button > div:first-child { display: grid; min-width: 0; gap: 4px; }.traffic-child-table button strong { overflow: hidden; color: #40544a; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }.traffic-child-table button span { color: #98a39d; font-size: 8px; }.traffic-child-table button > div:last-child { display: flex; align-items: center; gap: 5px; color: #288c69; }.traffic-child-table button > div:last-child strong { color: #288c69; }
.traffic-analysis-grid { display: grid; grid-template-columns: minmax(0, 1.45fr) minmax(300px, .55fr); gap: 14px; align-items: stretch; }.traffic-analysis-heading > div > span { display: block; margin-top: 6px; color: #98a39d; font-size: 9px; }.traffic-insight-list { display: grid; margin-top: 13px; }.traffic-insight-list button { display: grid; position: relative; min-height: 72px; grid-template-columns: minmax(0, 1fr) 18px; gap: 3px 8px; align-content: center; border: 0; border-bottom: 1px solid #edf1ef; padding: 10px 2px; background: transparent; text-align: left; }.traffic-insight-list button:hover strong { color: #288c69; }.traffic-insight-list span { color: #8f9b95; font-size: 9px; }.traffic-insight-list strong { overflow: hidden; color: #34493e; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }.traffic-insight-list small { color: #7c8982; font-size: 9px; }.traffic-insight-list svg { grid-column: 2; grid-row: 1 / span 3; align-self: center; color: #8ca49a; }
@media (max-width: 1360px) { .traffic-workspace-grid { grid-template-columns: 1fr; }.traffic-drilldown-panel { min-height: 0; }.traffic-child-table { max-height: 360px; } }
@media (max-width: 1180px) { .traffic-analysis-grid { grid-template-columns: 1fr; } }
@media (max-width: 900px) { .traffic-context-strip { align-items: flex-start; flex-direction: column; padding-block: 11px; }.traffic-context-strip > div { align-items: flex-start; }.traffic-context-strip span { white-space: normal; }.traffic-board-heading { align-items: flex-start; flex-direction: column; gap: 10px; }.traffic-sort-control { width: 100%; }.traffic-sort-control button { flex: 1; }.traffic-selected-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 760px) {
  .traffic-source-table { overflow: visible; }
  .traffic-source-head { display: none; }
  .traffic-source-row:not(.traffic-source-head) { min-width: 0; min-height: 86px; grid-template-columns: minmax(0, 1.35fr) minmax(66px, .7fr) minmax(66px, .7fr); grid-template-rows: auto auto; gap: 6px 8px; padding: 10px 4px; text-align: right; }
  .traffic-source-row:not(.traffic-source-head) > :first-child { grid-column: 1; grid-row: 1 / span 2; align-self: center; }
  .traffic-source-row:not(.traffic-source-head) > :nth-child(2) { grid-column: 2; grid-row: 1; }
  .traffic-source-row:not(.traffic-source-head) > :nth-child(3) { grid-column: 3; grid-row: 1; }
  .traffic-source-row:not(.traffic-source-head) > :nth-child(4) { grid-column: 2; grid-row: 2; }
  .traffic-source-row:not(.traffic-source-head) > :nth-child(5) { grid-column: 3; grid-row: 2; }
  .traffic-source-row:not(.traffic-source-head) > :nth-child(6) { display: none; }
  .traffic-source-row:not(.traffic-source-head) > :nth-child(2)::before { content: "访客 "; color: #98a39d; font-size: 8px; font-weight: 400; }
  .traffic-source-row:not(.traffic-source-head) > :nth-child(3)::before { content: "买家 "; color: #98a39d; font-size: 8px; font-weight: 400; }
  .traffic-source-row:not(.traffic-source-head) > :nth-child(4)::before { content: "转化 "; color: #98a39d; font-size: 8px; font-weight: 400; }
  .traffic-source-row:not(.traffic-source-head) > :nth-child(5)::before { content: "成交 "; color: #98a39d; font-size: 8px; font-weight: 400; }
  .traffic-source-name { grid-template-columns: minmax(0, 1fr); gap: 6px; }
  .traffic-source-name > div { width: 100%; }
  .traffic-selected-heading h2 { max-width: 185px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .traffic-child-table { max-height: none; }
}
</style>
