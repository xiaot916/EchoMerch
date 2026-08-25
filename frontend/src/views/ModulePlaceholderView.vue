<script setup lang="ts">
import { computed, onMounted } from "vue"
import { BarChart3, CircleDollarSign, Database, Inbox, Target, UsersRound } from "lucide-vue-next"
import EmptyState from "@/components/EmptyState.vue"
import MetricCard from "@/components/MetricCard.vue"
import { useDashboard } from "@/composables/useDashboard"
import { currency, number, ratio } from "@/lib/format"
import { useRoute } from "vue-router"
import type { AnalysisSnapshot } from "@/types"

const route = useRoute()
const { dashboard, ensureDashboard } = useDashboard()
const title = computed(() => String(route.meta.title || "数据模块"))
const eyebrow = computed(() => String(route.meta.eyebrow || "业务数据"))
const analysis = computed(() => dashboard.value?.analysis || null)
const moduleKey = computed(() => String(route.name || ""))

const moduleConfig = computed(() => {
  const configs: Record<string, { key: keyof AnalysisSnapshot | null; description: string; icon: typeof UsersRound }> = {
    customers: { key: "customer", description: "新客、老客与复购贡献", icon: UsersRound },
    "customer-members": { key: "member", description: "会员规模、成交与招募转化", icon: UsersRound },
    service: { key: "customer_service", description: "客服销售、咨询与服务质量", icon: Target },
    content: { key: "content", description: "内容触达、互动与种草成交", icon: BarChart3 },
    "marketing-new-customer": { key: "customer", description: "新客成交与新客转化", icon: UsersRound },
    market: { key: null, description: "当前本地库暂未提供竞品或行业对标数据", icon: Database },
    "marketing-activities": { key: null, description: "当前本地库暂未提供活动日历明细", icon: Inbox },
    "marketing-shopping-gold": { key: null, description: "当前本地库暂未提供购物金汇总明细", icon: CircleDollarSign },
    "marketing-bybt": { key: null, description: "当前本地库暂未提供百补汇总明细", icon: Target },
  }
  return configs[moduleKey.value] || configs.customers
})

const snapshot = computed(() => {
  const key = moduleConfig.value.key
  return key && analysis.value ? analysis.value[key] : null
})

const kpis = computed(() => {
  const value = snapshot.value as Record<string, number> | null
  if (!value) return []
  const key = moduleConfig.value.key
  if (key === "customer") return [
    { label: "店铺客户数", value: number(value.shop_customers), detail: "最后有效日存量", icon: UsersRound, tone: "blue" as const },
    { label: "新客成交金额", value: currency(value.new_customer_paid_amount), detail: `${number(value.new_customer_paid_buyers)} 位成交`, icon: CircleDollarSign, tone: "teal" as const },
    { label: "老客复购金额", value: currency(value.repeat_customer_paid_amount), detail: `复购率 ${ratio(value.repeat_rate)}`, icon: Target, tone: "amber" as const },
    { label: "新客转化率", value: ratio(value.new_customer_conversion_rate), detail: `${number(value.new_customers)} 位新访客户`, icon: BarChart3, tone: "coral" as const },
  ]
  if (key === "member") return [
    { label: "会员总数", value: number(value.total_members), detail: "最后有效日存量", icon: UsersRound, tone: "blue" as const },
    { label: "会员成交金额", value: currency(value.paid_amount), detail: `${number(value.paid_members)} 位成交`, icon: CircleDollarSign, tone: "teal" as const },
    { label: "会员复购金额", value: currency(value.repurchase_amount), detail: `${number(value.repurchase_members)} 位复购`, icon: Target, tone: "amber" as const },
    { label: "新增会员", value: number(value.new_members), detail: `招募转化 ${ratio(value.recruit_conversion_rate)}`, icon: BarChart3, tone: "coral" as const },
  ]
  if (key === "customer_service") return [
    { label: "客服销售额", value: currency(value.sales_amount), detail: `${number(value.sale_users)} 位销售用户`, icon: CircleDollarSign, tone: "blue" as const },
    { label: "客服净销售额", value: currency(value.net_sales_amount), detail: "扣除成功退款", icon: Target, tone: "teal" as const },
    { label: "咨询人数", value: number(value.consult_users), detail: `${number(value.reception_users)} 位接待`, icon: UsersRound, tone: "amber" as const },
    { label: "平均响应", value: `${value.avg_reply_seconds.toFixed(1)} 秒`, detail: `满意率 ${ratio(value.satisfaction_rate)}`, icon: BarChart3, tone: "coral" as const },
  ]
  return [
    { label: "内容查看次数", value: number(value.view_count), detail: `${number(value.viewers)} 位查看用户`, icon: UsersRound, tone: "blue" as const },
    { label: "商品点击人数", value: number(value.product_click_users), detail: `${number(value.interaction_count)} 次互动`, icon: Target, tone: "teal" as const },
    { label: "种草成交金额", value: currency(value.paid_amount), detail: `${number(value.paid_buyers)} 位成交`, icon: CircleDollarSign, tone: "amber" as const },
    { label: "内容互动次数", value: number(value.interaction_count), detail: "已入库内容口径", icon: BarChart3, tone: "coral" as const },
  ]
})

onMounted(() => { void ensureDashboard() })
</script>

<template>
  <template v-if="dashboard">
    <section class="module-workbench-hero">
      <div><p>{{ eyebrow }}</p><h2>{{ title }}</h2><span>{{ moduleConfig.description }}</span></div>
      <div class="module-workbench-source"><component :is="moduleConfig.icon" :size="18" /><span>{{ snapshot ? "已接入真实历史数据" : "暂无该模块数据" }}</span></div>
    </section>

    <section v-if="snapshot" class="metrics-grid module-metrics">
      <MetricCard v-for="item in kpis" :key="item.label" :label="item.label" :value="item.value" :detail="item.detail" :icon="item.icon" :tone="item.tone" />
    </section>

    <section v-if="snapshot" class="module-data-grid">
      <article class="panel module-summary-panel">
        <div class="panel-heading"><div><p>模块摘要</p><h2>{{ title }}关键指标</h2></div><Database :size="18" /></div>
        <div class="module-summary-list">
          <div v-for="item in kpis" :key="item.label"><span>{{ item.label }}</span><strong>{{ item.value }}</strong><small>{{ item.detail }}</small></div>
        </div>
      </article>
      <article class="panel module-daily-panel">
        <div class="panel-heading"><div><p>全店参照</p><h2>同期支付趋势</h2></div><span class="panel-action">{{ dashboard.daily_metrics.length }} 个统计日</span></div>
        <div class="module-daily-table">
          <div class="module-daily-row module-daily-head"><span>日期</span><span>支付金额</span><span>访客</span><span>支付买家</span></div>
          <div v-for="item in dashboard.daily_metrics.slice(-10).reverse()" :key="item.stat_date" class="module-daily-row"><span>{{ item.stat_date }}</span><strong>{{ currency(item.paid_amount) }}</strong><span>{{ number(item.visitors) }}</span><span>{{ number(item.buyers) }}</span></div>
        </div>
      </article>
    </section>

    <EmptyState v-else title="暂无该模块真实数据" :detail="`${moduleConfig.description}。当前数据库没有对应日期范围的入库记录，页面不会用模拟数据填充。`" :icon="moduleConfig.icon" />
  </template>
</template>
