<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue"
import { LineChart } from "echarts/charts"
import { GridComponent, MarkAreaComponent, TooltipComponent } from "echarts/components"
import { init, use } from "echarts/core"
import { CanvasRenderer } from "echarts/renderers"
import type { ECharts } from "echarts/core"
import type { DailyMetric } from "@/types"
import type { StoreActivityCalendarEvent } from "@/types"

use([LineChart, GridComponent, MarkAreaComponent, TooltipComponent, CanvasRenderer])

const props = withDefaults(defineProps<{ metrics: DailyMetric[]; activities?: StoreActivityCalendarEvent[] }>(), { activities: () => [] })
const container = ref<HTMLDivElement>()
let chart: ECharts | undefined
let observer: ResizeObserver | undefined

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("zh-CN", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value)
}

function renderChart() {
  if (!container.value) return
  chart ??= init(container.value)
  const firstDay = props.metrics[0]?.stat_date || ""
  const lastDay = props.metrics[props.metrics.length - 1]?.stat_date || ""
  const activityAreas = props.activities.flatMap((activity) => {
    const rawStart = (activity.activity_start_time || activity.business_day).slice(0, 10)
    const rawEnd = (activity.activity_end_time || activity.activity_start_time || activity.business_day).slice(0, 10)
    const start = rawStart < firstDay ? firstDay : rawStart
    const end = rawEnd > lastDay ? lastDay : rawEnd
    if (!start || !end || start > end) return []
    return [[
      { name: activity.activity_name || "活动", xAxis: start.slice(5) },
      { xAxis: end.slice(5) },
    ]]
  })
  chart.setOption(
    {
      animationDuration: 400,
      grid: { left: 10, right: 14, top: 22, bottom: 8, containLabel: true },
      tooltip: {
        trigger: "axis",
        backgroundColor: "#ffffff",
        borderColor: "#d9e6de",
        textStyle: { color: "#344054" },
        axisPointer: { type: "line", lineStyle: { color: "#35b987", opacity: 0.35 } },
        valueFormatter: (value: number) => `¥ ${value.toLocaleString("zh-CN")}`,
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: props.metrics.map((item) => item.stat_date.slice(5)),
        axisLine: { lineStyle: { color: "#dfe7e2" } },
        axisTick: { show: false },
        axisLabel: { color: "#8c9aa7", fontSize: 11, interval: "auto" },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: "#e8efeb", type: "dashed" } },
        axisLabel: { color: "#8c9aa7", formatter: (value: number) => formatCurrency(value) },
      },
      series: [
        {
          name: "支付金额",
          type: "line",
          smooth: true,
          symbol: "none",
          lineStyle: { color: "#35b987", width: 2.5 },
          areaStyle: { color: "rgba(53, 185, 135, 0.14)" },
          data: props.metrics.map((item) => item.paid_amount),
          markArea: activityAreas.length ? {
            silent: false,
            itemStyle: { color: "rgba(73, 114, 218, 0.08)", borderColor: "rgba(73, 114, 218, 0.18)", borderWidth: 1 },
            label: { show: props.metrics.length <= 14, color: "#5270b8", fontSize: 9, overflow: "truncate" },
            data: activityAreas,
          } : undefined,
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

watch(() => props.metrics, renderChart, { deep: true })

onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
})
</script>

<template>
  <div ref="container" class="trend-chart" aria-label="支付金额趋势图"></div>
</template>
