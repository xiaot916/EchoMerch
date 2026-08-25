<script setup lang="ts">
import { BadgePercent, CircleDollarSign, Headphones, MessageCircleMore, ShieldCheck, Target, Timer, TrendingUp } from "lucide-vue-next"
import { computed, onMounted } from "vue"

import EmptyState from "@/components/EmptyState.vue"
import CustomerServiceTrendChart from "@/components/CustomerServiceTrendChart.vue"
import BusinessChart from "@/components/BusinessChart.vue"
import MetricCard from "@/components/MetricCard.vue"
import { useDashboard } from "@/composables/useDashboard"
import { currency, number, ratio } from "@/lib/format"

const { dashboard, ensureDashboard } = useDashboard()
const snapshot = computed(() => dashboard.value?.analysis?.customer_service ?? null)
const daily = computed(() => dashboard.value?.analysis?.customer_service_daily ?? [])
const recentDaily = computed(() => [...daily.value].reverse().slice(0, 7))
const accounts = computed(() => dashboard.value?.analysis?.customer_service_accounts ?? [])
const hasServiceData = computed(() => Boolean(snapshot.value && daily.value.length))
const bestAccountSales = computed(() => Math.max(...accounts.value.map((item) => item.sales_amount), 1))
const rankedAccounts = computed(() => [...accounts.value].sort((left, right) => right.sales_amount - left.sales_amount))

const performanceScatterOption = computed(() => {
  const team = snapshot.value
  const teamReception = team?.reception_rate ?? 0
  const teamConversion = team?.sales_conversion_rate ?? 0
  return {
    color: ["#16845b"],
    tooltip: {
      trigger: "item",
      formatter: (params: { data: [number, number, number, string, number] }) => {
        const [reception, conversion, sales, name, consults] = params.data
        return `${name}<br/>销售额：${currency(Number(sales))}<br/>咨询：${number(Number(consults))} 人<br/>接待率：${ratio(Number(reception))}<br/>咨询成交率：${ratio(Number(conversion))}`
      },
    },
    grid: { left: 76, right: 48, top: 22, bottom: 64 },
    xAxis: {
      type: "value", name: "接待率", nameLocation: "middle", nameGap: 38,
      min: 0, max: 100, splitNumber: 5,
      nameTextStyle: { color: "#718078", fontSize: 11, fontWeight: 600 },
      axisLine: { lineStyle: { color: "#aebbb4" } }, axisTick: { show: false },
      axisLabel: { color: "#7c8982", fontSize: 10, formatter: "{value}%", margin: 10 },
      splitLine: { lineStyle: { color: "#edf1ef" } },
    },
    yAxis: {
      type: "value", name: "咨询成交率", nameLocation: "middle", nameGap: 52,
      min: 0, max: 100, splitNumber: 5,
      nameTextStyle: { color: "#718078", fontSize: 11, fontWeight: 600 },
      axisLine: { lineStyle: { color: "#aebbb4" } }, axisTick: { show: false },
      axisLabel: { color: "#7c8982", fontSize: 10, formatter: "{value}%", margin: 10 },
      splitLine: { lineStyle: { color: "#edf1ef" } },
    },
    series: [{
      type: "scatter",
      clip: false,
      symbolSize: (value: [number, number, number]) => Math.max(14, Math.min(48, Math.sqrt(value[2] || 1) / 5)),
      itemStyle: { color: "#24956d", opacity: 0.86, borderColor: "#ffffff", borderWidth: 1.5 },
      data: rankedAccounts.value.map((item) => [item.reception_rate, item.sales_conversion_rate, item.sales_amount, item.account_name, item.consult_users]),
      markLine: {
        symbol: ["none", "none"],
        label: { color: "#5d7065", fontSize: 9, padding: [3, 5], backgroundColor: "rgba(255,255,255,.88)", borderRadius: 3 },
        lineStyle: { color: "#b8c9bf", type: "dashed" },
        data: [
          { xAxis: teamReception, label: { formatter: `团队接待 ${teamReception.toFixed(1)}%`, position: "insideEndTop" } },
          { yAxis: teamConversion, label: { formatter: `团队成交 ${teamConversion.toFixed(1)}%`, position: "insideStartTop" } },
        ],
      },
    }],
  }
})

function contributionWidth(value: number): string {
  return `${Math.max(3, Math.min(100, (value / bestAccountSales.value) * 100))}%`
}

onMounted(() => { void ensureDashboard() })
</script>

<template>
  <template v-if="dashboard">
    <section class="module-hero customer-service-hero">
      <div>
        <p>客服经营</p>
        <h2>客服成交、服务与人员效率</h2>
        <span>统一查看客服总盘、日趋势、咨询漏斗和账号绩效，不重复计算团队指标。</span>
      </div>
      <div class="customer-service-status"><Headphones :size="20" /><span>{{ hasServiceData ? `${daily.length} 个客服统计日` : "当前范围暂无客服数据" }}</span></div>
    </section>

    <section v-if="snapshot" class="metrics-grid customer-service-metrics">
      <MetricCard label="客服销售额" :value="currency(snapshot.sales_amount)" detail="客服报表归因成交" :icon="CircleDollarSign" tone="teal" />
      <MetricCard label="客服净销售额" :value="currency(snapshot.net_sales_amount)" :detail="`成功退款 ${currency(snapshot.refund_amount)}`" :icon="BadgePercent" tone="blue" />
      <MetricCard label="客服成交占比" :value="ratio(snapshot.sales_ratio)" detail="客服销售额 / 店铺销售口径" :icon="MessageCircleMore" tone="blue" />
      <MetricCard label="平均响应" :value="`${snapshot.avg_reply_seconds.toFixed(1)} 秒`" :detail="`满意率 ${ratio(snapshot.satisfaction_rate)}`" :icon="Timer" tone="teal" />
    </section>

    <section v-if="snapshot" class="panel service-overview-trend-panel">
      <div class="panel-heading"><div><p>多指标趋势</p><h2>销售、咨询、响应与满意率</h2></div><span class="panel-action">{{ daily.length }} 个统计日</span></div>
      <CustomerServiceTrendChart v-if="daily.length" :metrics="daily" />
      <EmptyState v-else title="暂无客服日级趋势" detail="当前日期范围没有客服概览入库记录。" :icon="Headphones" />
    </section>

    <section v-if="snapshot" class="service-overview-support-grid">
      <article class="panel customer-service-funnel-panel">
        <div class="panel-heading"><div><p>服务漏斗</p><h2>从咨询到客服成交</h2></div><MessageCircleMore :size="18" /></div>
        <div class="service-funnel-list">
          <div><span>咨询用户</span><strong>{{ number(snapshot.consult_users) }}</strong><small>客服报表累计咨询人数</small></div>
          <div><span>有效接待</span><strong>{{ number(snapshot.reception_users) }}</strong><small>咨询接待率 {{ ratio(snapshot.reception_rate) }}</small></div>
          <div><span>客服成交用户</span><strong>{{ number(snapshot.sale_users) }}</strong><small>咨询成交率 {{ ratio(snapshot.sales_conversion_rate) }}</small></div>
        </div>
      </article>

      <article class="panel customer-service-daily-panel">
        <div class="panel-heading"><div><p>日级核对</p><h2>最近 7 个有效统计日</h2></div><TrendingUp :size="18" /></div>
        <div v-if="daily.length" class="customer-service-table">
          <div class="customer-service-row customer-service-head"><span>日期</span><span>客服销售额</span><span>咨询</span><span>平均响应</span><span>满意率</span></div>
          <div v-for="item in recentDaily" :key="item.stat_date" class="customer-service-row"><span>{{ item.stat_date }}</span><strong>{{ currency(item.sales_amount) }}</strong><span>{{ number(item.consult_users) }}</span><span>{{ item.avg_reply_seconds.toFixed(1) }} 秒</span><span>{{ ratio(item.satisfaction_rate) }}</span></div>
        </div>
        <EmptyState v-else title="暂无客服日级数据" detail="当前日期范围没有客服概览入库记录。" :icon="Headphones" />
      </article>
    </section>

    <section v-if="snapshot" class="panel customer-service-account-panel">
      <div class="panel-heading"><div><p>人员贡献</p><h2>客服账号销售与接待效率</h2></div><ShieldCheck :size="18" /></div>
      <div v-if="accounts.length" class="customer-service-account-table">
        <div class="customer-service-account-row customer-service-account-head"><span>客服账号</span><span>销售额</span><span>净销售额</span><span>咨询</span><span>接待率</span><span>咨询成交率</span></div>
        <div v-for="account in rankedAccounts" :key="account.account_name" class="customer-service-account-row">
          <strong><b>{{ account.account_name }}</b><i><em :style="{ width: contributionWidth(account.sales_amount) }"></em></i></strong>
          <span>{{ currency(account.sales_amount) }}</span><span>{{ currency(account.net_sales_amount) }}</span><span>{{ number(account.consult_users) }}</span><span>{{ ratio(account.reception_rate) }}</span><span>{{ ratio(account.sales_conversion_rate) }}</span>
        </div>
      </div>
      <EmptyState v-else title="暂无客服账号数据" detail="客服概览已入库，但当前日期范围没有账号维度明细。" :icon="Headphones" />
    </section>

    <section v-if="snapshot" class="panel decision-wide-chart customer-service-scatter-panel">
      <div class="panel-heading customer-service-scatter-heading"><div><p>人员效率分布</p><h2>账号接待率与咨询成交率</h2><span>横轴看接待覆盖，纵轴看接待后的成交效率</span></div><Target :size="18" /></div>
      <div class="customer-service-scatter-chart"><BusinessChart v-if="rankedAccounts.length" :option="performanceScatterOption" ariaLabel="客服账号接待率与咨询成交率散点图" :height="360" /></div>
      <p class="panel-footnote">气泡大小代表销售额；虚线是团队整体指标。用于定位“接待不足”或“接待后转化不足”的账号，不替代团队总盘。</p>
    </section>

    <EmptyState v-if="!snapshot" title="暂无客服真实数据" detail="当前日期范围没有客服概览入库记录，页面不会用全店支付或访客数据替代。" :icon="Headphones" />
  </template>
</template>
