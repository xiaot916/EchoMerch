<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue"
import { LineChart } from "echarts/charts"
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components"
import { init, use } from "echarts/core"
import { CanvasRenderer } from "echarts/renderers"
import type { ECharts } from "echarts/core"

type Point = Record<string, string | number | null>

const props = defineProps<{
  items: Point[]
  series: Array<{ key: string; name: string; color: string; kind?: "currency" | "number" | "percent" }>
}>()

use([LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

const container = ref<HTMLDivElement>()
let chart: ECharts | undefined
let observer: ResizeObserver | undefined

function formatValue(value: number, kind: "currency" | "number" | "percent" = "number"): string {
  if (kind === "currency") return `¥ ${value.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}`
  if (kind === "percent") return `${value.toFixed(2)}%`
  return value.toLocaleString("zh-CN", { maximumFractionDigits: 0 })
}

function renderChart() {
  if (!container.value) return
  chart ??= init(container.value)
  const dates = props.items.map((item) => String(item.stat_date).slice(5))
  chart.setOption({
    animationDuration: 320,
    grid: { left: 46, right: 26, top: 42, bottom: 28, containLabel: true },
    legend: { top: 5, left: 46, itemWidth: 14, itemHeight: 7, textStyle: { color: "#6f8077", fontSize: 10 } },
    tooltip: {
      trigger: "axis",
      backgroundColor: "#fff",
      borderColor: "#dce8e1",
      textStyle: { color: "#33443b", fontSize: 11 },
      formatter: (params: Array<{ seriesName: string; value: number | null; marker: string; axisValue: string; seriesIndex: number }>) => {
        if (!params.length) return ""
        return `<strong>${params[0].axisValue}</strong><br/>${params.map((item) => {
          const definition = props.series[item.seriesIndex]
          return `${item.marker}${item.seriesName}：${item.value === null || item.value === undefined ? "未采集" : formatValue(Number(item.value), definition?.kind)}`
        }).join("<br/>")}`
      },
    },
    xAxis: { type: "category", boundaryGap: false, data: dates, axisLine: { lineStyle: { color: "#dfe8e3" } }, axisTick: { show: false }, axisLabel: { color: "#8b9891", fontSize: 9, interval: "auto", hideOverlap: true } },
    yAxis: { type: "value", splitLine: { lineStyle: { color: "#edf2ef", type: "dashed" } }, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: "#8b9891", fontSize: 9 } },
    series: props.series.map((definition) => ({ name: definition.name, type: "line", smooth: false, connectNulls: false, symbol: "none", lineStyle: { width: 2, color: definition.color }, itemStyle: { color: definition.color }, areaStyle: props.series.length === 1 ? { color: `${definition.color}18` } : undefined, data: props.items.map((item) => {
      const value = item[definition.key]
      return value === null || value === undefined || value === "" ? null : Number(value)
    }) })),
  }, true)
}

onMounted(() => {
  renderChart()
  if (container.value) {
    observer = new ResizeObserver(() => chart?.resize())
    observer.observe(container.value)
  }
})
watch(() => [props.items, props.series], renderChart, { deep: true })
onBeforeUnmount(() => { observer?.disconnect(); chart?.dispose() })
</script>

<template><div ref="container" class="marketing-trend-chart" aria-label="营销模块日趋势图"></div></template>
