<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import { RouterLink, RouterView, useRoute } from "vue-router"
import { Bot, Database, LoaderCircle, MoreHorizontal, X } from "lucide-vue-next"

import { useDashboard } from "@/composables/useDashboard"
import { fetchStores } from "@/api"
import type { StoreRecord } from "@/types"
import BusinessContextBar from "@/layout/BusinessContextBar.vue"
import NavigationSidebar from "@/layout/NavigationSidebar.vue"
import PageHeader from "@/layout/PageHeader.vue"
import RouteTabs from "@/layout/RouteTabs.vue"
import { filterNavigation } from "@/layout/navigation"
import { useAuth } from "@/composables/useAuth"
import { useWorkspacePreferences } from "@/composables/useWorkspacePreferences"
import AIAssistantDrawer from "@/components/AIAssistantDrawer.vue"

const route = useRoute()
const { can, canMenu } = useAuth()
const { dashboard, loading, error, startDate, endDate, currentStoreId, ensureDashboard, loadDashboard } = useDashboard()
const stores = ref<StoreRecord[]>([])
const storesReady = ref(false)
const activeStore = computed(() => stores.value.find((item) => item.store_id === currentStoreId.value) || stores.value[0] || null)

const pageTitle = computed(() => route.meta.title || "经营概览")
const pageEyebrow = computed(() => route.meta.eyebrow || "天猫经营数据")
const requiresDashboard = computed(() => route.meta.requiresDashboard !== false)
const visibleDomains = computed(() => filterNavigation(can, canMenu))
const mobileItems = computed(() => visibleDomains.value.flatMap((domain) => domain.items))
const mobileNavigation = computed(() => mobileItems.value.slice(0, 4))
const mobileMoreNavigation = computed(() => mobileItems.value.slice(4))

const showBusinessContext = computed(() => route.meta.surface === "business")
const mobileMenuOpen = ref(false)
const aiOpen = ref(false)
const { sidebarCollapsed, toggleSidebar } = useWorkspacePreferences()

const aiPageContext = computed(() => {
  const pageKey = String(route.name || "overview")
  const plans: Record<string, { section: string; data_domains: string[]; datasets: string[]; page_goal: string; recommended_questions: string[] }> = {
    overview: { section: "经营总盘", data_domains: ["overview", "traffic", "product", "customer", "promotion", "customer-service"], datasets: ["store_overview", "traffic_sources", "products", "product_catalog", "customers", "members", "promotion_campaigns", "customer_service", "live", "cps"], page_goal: "定位成交变化的主要驱动并形成今日优先动作", recommended_questions: ["为什么最近成交下降？给我最重要的三个原因和动作", "成交下降是流量还是转化问题？", "今天最应该先做什么？"] },
    analytics: { section: "交易分析", data_domains: ["overview", "product", "customer"], datasets: ["store_overview", "products", "product_catalog", "customers"], page_goal: "拆解支付、退款、转化、客单价和成交结构", recommended_questions: ["支付金额下降具体掉在哪个漏斗环节？", "下钻客单价下降的系列、类型和商品", "退款变化是否影响净支付？"] },
    traffic: { section: "流量", data_domains: ["traffic", "overview", "product"], datasets: ["traffic_sources", "store_overview", "products"], page_goal: "判断流量来源质量、转化承接和 UV 价值", recommended_questions: ["哪些流量来源值得加预算？", "有没有高流量低转化的来源？", "流量变化是否带来成交变化？"] },
    products: { section: "商品", data_domains: ["product", "promotion", "inventory"], datasets: ["products", "product_catalog", "promotion_products", "taobao_current_prices", "taobao_price_risks", "taobao_activity_snapshots", "inventory_snapshots"], page_goal: "按系列→类型→商品定位成交、客单价和价格活动风险", recommended_questions: ["下钻客单价下降的系列、类型和商品", "哪些商品高流量低转化？", "主销商品有没有价格或活动风险？"] },
    "product-analysis": { section: "单品分析", data_domains: ["product", "promotion", "inventory"], datasets: ["products", "product_catalog", "promotion_products", "taobao_current_prices", "taobao_price_risks", "taobao_activity_snapshots", "inventory_snapshots"], page_goal: "结合单品成交、推广、价格、活动和库存给出经营动作", recommended_questions: ["这个单品为什么转化变化？", "这个商品的价格和库存风险是什么？", "它适合继续投放吗？"] },
    promotions: { section: "推广", data_domains: ["promotion", "product"], datasets: ["promotion_campaigns", "promotion_adgroups", "promotion_keywords", "promotion_crowds", "promotion_products", "products"], page_goal: "从场景→计划→单元→关键词/人群/商品定位投放效率", recommended_questions: ["哪些推广场景应该降预算？", "帮我找高花费低产出的计划", "推广成交主要依赖哪些商品？"] },
    "promotions-cps": { section: "CPS", data_domains: ["promotion", "live", "product"], datasets: ["cps", "live", "products"], page_goal: "区分 CPS 付款、结算、佣金和达人贡献，评估渠道效率", recommended_questions: ["CPS 付款和结算的差异是什么？", "哪些达人值得复盘？", "佣金成本是否吞噬了渠道价值？"] },
    customers: { section: "客户", data_domains: ["customer", "overview", "product"], datasets: ["customers", "store_overview", "products"], page_goal: "分析新客、老客、回访和复购对成交的贡献", recommended_questions: ["最近成交下降是新客还是老客造成的？", "哪些客户人群值得召回？", "复购数据覆盖是否完整？"] },
    "customer-members": { section: "会员", data_domains: ["customer", "overview"], datasets: ["members", "member_channels", "customers", "store_overview"], page_goal: "分析会员资产、招募、成交和复购", recommended_questions: ["会员成交占比变化说明什么？", "哪个入会渠道质量更高？", "会员复购应该先做什么？"] },
    service: { section: "客服", data_domains: ["customer-service", "overview", "product"], datasets: ["customer_service", "products", "product_catalog", "store_overview"], page_goal: "定位咨询→接待→成交漏斗、客服账号差异和服务风险", recommended_questions: ["客服分析一下，最重要的问题和动作是什么？", "哪个客服账号承接最弱？", "客服成交和店铺整体成交是否同步？"] },
    content: { section: "内容", data_domains: ["content", "promotion", "product"], datasets: ["content", "promotion_contents", "products", "store_overview"], page_goal: "评估内容曝光、互动、商品点击和种草成交", recommended_questions: ["内容带来的成交质量怎么样？", "哪些内容值得继续做？", "内容流量为什么没有转化？"] },
    live: { section: "直播", data_domains: ["live", "product", "promotion"], datasets: ["live", "live_store_performance", "live_talent_reports", "products", "store_overview"], page_goal: "拆分店播与达播，定位直播漏斗和商品承接", recommended_questions: ["店播和达播哪个更有效？", "直播成交下降掉在哪个环节？", "直播间主推商品需要调整吗？"] },
    market: { section: "市场", data_domains: ["market", "product"], datasets: ["market_rankings", "market_keywords", "products"], page_goal: "将市场需求/竞品观察与店铺商品成交结合，形成验证机会", recommended_questions: ["当前市场有哪些竞品机会？", "哪些搜索词值得小预算验证？", "市场信号和店铺成交是否匹配？"] },
    reviews: { section: "评价", data_domains: ["reviews", "product", "overview", "customer-service"], datasets: ["review_records", "ask_records", "products", "product_catalog", "store_overview", "customer_service"], page_goal: "从评价问题、问大家和商品经营数据中定位用户反馈与业务动作", recommended_questions: ["评价里最重要的商品问题是什么？", "哪些商品问题率最高？", "问大家未回答的问题会影响哪些商品承接？"] },
    "marketing-activities": { section: "活动", data_domains: ["campaign", "overview", "product", "traffic"], datasets: ["store_activity_calendar_events", "store_overview", "products", "traffic_sources", "promotion_campaigns"], page_goal: "比较活动前中后成交、流量、商品和推广变化", recommended_questions: ["这次活动带来了什么真实变化？", "活动商品承接是否达标？", "活动后哪些指标需要补救？"] },
    "marketing-flash-sale": { section: "秒杀", data_domains: ["campaign", "product"], datasets: ["taobao_flash_sale_overviews", "taobao_flash_sale_items", "products", "store_overview"], page_goal: "判断秒杀商品曝光、转化、成交和活动承接", recommended_questions: ["秒杀商品哪个最值得复盘？", "秒杀成交低是曝光还是转化问题？", "秒杀活动是否带来店铺成交？"] },
    "marketing-new-customer": { section: "新客礼金", data_domains: ["campaign", "customer"], datasets: ["new_customer_discount", "store_overview", "customers", "products"], page_goal: "评估新客礼金带来的新客成交和店铺增量信号", recommended_questions: ["新客礼金带来的成交质量怎么样？", "新客礼金转化下降原因是什么？", "这个活动应该继续吗？"] },
    "marketing-shopping-gold": { section: "购物金", data_domains: ["campaign", "customer"], datasets: ["shopping_gold", "store_overview", "customers"], page_goal: "分析购物金充值、使用、成交和退款风险", recommended_questions: ["购物金对成交有什么贡献？", "充值和使用之间是否健康？", "购物金应该优先优化哪一步？"] },
    "marketing-bybt": { section: "百亿补贴", data_domains: ["campaign", "product"], datasets: ["bybt", "products", "store_overview"], page_goal: "评估百亿补贴商品成交、转化和店铺承接", recommended_questions: ["百补成交变化的主要原因是什么？", "百补商品是否带来新客？", "百补商品的价格和库存风险是什么？"] },
    inventory: { section: "库存", data_domains: ["inventory", "product"], datasets: ["inventory_catalog", "inventory_snapshots", "products", "product_catalog"], page_goal: "把库存快照与商品销量结合，识别断货、低库存和滞销风险", recommended_questions: ["哪些主销商品最有断货风险？", "库存覆盖和最近销量是否匹配？", "帮我找低库存且成交贡献高的商品"] },
    "brand-assets": { section: "品牌资产", data_domains: ["brand", "customer", "product"], datasets: ["brand_asset_daily_overviews", "brand_asset_daily_metrics", "customers", "products"], page_goal: "解释品牌资产、人群关系和成交的联动变化", recommended_questions: ["品牌资产最近最重要的变化是什么？", "哪些人群关系值得重点经营？", "品牌资产变化和店铺成交是否同步？"] },
  }
  const plan = plans[pageKey] || plans.overview
  return { page_key: pageKey, page: pageTitle.value, route: route.fullPath, ...plan, filters: { query: route.query, start_date: startDate.value, end_date: endDate.value } }
})

function loadCurrentDashboard(useFilter = false): Promise<void> {
  return loadDashboard(useFilter, activeStore.value?.store_id)
}

function ensureCurrentDashboard(): Promise<void> {
  return ensureDashboard(activeStore.value?.store_id)
}

function isMobileActive(path: string): boolean {
  return route.path === path || route.path.startsWith(`${path}/`)
}

onMounted(async () => {
  try {
    stores.value = await fetchStores()
  } catch {
    stores.value = []
  } finally {
    storesReady.value = true
    currentStoreId.value = activeStore.value?.store_id ?? null
    if (showBusinessContext.value) void ensureCurrentDashboard()
  }
})

watch(showBusinessContext, (visible) => {
  if (visible && storesReady.value) void ensureCurrentDashboard()
}, { immediate: true })

watch(() => route.path, () => {
  mobileMenuOpen.value = false
})
</script>

<template>
  <main class="app-shell" :class="{ 'sidebar-is-collapsed': sidebarCollapsed }">
    <NavigationSidebar :collapsed="sidebarCollapsed" @toggle="toggleSidebar" />

    <section class="workspace">
      <PageHeader :title="pageTitle" :eyebrow="pageEyebrow" :show-business-context="showBusinessContext" :loading="loading" :sidebar-collapsed="sidebarCollapsed" @refresh="loadCurrentDashboard(true)" @toggle-sidebar="toggleSidebar" />
      <RouteTabs />

      <div class="content" :class="{ 'content-ai': route.name === 'ai' }">
        <BusinessContextBar
          v-if="showBusinessContext && route.name !== 'ai'"
          :store="activeStore"
          :start-date="startDate"
          :end-date="endDate"
          :loading="loading"
          @update:start-date="startDate = $event"
          @update:end-date="endDate = $event"
          @submit="loadCurrentDashboard(true)"
        />

        <section class="page-outlet">
          <RouterView v-slot="{ Component, route: pageRoute }">
            <component :is="Component" :key="pageRoute.fullPath" />
          </RouterView>

          <div v-if="requiresDashboard && !dashboard && !error" class="page-state-overlay">
            <section class="loading-panel">
              <LoaderCircle :size="28" class="spinning" /><span>正在读取历史经营数据</span>
            </section>
          </div>

          <div v-else-if="requiresDashboard && error" class="page-state-overlay">
            <section class="error-panel">
              <Database :size="25" />
              <div><strong>数据源暂不可用</strong><p>{{ error }}</p></div>
              <button @click="loadCurrentDashboard(true)">重试</button>
            </section>
          </div>
        </section>
      </div>
    </section>

    <button v-if="['analytics.read', 'brand_assets.read'].includes(String(route.meta.permission || '')) && route.name !== 'ai'" class="ai-floating-button" title="打开当前页面 AI 助手" @click="aiOpen = true"><Bot :size="19" /><span>AI</span></button>
    <AIAssistantDrawer
      :open="aiOpen"
      :domain="route.name === 'traffic' ? 'traffic' : route.name === 'promotions' || route.name === 'promotions-cps' ? 'promotion' : route.name === 'market' ? 'market' : route.name === 'reviews' ? 'reviews' : route.name === 'service' ? 'customer-service' : route.name === 'content' ? 'content' : route.name === 'live' ? 'live' : route.name?.toString().startsWith('marketing-') ? 'campaign' : route.name === 'products' || route.name === 'product-analysis' ? 'product' : route.name === 'customers' || route.name === 'customer-members' ? 'customer' : 'auto'"
      :title="pageTitle"
      :store-id="activeStore?.store_id"
      :start-date="startDate"
      :end-date="endDate"
      :page-context="aiPageContext"
      @close="aiOpen = false"
    />

    <div v-if="mobileMenuOpen" class="mobile-more-menu">
      <div class="mobile-more-heading"><strong>更多页面</strong><button class="icon-button" title="关闭更多页面" @click="mobileMenuOpen = false"><X :size="17" /></button></div>
      <RouterLink v-for="item in mobileMoreNavigation" :key="item.to" :to="item.to" class="mobile-more-link">
        <component :is="item.icon" :size="17" /><span>{{ item.label }}</span><small v-if="item.note">{{ item.note }}</small>
      </RouterLink>
    </div>

    <nav class="mobile-nav" aria-label="移动端主导航">
      <RouterLink v-for="item in mobileNavigation" :key="item.to" :to="item.to" :class="{ active: isMobileActive(item.to) }">
        <component :is="item.icon" :size="18" /><span>{{ item.label }}</span>
      </RouterLink>
      <button v-if="mobileMoreNavigation.length" class="mobile-nav-more" :class="{ active: mobileMenuOpen || mobileMoreNavigation.some((item) => isMobileActive(item.to)) }" title="打开更多页面" @click="mobileMenuOpen = !mobileMenuOpen">
        <MoreHorizontal :size="18" /><span>更多</span>
      </button>
    </nav>
  </main>
</template>
