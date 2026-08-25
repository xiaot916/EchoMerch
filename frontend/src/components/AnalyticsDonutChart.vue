<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue"
import { LegendComponent, TooltipComponent } from "echarts/components"
import { PieChart } from "echarts/charts"
import { init, use } from "echarts/core"
import { CanvasRenderer } from "echarts/renderers"
import type { ECharts } from "echarts/core"

use([PieChart, LegendComponent, TooltipComponent, CanvasRenderer])

const props = withDefaults(defineProps<{ items: Array<{ name: string; value: number }>; theme?: "dark" | "light" }>(), { theme: "dark" })
const container = ref<HTMLDivElement>()
let chart: ECharts | undefined
let observer: ResizeObserver | undefined

function renderChart() {
  if (!container.value) return
  chart ??= init(container.value)
  const isLight = props.theme === "light"
  chart.setOption(
    {
      color: ["#63d9b8", "#83b6ef", "#f0bd76", "#c48be8", "#e98d8d", "#8e9ca4"],
      tooltip: {
        trigger: "item",
        backgroundColor: isLight ? "#ffffff" : "#182126",
        borderColor: isLight ? "#d8dee6" : "#35464d",
        textStyle: { color: isLight ? "#222b36" : "#eef8f4" },
        formatter: (params: { name: string; value: number; percent: number }) => `${params.name}<br/>¥ ${params.value.toLocaleString("zh-CN", { maximumFractionDigits: 2 })} · ${params.percent.toFixed(1)}%`,
      },
      legend: { bottom: 0, left: "center", itemWidth: 8, itemHeight: 8, textStyle: { color: isLight ? "#687382" : "#9baab0", fontSize: 11 } },
      series: [{ type: "pie", radius: ["48%", "73%"], center: ["50%", "43%"], avoidLabelOverlap: true, label: { show: false }, data: props.items }],
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

<template><div ref="container" class="analytics-donut-chart" aria-label="流量来源分布图"></div></template>
