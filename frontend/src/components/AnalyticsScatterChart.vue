<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue"
import { GridComponent, TooltipComponent } from "echarts/components"
import { ScatterChart } from "echarts/charts"
import { init, use } from "echarts/core"
import { CanvasRenderer } from "echarts/renderers"
import type { ECharts } from "echarts/core"

use([ScatterChart, GridComponent, TooltipComponent, CanvasRenderer])

const props = withDefaults(defineProps<{ items: Array<{ name: string; spend: number; paid: number; buyers: number }>; theme?: "dark" | "light" }>(), { theme: "dark" })
const container = ref<HTMLDivElement>()
let chart: ECharts | undefined
let observer: ResizeObserver | undefined

function renderChart() {
  if (!container.value) return
  chart ??= init(container.value)
  const isLight = props.theme === "light"
  const label = isLight ? "#6d7784" : "#8fa0a7"
  const split = isLight ? "#e2e6eb" : "#2b373d"
  chart.setOption(
    {
      grid: { left: 10, right: 18, top: 18, bottom: 10, containLabel: true },
      xAxis: { type: "value", name: "花费", nameTextStyle: { color: label, fontSize: 10 }, axisLabel: { color: label, fontSize: 10 }, splitLine: { lineStyle: { color: split, type: "dashed" } } },
      yAxis: { type: "value", name: "成交金额", nameTextStyle: { color: label, fontSize: 10 }, axisLabel: { color: label, fontSize: 10 }, splitLine: { lineStyle: { color: split, type: "dashed" } } },
      tooltip: {
        trigger: "item",
        backgroundColor: isLight ? "#ffffff" : "#182126",
        borderColor: isLight ? "#d8dee6" : "#35464d",
        textStyle: { color: isLight ? "#222b36" : "#eef8f4" },
        formatter: (params: { data: [number, number, number, string] }) => `${params.data[3]}<br/>花费 ¥ ${params.data[0].toLocaleString("zh-CN", { maximumFractionDigits: 2 })}<br/>成交 ¥ ${params.data[1].toLocaleString("zh-CN", { maximumFractionDigits: 2 })}<br/>成交人数 ${params.data[2].toLocaleString("zh-CN")}`,
      },
      series: [{ type: "scatter", symbolSize: (value: [number, number, number]) => Math.max(10, Math.min(30, Math.sqrt(value[2] || 1) * 3)), itemStyle: { color: "#f0bd76", opacity: 0.85 }, data: props.items.map((item) => [item.spend, item.paid, item.buyers, item.name]) }],
    },
    true,
  )
}

onMounted(() => {
  renderChart()
  if (container.value) {
    observer = new ResizeObserver(() => chart?.resize())
    observer.observe(container.value)
  }
})
watch(() => [props.items, props.theme], renderChart, { deep: true })
onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
})
</script>

<template><div ref="container" class="analytics-scatter-chart" aria-label="推广计划投入产出散点图"></div></template>
