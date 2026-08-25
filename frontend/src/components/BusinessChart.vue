<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue"
import { BarChart, FunnelChart, LineChart, PieChart, ScatterChart } from "echarts/charts"
import {
  DatasetComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TitleComponent,
  TooltipComponent,
  TransformComponent,
} from "echarts/components"
import { init, use } from "echarts/core"
import { CanvasRenderer } from "echarts/renderers"
import type { ECharts, EChartsCoreOption } from "echarts/core"

use([
  BarChart,
  FunnelChart,
  LineChart,
  PieChart,
  ScatterChart,
  DatasetComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TitleComponent,
  TooltipComponent,
  TransformComponent,
  CanvasRenderer,
])

const props = withDefaults(defineProps<{
  option: EChartsCoreOption
  ariaLabel: string
  height?: number
}>(), { height: 320 })

const container = ref<HTMLDivElement>()
let chart: ECharts | undefined
let observer: ResizeObserver | undefined

function renderChart(): void {
  if (!container.value) return
  chart ??= init(container.value)
  chart.setOption(props.option, true)
}

onMounted(() => {
  renderChart()
  if (!container.value) return
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(container.value)
})

watch(() => props.option, renderChart, { deep: true })

onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
})
</script>

<template>
  <div
    ref="container"
    class="business-chart"
    :style="{ height: `${height}px` }"
    role="img"
    :aria-label="ariaLabel"
  ></div>
</template>
