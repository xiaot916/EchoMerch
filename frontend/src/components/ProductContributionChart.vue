<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue"
import { BarChart } from "echarts/charts"
import { GridComponent, TooltipComponent } from "echarts/components"
import { init, use } from "echarts/core"
import { CanvasRenderer } from "echarts/renderers"
import type { ECharts } from "echarts/core"

import type { ProductMetric } from "@/types"

use([BarChart, GridComponent, TooltipComponent, CanvasRenderer])

const props = defineProps<{ items: ProductMetric[] }>()
const container = ref<HTMLDivElement>()
let chart: ECharts | undefined
let observer: ResizeObserver | undefined

function compactAmount(value: number): string {
  if (value >= 10000) return `${(value / 10000).toFixed(value >= 100000 ? 0 : 1)}万`
  return value.toLocaleString("zh-CN", { maximumFractionDigits: 0 })
}

function renderChart() {
  if (!container.value) return
  chart ??= init(container.value)
  const items = props.items.slice(0, 8).reverse()
  const names = items.map((item) => item.product_name || item.product_id)
  const values = items.map((item) => item.paid_amount)

  chart.setOption(
    {
      animationDuration: 350,
      grid: { left: 8, right: 30, top: 8, bottom: 8, containLabel: true },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        backgroundColor: "#ffffff",
        borderColor: "#dce8e1",
        textStyle: { color: "#2f4037", fontSize: 12 },
        formatter: (params: Array<{ dataIndex: number; value: number }>) => {
          const item = items[params[0]?.dataIndex]
          if (!item) return ""
          const conversion = item.visitors ? (item.buyers / item.visitors) * 100 : 0
          return `<strong>${item.product_name || item.product_id}</strong><br/>支付金额：¥ ${item.paid_amount.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}<br/>访客：${item.visitors.toLocaleString("zh-CN")}　买家：${item.buyers.toLocaleString("zh-CN")}<br/>转化率：${conversion.toFixed(2)}%`
        },
      },
      xAxis: {
        type: "value",
        splitLine: { lineStyle: { color: "#edf2ef", type: "dashed" } },
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: "#8b9992", fontSize: 10, formatter: (value: number) => compactAmount(value) },
      },
      yAxis: {
        type: "category",
        data: names,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: "#52635a",
          fontSize: 11,
          width: 190,
          overflow: "truncate",
          ellipsis: "…",
        },
      },
      series: [
        {
          name: "支付金额",
          type: "bar",
          barMaxWidth: 18,
          showBackground: true,
          backgroundStyle: { color: "#f1f6f3", borderRadius: 3 },
          itemStyle: { color: "#16845b", borderRadius: [0, 4, 4, 0] },
          label: { show: true, position: "right", color: "#16845b", fontSize: 10, formatter: (params: { value: number }) => compactAmount(params.value) },
          data: values,
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

watch(() => props.items, renderChart, { deep: true })

onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
})
</script>

<template>
  <div ref="container" class="product-contribution-chart" aria-label="商品支付金额贡献图"></div>
</template>
