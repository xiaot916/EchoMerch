<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import { ArrowLeft, ArrowRight, BarChart3, CircleDollarSign, Percent, RefreshCw, Search, ShoppingBag, UsersRound } from "lucide-vue-next"
import { useRoute } from "vue-router"

import EmptyState from "@/components/EmptyState.vue"
import MarketingTrendChart from "@/components/MarketingTrendChart.vue"
import MetricCard from "@/components/MetricCard.vue"
import { fetchBybtProductItems, fetchStores } from "@/api"
import { useDashboard } from "@/composables/useDashboard"
import { currency, number, ratio } from "@/lib/format"
import type { PromotionProductMetric } from "@/types"

const { dashboard, ensureDashboard } = useDashboard()
const route = useRoute()
const routeName = computed(() => String(route.name).endsWith("bybt") ? "bybt" : "shopping_gold")
const isBybt = computed(() => routeName.value === "bybt")
const title = computed(() => isBybt.value ? "百亿补贴" : "购物金")
const eyebrow = computed(() => isBybt.value ? "营销活动 / 百补经营" : "营销活动 / 购物金经营")
const snapshot = computed(() => {
  const analysis = dashboard.value?.analysis
  return isBybt.value ? analysis?.bybt : analysis?.shopping_gold
})
const value = computed<Record<string, any>>(() => (snapshot.value || {}) as Record<string, any>)
const daily = computed(() => (value.value.daily_metrics || []) as Array<Record<string, string | number | null>>)
const hasData = computed(() => Boolean(snapshot.value && Number(value.value.covered_days ?? daily.value.length) > 0))
const bybtItems = ref<PromotionProductMetric[]>([])
const bybtItemsCoverage = ref<{
  range_start: string
  range_end: string
  available_start: string | null
  available_end: string | null
  missing_dates: string[]
} | null>(null)
const bybtItemsLoading = ref(false)
const bybtItemsError = ref("")
const bybtSearch = ref("")
const bybtSort = ref<"paid_amount" | "paid_order_count" | "visitors">("paid_amount")
const bybtPage = ref(1)
const bybtPageSize = ref(50)
const dailyPage = ref(1)
const dailyPageSize = ref(10)

const kpis = computed(() => {
  const current = value.value
  if (!snapshot.value) return []
  if (isBybt.value) return [
    { label: "百补支付金额", value: currency(current.paid_amount), detail: `${number(current.paid_buyers)} 位支付买家`, icon: CircleDollarSign, tone: "teal" as const },
    { label: "百补访客", value: number(current.visitors), detail: "按日访客累计", icon: UsersRound, tone: "blue" as const },
    { label: "支付转化率", value: ratio(current.conversion_rate), detail: "支付买家 / 百补访客", icon: Percent, tone: "amber" as const },
    { label: "支付件单", value: current.items_per_buyer.toFixed(2), detail: `${number(current.paid_items)} 件支付成交`, icon: ShoppingBag, tone: "coral" as const },
  ]
  return [
    { label: "购物金充值金额", value: currency(current.recharge_amount), detail: `${number(current.recharge_buyers)} 位充值买家`, icon: CircleDollarSign, tone: "teal" as const },
    { label: "购物金支付金额", value: currency(current.paid_amount), detail: `${number(current.paid_buyers)} 位支付买家`, icon: ShoppingBag, tone: "blue" as const },
    { label: "充值转化率", value: ratio(current.recharge_rate), detail: `${number(current.product_visitors)} 位商品访客`, icon: Percent, tone: "amber" as const },
    { label: "充值退款金额", value: currency(current.recharge_refund_amount), detail: `人均充值 ${currency(current.average_recharge_amount)}`, icon: BarChart3, tone: "coral" as const },
  ]
})

const chartItems = daily
const chartSeries = computed(() => isBybt.value
  ? [{ key: "paid_amount", name: "支付金额", color: "#16845b", kind: "currency" as const }]
  : [{ key: "recharge_amount", name: "充值金额", color: "#16845b", kind: "currency" as const }, { key: "paid_amount", name: "支付金额", color: "#4f77c8", kind: "currency" as const }])
const orderedDaily = computed(() => [...daily.value].reverse())
const dailyPageCount = computed(() => Math.max(1, Math.ceil(orderedDaily.value.length / dailyPageSize.value)))
const pagedDaily = computed(() => orderedDaily.value.slice((dailyPage.value - 1) * dailyPageSize.value, dailyPage.value * dailyPageSize.value))
const dailyPageStart = computed(() => orderedDaily.value.length ? (dailyPage.value - 1) * dailyPageSize.value + 1 : 0)
const dailyPageEnd = computed(() => Math.min(dailyPage.value * dailyPageSize.value, orderedDaily.value.length))

function metric(item: Record<string, string | number | null>, key: string): number | null {
  const valueToFormat = item[key]
  return valueToFormat === null || valueToFormat === undefined || valueToFormat === "" ? null : Number(valueToFormat)
}

function metricText(item: Record<string, string | number | null>, key: string, formatter: (value: number) => string): string {
  const valueToFormat = metric(item, key)
  return valueToFormat === null ? "未采集" : formatter(valueToFormat)
}

function shortDate(valueToFormat: string | null | undefined): string {
  if (!valueToFormat) return "暂无"
  const [, month, day] = valueToFormat.split("-")
  return `${Number(month)}月${Number(day)}日`
}

function dateRangeLabel(start: string | null | undefined, end: string | null | undefined): string {
  if (!start || !end) return "暂无可用日期"
  return `${shortDate(start)}至${shortDate(end)}`
}

async function loadBybtItems(): Promise<void> {
  if (!isBybt.value || !dashboard.value) return
  bybtItemsLoading.value = true
  bybtItemsError.value = ""
  try {
    const store = (await fetchStores())[0]
    if (!store) return
    const rows: PromotionProductMetric[] = []
    let coverage: typeof bybtItemsCoverage.value = null
    let page = 1
    while (true) {
      const payload = await fetchBybtProductItems(
        dashboard.value.range_start,
        dashboard.value.range_end,
        store.store_id,
        undefined,
        page,
        100,
        "paid_amount",
      )
      coverage ??= {
        range_start: payload.range_start,
        range_end: payload.range_end,
        available_start: payload.available_start,
        available_end: payload.available_end,
        missing_dates: payload.missing_dates,
      }
      rows.push(...payload.items)
      if (rows.length >= payload.total || payload.items.length < payload.page_size) break
      page += 1
    }
    bybtItems.value = rows
    bybtItemsCoverage.value = coverage
    bybtPage.value = 1
  } catch (requestError) {
    bybtItems.value = []
    bybtItemsCoverage.value = null
    bybtItemsError.value = requestError instanceof Error ? requestError.message : "商品明细读取失败"
  } finally {
    bybtItemsLoading.value = false
  }
}

const searchedBybtItems = computed(() => {
  const term = bybtSearch.value.trim().toLowerCase()
  const rows = term
    ? bybtItems.value.filter((item) => `${item.product_id} ${item.product_name} ${item.category_name}`.toLowerCase().includes(term))
    : bybtItems.value
  return [...rows].sort((left, right) => (Number(right[bybtSort.value] ?? 0) - Number(left[bybtSort.value] ?? 0)) || left.product_id.localeCompare(right.product_id))
})
const bybtPageCount = computed(() => Math.max(1, Math.ceil(searchedBybtItems.value.length / bybtPageSize.value)))
const pagedBybtItems = computed(() => searchedBybtItems.value.slice((bybtPage.value - 1) * bybtPageSize.value, bybtPage.value * bybtPageSize.value))
const bybtAmountTotal = computed(() => bybtItems.value.reduce((total, item) => total + (item.paid_amount ?? 0), 0))
const bybtReconcileRate = computed(() => {
  const coverage = bybtItemsCoverage.value
  const expectedDays = Number(value.value.expected_days ?? daily.value.length)
  const coveredDays = Number(value.value.covered_days ?? 0)
  const sameRequestedRange = coverage
    && coverage.range_start === dashboard.value?.range_start
    && coverage.range_end === dashboard.value?.range_end
  if (!coverage || !sameRequestedRange || coverage.missing_dates.length || coveredDays !== expectedDays || !value.value.paid_amount) return null
  return bybtAmountTotal.value / Number(value.value.paid_amount) * 100
})
const dailyHeading = computed(() => isBybt.value
  ? `已覆盖${Number(value.value.covered_days ?? 0)}/${Number(value.value.expected_days ?? daily.value.length)}天`
  : `${daily.value.length} 个统计日`)
const bybtItemsRangeLabel = computed(() => {
  const coverage = bybtItemsCoverage.value
  return coverage ? `商品明细覆盖 ${dateRangeLabel(coverage.range_start, coverage.range_end)}` : "商品明细暂无可用日期"
})
const bybtCategories = computed(() => {
  const grouped = new Map<string, number>()
  for (const item of bybtItems.value) {
    const key = item.category_name || "未分类"
    grouped.set(key, (grouped.get(key) ?? 0) + (item.paid_amount ?? 0))
  }
  return [...grouped.entries()].map(([label, amount]) => ({ label, amount, share: bybtAmountTotal.value ? amount / bybtAmountTotal.value * 100 : 0 })).sort((left, right) => right.amount - left.amount).slice(0, 8)
})

function changeBybtPage(page: number): void {
  bybtPage.value = Math.min(Math.max(page, 1), bybtPageCount.value)
}
function changeBybtPageSize(): void { bybtPage.value = 1 }
function changeDailyPage(page: number): void {
  dailyPage.value = Math.min(Math.max(page, 1), dailyPageCount.value)
}
function changeDailyPageSize(): void { dailyPage.value = 1 }
function bybtMetric(valueToFormat: number | null): string { return valueToFormat === null ? "暂无" : number(valueToFormat) }
function bybtMoney(valueToFormat: number | null): string { return valueToFormat === null ? "暂无" : currency(valueToFormat) }

onMounted(async () => {
  await ensureDashboard()
  await loadBybtItems()
})

watch(
  () => [isBybt.value, dashboard.value?.range_start, dashboard.value?.range_end],
  (current, previous) => {
    if (!previous || current.join("|") === previous.join("|")) return
    dailyPage.value = 1
    if (current[0]) void loadBybtItems()
  },
)
</script>

<template>
  <template v-if="dashboard">
    <section class="module-workbench-hero marketing-channel-hero">
      <div><p>{{ eyebrow }}</p><h2>{{ title }}</h2><span>{{ isBybt ? "看百补流量、成交和支付件效率，区分平台活动流量与实际成交。" : "看充值规模、购物金支付和退款，区分充值行为与实际消费。" }}</span></div>
      <div class="module-workbench-source"><component :is="isBybt ? BarChart3 : ShoppingBag" :size="18" /><span>{{ hasData ? "已接入真实历史数据" : "当前范围暂无数据" }}</span></div>
    </section>
    <section v-if="snapshot" class="metrics-grid module-metrics marketing-channel-metrics"><MetricCard v-for="item in kpis" :key="item.label" :label="item.label" :value="item.value" :detail="item.detail" :icon="item.icon" :tone="item.tone" /></section>
    <section v-if="snapshot" class="marketing-channel-grid">
      <article class="panel marketing-chart-panel"><div class="panel-heading"><div><p>日趋势</p><h2>{{ isBybt ? "百补支付金额变化" : "充值与支付金额变化" }}</h2></div><span class="panel-action">{{ dailyHeading }}</span></div><MarketingTrendChart :items="chartItems" :series="chartSeries" /></article>
      <article class="panel marketing-reading-panel"><div class="panel-heading"><div><p>经营解读</p><h2>{{ isBybt ? "活动流量是否转成成交" : "充值资金是否形成消费" }}</h2></div><BarChart3 :size="18" /></div><div class="marketing-reading-list" v-if="isBybt"><div><span>成交效率</span><strong>{{ ratio(value.conversion_rate) }}</strong><small>百补访客到支付买家</small></div><div><span>支付客单价</span><strong>{{ currency(value.customer_unit_price) }}</strong><small>支付金额 / 支付买家</small></div><div><span>支付件效率</span><strong>{{ Number(value.items_per_buyer || 0).toFixed(2) }} 件</strong><small>支付成交件数 / 支付买家</small></div></div><div class="marketing-reading-list" v-else><div><span>当期资金使用比</span><strong>{{ ratio(value.paid_amount_ratio) }}</strong><small>当期支付金额 / 当期充值金额，不等同用户转化率</small></div><div><span>充值客单</span><strong>{{ currency(value.average_recharge_amount) }}</strong><small>充值金额 / 充值买家</small></div><div><span>充值退款</span><strong>{{ currency(value.recharge_refund_amount) }}</strong><small>所选范围充值成功退款</small></div></div></article>
    </section>
    <section v-if="snapshot" class="panel marketing-daily-panel"><div class="panel-heading"><div><p>日级核对</p><h2>{{ isBybt ? `日报覆盖${Number(value.covered_days ?? 0)}/${Number(value.expected_days ?? daily.length)}天` : "购物金原始日报明细" }}</h2></div><span class="panel-action">{{ daily.length }} 个统计日 · 原始日报口径</span></div><div class="marketing-daily-table"><div class="marketing-daily-row marketing-daily-head"><span>日期</span><span>{{ isBybt ? "访客" : "充值金额" }}</span><span>{{ isBybt ? "支付买家" : "支付金额" }}</span><span>{{ isBybt ? "支付金额" : "充值买家" }}</span><span>{{ isBybt ? "支付件数" : "退款金额" }}</span></div><div v-for="item in pagedDaily" :key="String(item.stat_date)" class="marketing-daily-row" :class="{ 'marketing-daily-row-missing': isBybt && item.record_status === 'missing' }"><span>{{ item.stat_date }}<small v-if="isBybt && item.record_status === 'missing'">未采集</small></span><span>{{ isBybt ? metricText(item, 'visitors', number) : currency(metric(item, 'recharge_amount') ?? 0) }}</span><span>{{ isBybt ? metricText(item, 'paid_buyers', number) : currency(metric(item, 'paid_amount') ?? 0) }}</span><span>{{ isBybt ? metricText(item, 'paid_amount', currency) : number(metric(item, 'recharge_buyers') ?? 0) }}</span><span>{{ isBybt ? metricText(item, 'paid_items', number) : currency(metric(item, 'recharge_refund_amount') ?? 0) }}</span></div></div><footer class="daily-pagination"><div><span>显示 {{ number(dailyPageStart) }}–{{ number(dailyPageEnd) }} / {{ number(orderedDaily.length) }} 天</span><label>每页<select v-model.number="dailyPageSize" @change="changeDailyPageSize"><option :value="10">10</option><option :value="20">20</option><option :value="30">30</option></select></label></div><div><button type="button" :disabled="dailyPage <= 1" @click="changeDailyPage(dailyPage - 1)"><ArrowLeft :size="14" />上一页</button><span>第 {{ dailyPage }} / {{ dailyPageCount }} 页</span><button type="button" :disabled="dailyPage >= dailyPageCount" @click="changeDailyPage(dailyPage + 1)">下一页<ArrowRight :size="14" /></button></div></footer></section>
    <section v-if="snapshot && isBybt" class="panel marketing-product-panel">
      <div class="panel-heading"><div><p>商品结构</p><h2>百补商品贡献与类目分布</h2></div><div class="marketing-product-heading-actions"><span class="panel-action">{{ bybtItems.length }} 个商品 · {{ bybtItemsRangeLabel }}</span><button type="button" class="icon-button" title="刷新百补商品明细" :disabled="bybtItemsLoading" @click="loadBybtItems"><RefreshCw :size="15" :class="{ spinning: bybtItemsLoading }" /></button></div></div>
      <div v-if="bybtItemsError" class="marketing-product-error">{{ bybtItemsError }}</div>
      <template v-else>
        <div class="marketing-product-summary"><div><span>商品明细支付金额</span><strong>{{ currency(bybtAmountTotal) }}</strong><small>按商品明细全量汇总</small></div><div><span>日报对账率</span><strong>{{ bybtReconcileRate === null ? '不可对账' : `${bybtReconcileRate.toFixed(2)}%` }}</strong><small>{{ bybtReconcileRate === null ? '日报与商品明细覆盖范围不同或存在缺失日' : '商品明细金额 / 百补日报金额' }}</small></div><div><span>有效商品数</span><strong>{{ number(bybtItems.length) }}</strong><small>当前明细覆盖期内按商品与营销 ID 聚合</small></div></div>
        <div class="marketing-category-list"><div v-for="item in bybtCategories" :key="item.label" class="marketing-category-row"><div><span>{{ item.label }}</span><strong>{{ currency(item.amount) }}</strong></div><i><b :style="{ width: `${Math.min(item.share, 100)}%` }"></b></i><em>{{ item.share.toFixed(1) }}%</em></div></div>
        <div class="marketing-product-toolbar"><label><Search :size="14" /><input v-model="bybtSearch" type="search" placeholder="搜索商品 ID、名称或类目" @input="bybtPage = 1" /></label><select v-model="bybtSort" aria-label="商品排序" @change="bybtPage = 1"><option value="paid_amount">按支付金额</option><option value="paid_order_count">按子订单数</option><option value="visitors">按访客数</option></select><label class="marketing-product-page-size"><span>每页</span><select v-model.number="bybtPageSize" @change="changeBybtPageSize"><option :value="20">20</option><option :value="50">50</option><option :value="100">100</option></select></label></div>
        <div v-if="bybtItemsLoading && !bybtItems.length" class="marketing-product-loading">正在读取商品明细</div>
        <div v-else-if="pagedBybtItems.length" class="marketing-product-table-wrap"><table class="marketing-product-table"><thead><tr><th>商品</th><th>类目</th><th>访客</th><th>子订单</th><th>支付件数</th><th>支付金额</th><th>转化率</th><th>有效日</th></tr></thead><tbody><tr v-for="item in pagedBybtItems" :key="`${item.product_id}-${item.activity_id}`"><td><strong>{{ item.product_name || '未命名商品' }}</strong><small>{{ item.product_id }} · {{ item.activity_id || '无营销 ID' }}</small></td><td>{{ item.category_name || '未分类' }}</td><td>{{ bybtMetric(item.visitors) }}</td><td>{{ bybtMetric(item.paid_order_count) }}</td><td>{{ bybtMetric(item.paid_items) }}</td><td class="marketing-product-money">{{ bybtMoney(item.paid_amount) }}</td><td>{{ item.conversion_rate === null ? '暂无' : ratio(item.conversion_rate) }}</td><td>{{ item.active_days }}</td></tr></tbody></table></div><EmptyState v-else title="当前明细覆盖期暂无商品" :detail="bybtItemsCoverage ? `商品明细可用期为 ${dateRangeLabel(bybtItemsCoverage.available_start, bybtItemsCoverage.available_end)}，当前查询区间无可用明细。` : '当前区间没有已按业务日期采集的百补商品明细。'" :icon="ShoppingBag" />
        <div class="marketing-product-pagination"><span>显示 {{ searchedBybtItems.length ? (bybtPage - 1) * bybtPageSize + 1 : 0 }}–{{ Math.min(bybtPage * bybtPageSize, searchedBybtItems.length) }} / {{ number(searchedBybtItems.length) }} 个商品</span><button type="button" class="icon-button" title="上一页" :disabled="bybtPage <= 1" @click="changeBybtPage(bybtPage - 1)"><ArrowLeft :size="14" /></button><span>第 {{ bybtPage }} / {{ bybtPageCount }} 页</span><button type="button" class="icon-button" title="下一页" :disabled="bybtPage >= bybtPageCount" @click="changeBybtPage(bybtPage + 1)"><ArrowRight :size="14" /></button></div>
      </template>
    </section>
    <EmptyState v-if="!hasData" title="当前范围暂无模块数据" detail="已确认数据表存在记录，请切换到数据覆盖的日期范围查看。" :icon="isBybt ? BarChart3 : ShoppingBag" />
  </template>
</template>
