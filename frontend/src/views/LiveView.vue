<script setup lang="ts">
import { computed, ref } from "vue"
import { BarChart3, CircleDollarSign, Eye, LoaderCircle, Radio, Search, ShoppingBag, UsersRound } from "lucide-vue-next"

import BusinessChart from "@/components/BusinessChart.vue"
import EmptyState from "@/components/EmptyState.vue"
import MetricCard from "@/components/MetricCard.vue"
import { useDashboard } from "@/composables/useDashboard"
import { currency, number, ratio } from "@/lib/format"
import type { LiveTalentMetric } from "@/types"

const { dashboard, loading } = useDashboard()
const live = computed(() => dashboard.value?.analysis?.live)
const daily = computed(() => live.value?.daily_metrics ?? [])
const talents = computed(() => live.value?.talents ?? [])
const talentPage = ref(1)
const talentPageSize = ref(20)
const talentJumpPage = ref("")
const talentSearch = ref("")
type TalentSortKey = "paid_amount" | "contribution_share" | "single_output" | "click_deal_rate" | "buyers" | "sessions"
const talentSortKey = ref<TalentSortKey>("paid_amount")
const talentSortDirection = ref<"asc" | "desc">("desc")
const talentPageSizeOptions = [10, 20, 30, 50]

type TalentRow = LiveTalentMetric & {
  contribution_share: number
  click_cart_rate: number
  action: string
  action_key: "focus" | "core" | "expand" | "stable" | "optimize" | "observe"
  action_tone: "focus" | "core" | "expand" | "stable" | "optimize" | "test"
}
const talentActionFilter = ref<"all" | TalentRow["action_key"]>("all")

const talentAverageClickDealRate = computed(() => {
  const clicks = talents.value.reduce((sum, item) => sum + item.item_click_users, 0)
  const buyers = talents.value.reduce((sum, item) => sum + item.buyers, 0)
  return clicks ? buyers / clicks * 100 : 0
})
const talentAverageSingleOutput = computed(() => {
  const sessions = talents.value.reduce((sum, item) => sum + item.sessions, 0)
  const paid = talents.value.reduce((sum, item) => sum + item.paid_amount, 0)
  return sessions ? paid / sessions : 0
})
const talentRows = computed<TalentRow[]>(() => {
  const totalPaid = talents.value.reduce((sum, item) => sum + item.paid_amount, 0)
  return talents.value.map((item) => {
    const contributionShare = totalPaid ? item.paid_amount / totalPaid * 100 : 0
    const clickCartRate = item.item_click_users ? item.add_cart_users / item.item_click_users * 100 : 0
    const isHighContribution = contributionShare >= 5
    const isEfficient = item.click_deal_rate >= talentAverageClickDealRate.value
    const isHighOutput = item.single_output >= talentAverageSingleOutput.value
    const isLowSample = item.sessions <= 2
    const isOptimize = item.click_deal_rate < talentAverageClickDealRate.value * .75 && item.item_click_users >= 20
    const action = isHighContribution && isEfficient
      ? { action: "重点放量", action_key: "focus" as const, action_tone: "focus" as const }
      : isHighContribution
        ? { action: "核心提效", action_key: "core" as const, action_tone: "core" as const }
        : isLowSample && (isEfficient || isHighOutput)
          ? { action: "扩量验证", action_key: "expand" as const, action_tone: "expand" as const }
          : isLowSample
            ? { action: "低量观察", action_key: "observe" as const, action_tone: "test" as const }
            : isOptimize
              ? { action: "优化转化", action_key: "optimize" as const, action_tone: "optimize" as const }
              : isEfficient && isHighOutput
                ? { action: "扩量测试", action_key: "expand" as const, action_tone: "expand" as const }
                : { action: "稳定合作", action_key: "stable" as const, action_tone: "stable" as const }
    return {
      ...item,
      contribution_share: contributionShare,
      click_cart_rate: clickCartRate,
      ...action,
    }
  })
})
const filteredTalentRows = computed(() => {
  const query = talentSearch.value.trim().toLowerCase()
  const searchedRows = query ? talentRows.value.filter((item) => `${item.talent_name} ${item.talent_id}`.toLowerCase().includes(query)) : talentRows.value
  const rows = talentActionFilter.value === "all" ? searchedRows : searchedRows.filter((item) => item.action_key === talentActionFilter.value)
  const direction = talentSortDirection.value === "asc" ? 1 : -1
  return [...rows].sort((left, right) => {
    const leftValue = left[talentSortKey.value]
    const rightValue = right[talentSortKey.value]
    return (Number(leftValue) - Number(rightValue)) * direction
  })
})
const talentTotal = computed(() => filteredTalentRows.value.length)
const talentPageCount = computed(() => Math.max(1, Math.ceil(talentTotal.value / talentPageSize.value)))
const visibleTalentPages = computed(() => {
  const total = talentPageCount.value
  const current = talentPage.value
  const start = Math.max(1, Math.min(current - 2, total - 4))
  const end = Math.min(total, Math.max(current + 2, 5))
  return Array.from({ length: end - start + 1 }, (_, index) => start + index)
})
const pagedTalentRows = computed(() => {
  const start = (talentPage.value - 1) * talentPageSize.value
  return filteredTalentRows.value.slice(start, start + talentPageSize.value)
})
const topTalent = computed(() => talentRows.value.slice().sort((a, b) => b.paid_amount - a.paid_amount)[0] || null)
const talentContributionTopThree = computed(() => talentRows.value.slice().sort((a, b) => b.paid_amount - a.paid_amount).slice(0, 3).reduce((sum, item) => sum + item.contribution_share, 0))
const talentMaxContribution = computed(() => Math.max(...talentRows.value.map((item) => item.contribution_share), 1))
const talentDiagnosis = computed(() => {
  if (!talentRows.value.length) return "当前日期范围没有合作主播数据。"
  const focus = talentRows.value.filter((item) => item.action_key === "focus").sort((a, b) => b.paid_amount - a.paid_amount)[0]
  const core = talentRows.value.filter((item) => item.action_key === "core").sort((a, b) => b.paid_amount - a.paid_amount)[0]
  const concentration = talentContributionTopThree.value >= 60 ? "成交明显集中在头部主播" : "成交在主播间相对分散"
  const focusText = focus ? `“${focus.talent_name}”兼具规模与效率，可优先争取更多场次。` : "当前没有同时达到头部贡献和整体转化基准的主播。"
  const coreText = core ? `“${core.talent_name}”贡献高但转化低于整体，应优先优化选品、价格或直播承接。` : "头部主播转化暂未出现明显短板。"
  return `${concentration}，Top 3 贡献 ${talentContributionTopThree.value.toFixed(2)}%。${focusText}${coreText}`
})

function changeTalentPage(next: number): void {
  talentPage.value = Math.min(talentPageCount.value, Math.max(1, next))
  talentJumpPage.value = ""
}
function changeTalentPageSize(): void {
  talentPage.value = 1
  talentJumpPage.value = ""
}
function jumpTalentPage(): void {
  const target = Number.parseInt(talentJumpPage.value, 10)
  if (Number.isFinite(target)) changeTalentPage(target)
}
function changeTalentSort(key: TalentSortKey): void {
  if (talentSortKey.value === key) talentSortDirection.value = talentSortDirection.value === "asc" ? "desc" : "asc"
  else { talentSortKey.value = key; talentSortDirection.value = "desc" }
  talentPage.value = 1
}
function resetTalentPage(): void { talentPage.value = 1 }

const trendOption = computed(() => ({
  color: ["#16845b", "#e2a447", "#6b8fd6"],
  tooltip: { trigger: "axis", valueFormatter: (value: number) => currency(Number(value)) },
  legend: { bottom: 0, data: ["直播中成交", "播后成交", "店播成交"] },
  grid: { left: 62, right: 24, top: 24, bottom: 54 },
  xAxis: { type: "category", data: daily.value.map((item) => item.stat_date.slice(5)) },
  yAxis: { type: "value", axisLabel: { formatter: "¥{value}" }, splitLine: { lineStyle: { color: "#edf1ef" } } },
  series: [
    { name: "直播中成交", type: "bar", stack: "paid", barMaxWidth: 24, data: daily.value.map((item) => item.live_during_paid_amount) },
    { name: "播后成交", type: "bar", stack: "paid", barMaxWidth: 24, data: daily.value.map((item) => item.post_paid_amount) },
    { name: "店播成交", type: "line", smooth: true, data: daily.value.map((item) => item.shop_paid_amount) },
  ],
}))

const funnelOption = computed(() => ({
  color: ["#a8d9c4", "#6bbd99", "#e2a447", "#5b8def"],
  tooltip: { trigger: "item", valueFormatter: (value: number) => number(Number(value)) },
  series: [{ type: "funnel", left: "8%", top: 18, bottom: 18, width: "84%", min: 0, max: Math.max(live.value?.viewers ?? 0, 1), minSize: "14%", maxSize: "100%", sort: "descending", gap: 3, label: { show: true, position: "inside", color: "#264235", fontSize: 11 }, data: live.value ? [
    { name: "店播观看", value: live.value.viewers },
    { name: "商品点击", value: live.value.item_click_users },
    { name: "店播成交", value: live.value.buyers },
  ] : [] }],
}))
</script>

<template>
  <template v-if="dashboard && live">
    <section class="business-page-heading">
      <div><p>内容与服务 / 直播经营</p><h1>直播分析</h1><span>店播与达播分开看，避免把两套成交口径混成一个漏斗。</span></div>
      <span class="data-definition-badge"><Radio :size="15" /> 店播 / 达播双口径</span>
    </section>

    <section class="metrics-grid module-metrics">
      <MetricCard label="直播成交金额" :value="currency(live.paid_amount)" :detail="`店播 ${currency(live.shop_paid_amount)} · 达播 ${currency(live.talent_paid_amount)}`" :icon="CircleDollarSign" tone="teal" scope="区间累计" definition="直播概览总成交，不将店播与达播简单相加，避免重复归因。" />
      <MetricCard label="店播观看人数" :value="number(live.viewers)" :detail="`商品点击 ${number(live.item_click_users)} 人`" :icon="Eye" tone="blue" scope="区间累计" />
      <MetricCard label="店播成交转化" :value="ratio(live.deal_rate)" :detail="`${number(live.buyers)} 位成交买家 · 客单 ${currency(live.unit_price)}`" :icon="ShoppingBag" tone="amber" scope="店播口径" />
      <MetricCard label="达播合作规模" :value="number(live.talent_count)" :detail="`${number(live.talent_sessions)} 场 · ${number(talents.length)} 个合作主播`" :icon="UsersRound" tone="coral" scope="区间累计" />
    </section>

    <section class="decision-chart-grid">
      <article class="panel"><div class="panel-heading"><div><p>店播经营</p><h2>直播中成交与播后成交</h2></div><Radio :size="18" /></div><BusinessChart :option="trendOption" ariaLabel="店播直播中和播后成交趋势图" :height="330" /><p class="panel-footnote">店播成交金额来自直播概览；观看、点击、成交漏斗来自店播转化表，两个数据集按日期核对。</p></article>
      <article class="panel"><div class="panel-heading"><div><p>店播漏斗</p><h2>观看到商品成交</h2></div><BarChart3 :size="18" /></div><BusinessChart :option="funnelOption" ariaLabel="店播观看商品点击成交漏斗" :height="330" /></article>
    </section>

    <section class="panel talent-diagnostic-panel">
      <div class="panel-heading"><div><p>达播诊断</p><h2>合作主播贡献与效率</h2></div><span class="panel-action">全量 {{ number(talents.length) }} 个主播 · 当前筛选 {{ number(talentTotal) }} 个</span></div>

      <div class="talent-summary-strip">
        <div><span>达播成交</span><strong>{{ currency(live.talent_paid_amount) }}</strong><small>{{ number(live.talent_sessions) }} 场合作</small></div>
        <div><span>Top 3 成交集中度</span><strong>{{ ratio(talentContributionTopThree) }}</strong><small>判断是否过度依赖头部主播</small></div>
        <div><span>平均单场产出</span><strong>{{ currency(talentAverageSingleOutput) }}</strong><small>全部主播加权口径</small></div>
        <div><span>整体点击成交率</span><strong>{{ ratio(talentAverageClickDealRate) }}</strong><small>成交买家 / 商品点击人数</small></div>
        <div><span>成交第一主播</span><strong>{{ topTalent?.talent_name || '--' }}</strong><small>{{ topTalent ? `${currency(topTalent.paid_amount)} · ${ratio(topTalent.contribution_share)}` : '暂无主播数据' }}</small></div>
      </div>

      <div class="talent-diagnosis"><strong>当前判断</strong><span>{{ talentDiagnosis }}</span></div>

      <div class="talent-table-toolbar">
        <div class="talent-search"><Search :size="15" /><input v-model="talentSearch" placeholder="搜索主播名称或 ID" @input="resetTalentPage" /></div>
        <label><span>建议</span><select v-model="talentActionFilter" @change="resetTalentPage"><option value="all">全部合作建议</option><option value="focus">重点放量</option><option value="core">核心提效</option><option value="expand">扩量验证</option><option value="stable">稳定合作</option><option value="optimize">优化转化</option><option value="observe">低量观察</option></select></label>
        <label><span>排序</span><select v-model="talentSortKey" @change="resetTalentPage"><option value="paid_amount">成交金额</option><option value="contribution_share">成交贡献</option><option value="single_output">单场产出</option><option value="click_deal_rate">点击成交率</option><option value="buyers">成交买家</option><option value="sessions">合作场次</option></select></label>
        <button type="button" class="talent-sort-direction" @click="talentSortDirection = talentSortDirection === 'asc' ? 'desc' : 'asc'">{{ talentSortDirection === 'desc' ? '降序' : '升序' }}</button>
      </div>

      <div v-if="pagedTalentRows.length" class="talent-table-wrap">
        <table class="talent-data-table">
          <thead><tr><th>排名 / 主播</th><th><button type="button" @click="changeTalentSort('sessions')">场次</button></th><th>点击 / 加购</th><th><button type="button" @click="changeTalentSort('buyers')">成交买家</button></th><th><button type="button" @click="changeTalentSort('paid_amount')">成交金额</button></th><th><button type="button" @click="changeTalentSort('contribution_share')">贡献占比</button></th><th><button type="button" @click="changeTalentSort('single_output')">单场产出</button></th><th><button type="button" @click="changeTalentSort('click_deal_rate')">点击成交率</button></th><th>合作建议</th></tr></thead>
          <tbody><tr v-for="(item, index) in pagedTalentRows" :key="`${item.talent_id}-${item.talent_name}`"><td><span class="talent-rank">{{ (talentPage - 1) * talentPageSize + index + 1 }}</span><strong>{{ item.talent_name }}</strong><small>{{ item.talent_id || '无主播 ID' }}</small></td><td>{{ number(item.sessions) }}</td><td>{{ number(item.item_click_users) }} / {{ number(item.add_cart_users) }}<small>加购承接 {{ ratio(item.click_cart_rate) }}</small></td><td>{{ number(item.buyers) }}</td><td><em>{{ currency(item.paid_amount) }}</em><small>{{ number(item.paid_orders) }} 笔 · {{ number(item.paid_items) }} 件</small></td><td><strong>{{ ratio(item.contribution_share) }}</strong><i class="talent-contribution-bar"><b :style="{ width: `${item.contribution_share / talentMaxContribution * 100}%` }"></b></i></td><td>{{ currency(item.single_output) }}</td><td>{{ ratio(item.click_deal_rate) }}</td><td><span class="talent-action" :class="item.action_tone">{{ item.action }}</span></td></tr></tbody>
        </table>
      </div>
      <EmptyState v-else title="没有符合条件的主播" detail="清空主播搜索后查看当前日期范围的全部达播合作。" :icon="UsersRound" />

      <div v-if="talentTotal" class="talent-pagination">
        <span class="talent-pagination-total">显示 {{ (talentPage - 1) * talentPageSize + 1 }}–{{ Math.min(talentPage * talentPageSize, talentTotal) }} / {{ number(talentTotal) }} 个主播</span>
        <label>每页<select v-model.number="talentPageSize" @change="changeTalentPageSize"><option v-for="size in talentPageSizeOptions" :key="size" :value="size">{{ size }} 条</option></select></label>
        <div class="talent-page-buttons"><button type="button" :disabled="talentPage <= 1" @click="changeTalentPage(1)">首页</button><button type="button" :disabled="talentPage <= 1" @click="changeTalentPage(talentPage - 1)">上一页</button><button v-for="page in visibleTalentPages" :key="page" type="button" :class="{ active: page === talentPage }" @click="changeTalentPage(page)">{{ page }}</button><button type="button" :disabled="talentPage >= talentPageCount" @click="changeTalentPage(talentPage + 1)">下一页</button><button type="button" :disabled="talentPage >= talentPageCount" @click="changeTalentPage(talentPageCount)">末页</button></div>
        <label class="talent-page-jump">跳至<input v-model="talentJumpPage" inputmode="numeric" aria-label="达播主播跳转页码" @keyup.enter="jumpTalentPage" />页<button type="button" @click="jumpTalentPage">确定</button></label>
      </div>
      <p class="panel-footnote">达播成交来自合作主播日报。贡献占比以当前日期范围全部主播成交为分母；“合作建议”根据贡献规模、单场产出、点击成交率和合作场次数分层，仅用于运营排查，不代表平台官方评级。当前没有佣金、坑位费、投流费和退款成本字段，因此这里判断的是成交效率，不等同主播利润率。</p>
    </section>
  </template>
  <section v-else-if="loading" class="loading-panel"><LoaderCircle :size="26" class="spinning" /><span>正在读取直播分析</span></section>
  <EmptyState v-else title="暂无直播分析数据" detail="当前日期范围没有直播概览或店播转化记录。" :icon="Radio" />
</template>
