<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue"
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components"
import { LineChart } from "echarts/charts"
import { init, use } from "echarts/core"
import { CanvasRenderer } from "echarts/renderers"
import type { ECharts } from "echarts/core"

use([LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

export interface TrendPoint {
  date: string
  value: number | null
}

const props = withDefaults(
  defineProps<{
    points: TrendPoint[]
    label: string
    color?: string
    kind?: "currency" | "number" | "percent"
    theme?: "dark" | "light"
  }>(),
  { color: "#63d9b8", kind: "currency", theme: "dark" },
)

const container = ref<HTMLDivElement>()
let chart: ECharts | undefined
let observer: ResizeObserver | undefined

function display(value: number | null) {
  if (value === null) return "--"
  if (props.kind === "percent") return `${value.toFixed(2)}%`
  if (props.kind === "currency") return `¥ ${value.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}`
  return value.toLocaleString("zh-CN", { maximumFractionDigits: 0 })
}

function renderChart() {
  if (!container.value) return
  chart ??= init(container.value)
  const isLight = props.theme === "light"
  const axis = isLight ? "#ccd3dd" : "#334149"
  const label = isLight ? "#6d7784" : "#8fa0a7"
  const split = isLight ? "#e2e6eb" : "#2b373d"
  chart.setOption(
    {
      animationDuration: 260,
      grid: { left: 10, right: 18, top: 26, bottom: 10, containLabel: true },
      tooltip: {
        trigger: "axis",
        backgroundColor: isLight ? "#ffffff" : "#182126",
        borderColor: isLight ? "#d8dee6" : "#35464d",
        textStyle: { color: isLight ? "#222b36" : "#eef8f4" },
        extraCssText: isLight ? "box-shadow: 0 8px 22px rgba(31, 42, 55, 0.12);" : "",
        valueFormatter: (value: number) => display(value),
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: props.points.map((item) => item.date.slice(5)),
        axisLine: { lineStyle: { color: axis } },
        axisTick: { show: false },
        axisLabel: { color: label, fontSize: 11, interval: "auto" },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: split, type: "dashed" } },
        axisLabel: { color: label, formatter: (value: number) => display(value) },
      },
      series: [
        {
          name: props.label,
          type: "line",
          smooth: 0.25,
          showSymbol: props.points.length <= 8,
          symbol: "circle",
          symbolSize: props.points.length === 1 ? 10 : 6,
          lineStyle: { color: props.color, width: 2.5 },
          itemStyle: { color: props.color, borderColor: "#fff", borderWidth: 2 },
          areaStyle: { color: `${props.color}20` },
          data: props.points.map((item) => item.value),
        },
      ],
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

watch(() => [props.points, props.label, props.color, props.kind, props.theme], renderChart, { deep: true })

onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
})
</script>

<template>
  <div ref="container" class="analytics-trend-chart" :aria-label="`${label}趋势图`"></div>
</template>
