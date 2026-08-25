<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import * as echarts from "echarts"
import "echarts-wordcloud"

const props = withDefaults(defineProps<{
  items: Array<{ name: string; count: number }>
  ariaLabel: string
  height?: number
  tone?: "issue" | "competitor"
}>(), { height: 290, tone: "issue" })

const emit = defineEmits<{
  select: [name: string]
}>()

const container = ref<HTMLDivElement>()
let chart: echarts.ECharts | undefined
let observer: ResizeObserver | undefined

const palette = computed(() => props.tone === "competitor"
  ? ["#4f77c8", "#16845b", "#c37c3a", "#7d62a8", "#3f8f99", "#9a6d45"]
  : ["#b75a4f", "#c37c3a", "#16845b", "#4f77c8", "#8a6b3f", "#7d62a8"])

function renderChart(): void {
  if (!container.value) return
  chart ??= echarts.init(container.value)
  const values = props.items.map((item) => item.count)
  const min = Math.min(...values, 1)
  const max = Math.max(...values, 1)
  chart.setOption({
    tooltip: {
      trigger: "item",
      formatter: (params: { name?: string; value?: number }) => `${params.name || ""}<br/>出现 ${Number(params.value || 0).toLocaleString("zh-CN")} 条`,
    },
    series: [{
      type: "wordCloud",
      shape: "circle",
      left: "center",
      top: "center",
      width: "96%",
      height: "94%",
      gridSize: 9,
      sizeRange: [15, 46],
      rotationRange: [0, 0],
      drawOutOfBound: false,
      layoutAnimation: true,
      emphasis: { textStyle: { shadowBlur: 6, shadowColor: "rgba(33, 62, 48, .22)" } },
      data: props.items.map((item, index) => ({
        name: item.name,
        value: item.count,
        textStyle: {
          color: palette.value[index % palette.value.length],
          fontWeight: item.count >= max * .5 ? 700 : item.count <= min ? 500 : 620,
        },
      })),
    }],
  }, true)
  chart.off("click")
  chart.on("click", (params) => {
    if (params.name) emit("select", params.name)
  })
}

onMounted(() => {
  renderChart()
  if (!container.value) return
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(container.value)
})

watch(() => props.items, renderChart, { deep: true })

onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
})
</script>

<template>
  <div ref="container" class="review-word-cloud" :style="{ height: `${height}px` }" role="img" :aria-label="ariaLabel"></div>
</template>
