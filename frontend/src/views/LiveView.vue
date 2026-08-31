<script setup lang="ts">
import { computed, ref } from "vue"
import { BarChart3, CircleDollarSign, Eye, LoaderCircle, Radio, Search, ShoppingBag, UsersRound } from "lucide-vue-next"

import BusinessChart from "@/components/BusinessChart.vue"
import BusinessActionTable from "@/components/BusinessActionTable.vue"
import EmptyState from "@/components/EmptyState.vue"
import MetricCard from "@/components/MetricCard.vue"
import { useDashboard } from "@/composables/useDashboard"
import { currency, number, ratio } from "@/lib/format"
import type { BusinessActionRow } from "@/lib/businessDecision"
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
const shopWeightedClickRate = computed(() => {
  const viewers = daily.value.reduce((sum, item) => sum + item.viewers, 0)
  return viewers ? daily.value.reduce((sum, item) => sum + item.item_click_users, 0) / viewers * 100 : 0
})
const shopWeightedDealRate = computed(() => {
  const clicks = daily.value.reduce((sum, item) => sum + item.item_click_users, 0)
  return clicks ? daily.value.reduce((sum, item) => sum + item.buyers, 0) / clicks * 100 : 0
})
const shopViewClickRate = computed<number | null>(() => live.value?.viewers ? live.value.item_click_users / live.value.viewers * 100 : null)
const shopClickDealRate = computed<number | null>(() => live.value?.item_click_users ? live.value.buyers / live.value.item_click_users * 100 : null)
const shopOverallDealRate = computed<number | null>(() => live.value?.viewers ? live.value.buyers / live.value.viewers * 100 : null)
const funnelRateLabel = (value: number | null): string => value === null ? "--" : ratio(value)
const liveActionRows = computed<BusinessActionRow[]>(() => {
  const rows: BusinessActionRow[] = []
  const lowClickDay = daily.value.filter((item) => item.viewers >= 100 && item.view_click_rate < shopWeightedClickRate.value * .7).sort((left, right) => right.viewers - left.viewers)[0]
  if (lowClickDay) rows.push({ id: `shop-click-${lowClickDay.stat_date}`, priority: "P0", object: `店播 ${lowClickDay.stat_date}`, issue: "观看规模高但商品点击承接弱", evidence: `${number(lowClickDay.viewers)} 观看，观看点击率 ${ratio(lowClickDay.view_click_rate)}`, impact: currency(lowClickDay.shop_paid_amount), action: "复盘商品露出、讲解顺序和利益点，优先调整前 30 分钟货盘。", validation: "观看点击率、商品点击人数", window: "下一场", tone: "risk" })
  const lowDealDay = daily.value.filter((item) => item.item_click_users >= 30 && item.click_deal_rate < shopWeightedDealRate.value * .7).sort((left, right) => right.item_click_users - left.item_click_users)[0]
  if (lowDealDay) rows.push({ id: `shop-deal-${lowDealDay.stat_date}`, priority: "P0", object: `店播 ${lowDealDay.stat_date}`, issue: "商品点击后成交承接弱", evidence: `${number(lowDealDay.item_click_users)} 点击，点击成交 ${ratio(lowDealDay.click_deal_rate)}`, impact: currency(lowDealDay.shop_paid_amount), action: "核对直播价、优惠规则、库存和客服承接，不继续单纯拉观看。", validation: "点击成交率、支付买家、客单价", window: "下一场", tone: "risk" })
  if (talentContributionTopThree.value >= 60) rows.push({ id: "talent-concentration", priority: "P1", object: "达播 Top 3 主播", issue: "达播成交集中度较高", evidence: `Top 3 占达播成交 ${ratio(talentContributionTopThree.value)}`, impact: currency(talentRows.value.slice().sort((a, b) => b.paid_amount - a.paid_amount).slice(0, 3).reduce((sum, item) => sum + item.paid_amount, 0)), action: "保留头部合作，同时测试第二梯队主播，避免排期变化造成成交波动。", validation: "Top 3 占比、第二梯队单场产出", window: "2-4 周", tone: "warning" })
  const coreTalent = talentRows.value.filter((item) => item.action_key === "core" || item.action_key === "optimize").sort((left, right) => right.paid_amount - left.paid_amount)[0]
  if (coreTalent) rows.push({ id: `talent-optimize-${coreTalent.talent_id}`, priority: "P1", object: coreTalent.talent_name, issue: "贡献有规模但点击成交需提效", evidence: `${number(coreTalent.sessions)} 场，成交 ${currency(coreTalent.paid_amount)}，点击成交 ${ratio(coreTalent.click_deal_rate)}`, impact: currency(coreTalent.paid_amount), action: "复盘选品、价格和讲解脚本，下一场保持货盘可比后验证。", validation: "点击成交率、单场产出、支付买家", window: "下一场", tone: "warning" })
  const scaleTalent = talentRows.value.filter((item) => item.action_key === "focus" || item.action_key === "expand").sort((left, right) => right.single_output - left.single_output)[0]
  if (scaleTalent) rows.push({ id: `talent-scale-${scaleTalent.talent_id}`, priority: "P2", object: scaleTalent.talent_name, issue: "可增加场次验证", evidence: `${number(scaleTalent.sessions)} 场，单场 ${currency(scaleTalent.single_output)}，点击成交 ${ratio(scaleTalent.click_deal_rate)}`, impact: currency(scaleTalent.paid_amount), action: "增加一档合作场次，保持商品与价格可比，观察单场产出是否衰减。", validation: "边际单场产出、点击成交率", window: "1-2 周", tone: "opportunity" })
  return rows.slice(0, 5)
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
  tooltip: { trigger: "item", formatter: (params: { name: string; value: number }) => `${params.name}<br/>${number(params.value)} 人` },
  series: [{ type: "funnel", left: "5%", top: 18, bottom: 18, width: "90%", min: 0, max: Math.max(live.value?.viewers ?? 0, 1), minSize: "18%", maxSize: "100%", sort: "descending", gap: 4, label: { show: true, position: "inside", color: "#264235", fontSize: 11, lineHeight: 19, formatter: (params: { name: string; value: number }) => `${params.name}\n${number(params.value)} 人` }, data: live.value ? [
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
      <article class="panel live-funnel-panel">
        <div class="panel-heading"><div><p>店播漏斗</p><h2>观看到商品成交</h2></div><BarChart3 :size="18" /></div>
        <div class="live-funnel-layout">
          <BusinessChart :option="funnelOption" ariaLabel="店播观看商品点击成交漏斗及各阶段人数" :height="330" />
          <div class="live-funnel-rates">
            <div><span>观看 → 商品点击</span><strong>{{ funnelRateLabel(shopViewClickRate) }}</strong><small>{{ number(live.item_click_users) }} 点击 / {{ number(live.viewers) }} 观看</small></div>
            <div><span>商品点击 → 成交</span><strong>{{ funnelRateLabel(shopClickDealRate) }}</strong><small>{{ number(live.buyers) }} 买家 / {{ number(live.item_click_users) }} 点击</small></div>
            <div class="overall"><span>观看 → 成交</span><strong>{{ funnelRateLabel(shopOverallDealRate) }}</strong><small>{{ number(live.buyers) }} 买家 / {{ number(live.viewers) }} 观看</small></div>
          </div>
        </div>
        <p class="panel-footnote">观看点击率衡量商品露出承接，点击成交率衡量价格、货盘和信任承接；整体成交率为成交买家 / 店播观看人数。</p>
      </article>
    </section>

    <section class="panel live-daily-panel">
      <div class="panel-heading"><div><p>店播对象</p><h2>逐日漏斗与成交明细</h2></div><span class="panel-action">{{ number(daily.length) }} 个店播日</span></div>
      <div v-if="daily.length" class="live-daily-table-wrap"><table class="live-daily-table"><thead><tr><th>日期</th><th>观看人数</th><th>商品点击</th><th>观看点击率</th><th>支付买家</th><th>点击成交率</th><th>直播中成交</th><th>播后成交</th><th>店播成交</th><th>买家产出</th></tr></thead><tbody><tr v-for="item in daily.slice().reverse()" :key="item.stat_date"><td><strong>{{ item.stat_date }}</strong></td><td>{{ number(item.viewers) }}</td><td>{{ number(item.item_click_users) }}</td><td>{{ ratio(item.view_click_rate) }}</td><td>{{ number(item.buyers) }}</td><td>{{ ratio(item.click_deal_rate) }}</td><td>{{ currency(item.live_during_paid_amount) }}</td><td>{{ currency(item.post_paid_amount) }}</td><td><em>{{ currency(item.shop_paid_amount) }}</em></td><td>{{ currency(item.paid_amount_per_buyer) }}</td></tr></tbody></table></div>
      <EmptyState v-else title="暂无店播日明细" detail="当前范围没有店播转化日报。" />
      <p class="panel-footnote">店播按日期下钻；观看、点击、买家来自店播转化表，直播中、播后和店播成交来自直播概览，页面不把达播主播成交混入该漏斗。</p>
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

    <BusinessActionTable :rows="liveActionRows" eyebrow="直播动作" title="店播日期与达播主播行动" note="店播、达播分别验证" />
  </template>
  <section v-else-if="loading" class="loading-panel"><LoaderCircle :size="26" class="spinning" /><span>正在读取直播分析</span></section>
  <EmptyState v-else title="暂无直播分析数据" detail="当前日期范围没有直播概览或店播转化记录。" :icon="Radio" />
</template>

<style scoped>
.live-daily-panel { margin-top: 16px; overflow: hidden; }
.live-funnel-layout { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(170px, .75fr); align-items: center; gap: 14px; }
.live-funnel-layout > * { min-width: 0; }
.live-funnel-rates { display: grid; gap: 0; border-left: 1px solid #e4ebe7; padding-left: 16px; }
.live-funnel-rates > div { display: grid; gap: 5px; border-bottom: 1px solid #edf2ef; padding: 16px 0; }
.live-funnel-rates > div:last-child { border-bottom: 0; }
.live-funnel-rates span { color: #74867c; font-size: 10px; }
.live-funnel-rates strong { color: #16845b; font-size: 22px; font-weight: 740; line-height: 1.15; }
.live-funnel-rates small { color: #94a098; font-size: 9px; line-height: 1.5; }
.live-funnel-rates .overall strong { color: #d3922c; }
.live-daily-table-wrap { overflow-x: auto; margin-top: 12px; padding: 0 16px; }
.live-daily-table { width: 100%; min-width: 1050px; border-collapse: collapse; table-layout: fixed; }.live-daily-table th,.live-daily-table td { border-bottom: 1px solid #edf2ef; padding: 10px 8px; color: #66776e; font-size: 10px; text-align: right; }.live-daily-table th { color: #8c9991; background: #f8faf9; font-size: 9px; font-weight: 650; }.live-daily-table th:first-child,.live-daily-table td:first-child { width: 105px; text-align: left; }.live-daily-table td strong { color: #40564a; }.live-daily-table td em { color: #16845b; font-style: normal; font-weight: 700; }
@media (max-width: 760px) {
  .live-funnel-layout { grid-template-columns: 1fr; }
  .live-funnel-rates { grid-template-columns: repeat(3, minmax(0, 1fr)); border-top: 1px solid #e4ebe7; border-left: 0; padding-top: 8px; padding-left: 0; }
  .live-funnel-rates > div { border-right: 1px solid #edf2ef; border-bottom: 0; padding: 10px; }
  .live-funnel-rates > div:last-child { border-right: 0; }
  .live-funnel-rates strong { font-size: 18px; }
}
@media (max-width: 480px) {
  .live-funnel-rates { grid-template-columns: 1fr; }
  .live-funnel-rates > div { border-right: 0; border-bottom: 1px solid #edf2ef; padding: 11px 0; }
}
</style>
