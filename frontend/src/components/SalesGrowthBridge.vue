<script setup lang="ts">
import { computed } from "vue"
import { AlertTriangle, TrendingDown, TrendingUp } from "lucide-vue-next"

import BusinessChart from "@/components/BusinessChart.vue"
import { buildSalesGrowthBridge, percentageDelta, type SalesBridgeInput } from "@/lib/businessDecision"
import { currency, number, ratio } from "@/lib/format"

const props = withDefaults(defineProps<{
  current: SalesBridgeInput
  previous: SalesBridgeInput
  comparable?: boolean
  height?: number
}>(), {
  comparable: true,
  height: 300,
})

const bridge = computed(() => buildSalesGrowthBridge(props.current, props.previous))
const strongestDriver = computed(() => bridge.value.drivers.slice().sort((left, right) => Math.abs(right.contribution) - Math.abs(left.contribution))[0])

function driverValue(key: SalesBridgeInput extends never ? never : string, value: number): string {
  if (key === "conversion") return ratio(value)
  if (key === "unitPrice") return currency(value)
  return number(value)
}

function changeLabel(current: number, previous: number): string {
  const value = percentageDelta(current, previous)
  if (value === null) return "暂无基期"
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`
}

const chartOption = computed(() => {
  const items = [
    { label: "上一周期", value: bridge.value.previousPaidAmount, total: true, contribution: bridge.value.previousPaidAmount },
    ...bridge.value.drivers.map((item) => ({ label: item.label, value: item.contribution, total: false, contribution: item.contribution })),
    { label: "本周期", value: bridge.value.currentPaidAmount, total: true, contribution: bridge.value.currentPaidAmount },
  ]
  let running = bridge.value.previousPaidAmount
  const base: number[] = [0]
  const values: Array<{ value: number; itemStyle: { color: string } }> = [{ value: bridge.value.previousPaidAmount, itemStyle: { color: "#6d87b8" } }]
  for (const driver of bridge.value.drivers) {
    const next = running + driver.contribution
    base.push(driver.contribution >= 0 ? running : next)
    values.push({ value: Math.abs(driver.contribution), itemStyle: { color: driver.contribution >= 0 ? "#2a9a70" : "#c96b58" } })
    running = next
  }
  base.push(0)
  values.push({ value: bridge.value.currentPaidAmount, itemStyle: { color: "#237f5e" } })
  return {
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (params: Array<{ dataIndex: number }>) => {
        const item = items[params[0]?.dataIndex ?? 0]
        if (!item) return ""
        return item.total
          ? `${item.label}<br/>支付金额 ${currency(item.value)}`
          : `${item.label}<br/>金额贡献 ${item.contribution >= 0 ? "+" : ""}${currency(item.contribution)}`
      },
    },
    grid: { left: 70, right: 24, top: 28, bottom: 44 },
    xAxis: { type: "category", data: items.map((item) => item.label), axisLabel: { color: "#75867d", fontSize: 10 } },
    yAxis: { type: "value", axisLabel: { formatter: (value: number) => `${Math.round(value / 10000)}万`, color: "#8c9991" }, splitLine: { lineStyle: { color: "#edf2ef" } } },
    series: [
      { type: "bar", stack: "bridge", silent: true, itemStyle: { color: "transparent" }, emphasis: { itemStyle: { color: "transparent" } }, data: base },
      { type: "bar", stack: "bridge", barMaxWidth: 44, label: { show: true, position: "top", color: "#52665a", fontSize: 9, formatter: (params: { dataIndex: number }) => { const item = items[params.dataIndex]; return item?.total ? currency(item.value) : `${item && item.contribution >= 0 ? "+" : ""}${currency(item?.contribution ?? 0)}` } }, data: values },
    ],
  }
})
</script>

<template>
  <div class="sales-growth-bridge">
    <div class="sales-growth-summary" :class="{ warning: !comparable }">
      <AlertTriangle v-if="!comparable" :size="16" />
      <component :is="bridge.delta >= 0 ? TrendingUp : TrendingDown" v-else :size="16" />
      <div>
        <strong>{{ bridge.delta >= 0 ? "支付金额增长" : "支付金额下降" }} {{ currency(Math.abs(bridge.delta)) }}</strong>
        <span v-if="comparable">最大金额驱动：{{ strongestDriver?.label }} {{ strongestDriver && strongestDriver.contribution >= 0 ? "+" : "" }}{{ currency(strongestDriver?.contribution ?? 0) }}</span>
        <span v-else>当前日报覆盖不完整，贡献桥仅作方向排查，不作严格周期结论。</span>
      </div>
    </div>
    <BusinessChart :option="chartOption" ariaLabel="支付金额增长贡献桥" :height="height" />
    <div class="sales-driver-strip">
      <div v-for="item in bridge.drivers" :key="item.key">
        <span>{{ item.label }}</span>
        <strong :class="item.contribution >= 0 ? 'positive' : 'negative'">{{ item.contribution >= 0 ? "+" : "" }}{{ currency(item.contribution) }}</strong>
        <small>{{ driverValue(item.key, item.currentValue) }} · {{ changeLabel(item.currentValue, item.previousValue) }}</small>
      </div>
    </div>
    <p>金额贡献采用顺序替代法：先按访客、再按支付转化率，剩余归入支付买家客单价与商品结构；三项与支付金额变化严格对账，不能直接相加解释为互斥订单来源。</p>
  </div>
</template>

<style scoped>
.sales-growth-bridge { min-width: 0; }
.sales-growth-summary { display: flex; align-items: center; gap: 9px; margin: 12px 14px 0; border-left: 3px solid #258d69; padding: 7px 10px; color: #2b8463; background: #f4faf7; }.sales-growth-summary.warning { border-left-color: #d49a38; color: #966b24; background: #fff9ee; }.sales-growth-summary > div { display: grid; gap: 3px; }.sales-growth-summary strong { color: #344d40; font-size: 11px; }.sales-growth-summary span { color: #75877d; font-size: 9px; line-height: 1.45; }
.sales-driver-strip { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1px; margin: 0 14px; overflow: hidden; border: 1px solid #e1e9e4; border-radius: 5px; background: #e1e9e4; }.sales-driver-strip > div { display: grid; min-width: 0; gap: 4px; padding: 9px 10px; background: #fbfdfc; }.sales-driver-strip span { color: #7f8f86; font-size: 8px; }.sales-driver-strip strong { overflow: hidden; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }.sales-driver-strip strong.positive { color: #17805a; }.sales-driver-strip strong.negative { color: #bd624f; }.sales-driver-strip small { color: #8d9a93; font-size: 8px; }
.sales-growth-bridge > p { margin: 9px 14px 0; color: #89968f; font-size: 8px; line-height: 1.55; }
@media (max-width: 620px) { .sales-driver-strip { grid-template-columns: 1fr; }.sales-growth-summary { align-items: flex-start; } }
</style>
