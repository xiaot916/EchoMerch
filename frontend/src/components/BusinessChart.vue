<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
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

import { withChartTheme } from "@/lib/echartsTheme"

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
  /** Fallback height in px. Used when `aspect` is not set, or as the lower bound when it is. */
  height?: number
  /**
   * Responsive height mode: the container keeps this width/height ratio
   * (e.g. 16 / 7), clamped between `height` (min) and 3 × height (max).
   * Takes precedence over the fixed `height` when provided.
   */
  aspect?: number
}>(), { height: 320 })

const containerStyle = computed(() => {
  if (props.aspect) {
    return {
      aspectRatio: String(props.aspect),
      minHeight: `${props.height}px`,
      maxHeight: `${props.height * 3}px`,
    }
  }
  return { height: `${props.height}px` }
})

const container = ref<HTMLDivElement>()
let chart: ECharts | undefined
let observer: ResizeObserver | undefined

function renderChart(): void {
  if (!container.value) return
  chart ??= init(container.value)
  chart.setOption(withChartTheme(props.option), true)
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
    :style="containerStyle"
    role="img"
    :aria-label="ariaLabel"
  ></div>
</template>
