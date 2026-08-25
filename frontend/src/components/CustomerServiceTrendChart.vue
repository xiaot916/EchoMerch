<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue"
import { LineChart } from "echarts/charts"
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components"
import { init, use } from "echarts/core"
import { CanvasRenderer } from "echarts/renderers"
import type { ECharts } from "echarts/core"

import type { CustomerServiceDailyMetric } from "@/types"

use([LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

const props = defineProps<{ metrics: CustomerServiceDailyMetric[] }>()
const container = ref<HTMLDivElement>()
let chart: ECharts | undefined
let observer: ResizeObserver | undefined

function compactNumber(value: number): string {
  if (value >= 10000) return `${(value / 10000).toFixed(1)}万`
  return value.toLocaleString("zh-CN", { maximumFractionDigits: 0 })
}

function renderChart() {
  if (!container.value) return
  chart ??= init(container.value)
  const dates = props.metrics.map((item) => item.stat_date.slice(5))

  chart.setOption(
    {
      animationDuration: 350,
      color: ["#16845b", "#6e9b83", "#4f77c8", "#c28a2f", "#8b63b8"],
      tooltip: {
        trigger: "axis",
        backgroundColor: "#ffffff",
        borderColor: "#dce8e1",
        textStyle: { color: "#33443b", fontSize: 11 },
        axisPointer: { type: "line", lineStyle: { color: "#8ebea8", opacity: 0.4 } },
        formatter: (params: Array<{ seriesName: string; value: number; axisValue: string; seriesIndex: number; marker: string }>) => {
          if (!params.length) return ""
          const lines = params.map((item) => {
            const value = item.seriesIndex === 0 || item.seriesIndex === 1
              ? `¥ ${Number(item.value).toLocaleString("zh-CN", { maximumFractionDigits: 2 })}`
              : item.seriesIndex === 2
                ? `${Number(item.value).toLocaleString("zh-CN")} 人`
                : item.seriesIndex === 3
                  ? `${Number(item.value).toFixed(1)} 秒`
                  : `${Number(item.value).toFixed(2)}%`
            return `${item.marker}${item.seriesName}：${value}`
          })
          return `<strong>${params[0].axisValue}</strong><br/>${lines.join("<br/>")}`
        },
      },
      legend: [
        { data: ["客服销售额", "客服净销售额", "咨询用户"], top: 2, left: 48, itemWidth: 14, itemHeight: 7, textStyle: { color: "#66776e", fontSize: 10 } },
        { data: ["平均响应", "满意率"], top: "53%", left: 48, itemWidth: 14, itemHeight: 7, textStyle: { color: "#66776e", fontSize: 10 } },
      ],
      grid: [
        { left: 54, right: 58, top: 36, height: "34%" },
        { left: 54, right: 58, top: "61%", height: "27%" },
      ],
      xAxis: [
        { type: "category", gridIndex: 0, boundaryGap: false, data: dates, axisLine: { lineStyle: { color: "#dfe8e3" } }, axisTick: { show: false }, axisLabel: { show: false } },
        { type: "category", gridIndex: 1, boundaryGap: false, data: dates, axisLine: { lineStyle: { color: "#dfe8e3" } }, axisTick: { show: false }, axisLabel: { color: "#8b9891", fontSize: 9, interval: "auto", hideOverlap: true } },
      ],
      yAxis: [
        { type: "value", gridIndex: 0, name: "销售额", nameTextStyle: { color: "#86948c", fontSize: 9 }, splitLine: { lineStyle: { color: "#edf2ef", type: "dashed" } }, axisLabel: { color: "#8b9891", fontSize: 9, formatter: (value: number) => compactNumber(value) } },
        { type: "value", gridIndex: 0, name: "咨询", nameTextStyle: { color: "#86948c", fontSize: 9 }, splitLine: { show: false }, axisLabel: { color: "#8b9891", fontSize: 9, formatter: (value: number) => compactNumber(value) } },
        { type: "value", gridIndex: 1, name: "响应(秒)", nameTextStyle: { color: "#86948c", fontSize: 9 }, splitLine: { lineStyle: { color: "#edf2ef", type: "dashed" } }, axisLabel: { color: "#8b9891", fontSize: 9 } },
        { type: "value", gridIndex: 1, min: 0, max: 100, name: "满意率", nameTextStyle: { color: "#86948c", fontSize: 9 }, splitLine: { show: false }, axisLabel: { color: "#8b9891", fontSize: 9, formatter: "{value}%" } },
      ],
      series: [
        { name: "客服销售额", type: "line", xAxisIndex: 0, yAxisIndex: 0, smooth: true, symbol: "none", lineStyle: { width: 2.4 }, areaStyle: { color: "rgba(22, 132, 91, .10)" }, data: props.metrics.map((item) => item.sales_amount) },
        { name: "客服净销售额", type: "line", xAxisIndex: 0, yAxisIndex: 0, smooth: true, symbol: "none", lineStyle: { width: 1.7, type: "dashed" }, data: props.metrics.map((item) => item.net_sales_amount) },
        { name: "咨询用户", type: "line", xAxisIndex: 0, yAxisIndex: 1, smooth: true, symbol: "none", lineStyle: { width: 2 }, data: props.metrics.map((item) => item.consult_users) },
        { name: "平均响应", type: "line", xAxisIndex: 1, yAxisIndex: 2, smooth: true, symbol: "none", lineStyle: { width: 2 }, data: props.metrics.map((item) => item.avg_reply_seconds) },
        { name: "满意率", type: "line", xAxisIndex: 1, yAxisIndex: 3, smooth: true, symbol: "none", lineStyle: { width: 2 }, data: props.metrics.map((item) => item.satisfaction_rate) },
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
  <div ref="container" class="customer-service-trend-chart" aria-label="客服销售、咨询、响应和满意率趋势图"></div>
</template>
