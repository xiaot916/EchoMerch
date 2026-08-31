import { createRouter, createWebHistory } from "vue-router"

import AppShell from "@/layout/AppShell.vue"
import { useAuth } from "@/composables/useAuth"
import { finishNavigation, startNavigation } from "@/composables/useNavigationLoading"

declare module "vue-router" {
  interface RouteMeta {
    title: string
    eyebrow: string
    requiresDashboard?: boolean
    surface: "business" | "system"
    permission?: string
    menuCode?: string
    aiPageKey?: string
  }
}

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  scrollBehavior(_to, _from, savedPosition) {
    return savedPosition || { top: 0, left: 0 }
  },
  routes: [
    {
      path: "/",
      component: AppShell,
      children: [
        { path: "", name: "overview", component: () => import("@/views/OverviewView.vue"), meta: { title: "经营概览", eyebrow: "天猫经营数据", requiresDashboard: true, surface: "business", permission: "analytics.read", aiPageKey: "overview" } },
        { path: "ai", name: "ai", component: () => import("@/views/AIDecisionView.vue"), meta: { title: "AI 决策中心", eyebrow: "经营数据助手", requiresDashboard: false, surface: "business", permission: "analytics.read" } },
        { path: "analytics", name: "analytics", component: () => import("@/views/AnalyticsView.vue"), meta: { title: "交易分析", eyebrow: "交易与效率", requiresDashboard: true, surface: "business", permission: "analytics.read", aiPageKey: "analytics" } },
        { path: "products", name: "products", component: () => import("@/views/ProductsView.vue"), meta: { title: "商品表现", eyebrow: "商品经营洞察", requiresDashboard: true, surface: "business", permission: "analytics.read", aiPageKey: "products" } },
        { path: "traffic", name: "traffic", component: () => import("@/views/TrafficView.vue"), meta: { title: "流量归因", eyebrow: "来源与访客质量", requiresDashboard: true, surface: "business", permission: "analytics.read", aiPageKey: "traffic" } },
        { path: "promotions", name: "promotions", component: () => import("@/views/PromotionsView.vue"), meta: { title: "推广分析", eyebrow: "渠道与投入产出", requiresDashboard: true, surface: "business", permission: "analytics.read", aiPageKey: "promotions" } },
        { path: "promotions/cps", name: "promotions-cps", component: () => import("@/views/CpsView.vue"), meta: { title: "CPS 分析", eyebrow: "商品推广 / CPS 渠道", requiresDashboard: true, surface: "business", permission: "analytics.read", aiPageKey: "promotions-cps" } },
        { path: "customers", name: "customers", component: () => import("@/views/CustomersView.vue"), meta: { title: "客户概况", eyebrow: "客户", requiresDashboard: true, surface: "business", permission: "analytics.read", aiPageKey: "customers" } },
        { path: "customers/members", name: "customer-members", component: () => import("@/views/MembersView.vue"), meta: { title: "会员分析", eyebrow: "客户与复购", requiresDashboard: true, surface: "business", permission: "analytics.read", aiPageKey: "customer-members" } },
        { path: "marketing/activities", name: "marketing-activities", component: () => import("@/views/ActivitiesView.vue"), meta: { title: "活动复盘", eyebrow: "营销活动", requiresDashboard: true, surface: "business", permission: "analytics.read", aiPageKey: "marketing-activities" } },
        { path: "marketing/flash-sale", name: "marketing-flash-sale", component: () => import("@/views/FlashSaleView.vue"), meta: { title: "淘宝秒杀", eyebrow: "营销活动 / 秒杀经营", requiresDashboard: false, surface: "business", permission: "analytics.read", aiPageKey: "marketing-flash-sale" } },
        { path: "marketing/new-customer", name: "marketing-new-customer", component: () => import("@/views/NewCustomerView.vue"), meta: { title: "新客折扣", eyebrow: "营销活动", requiresDashboard: true, surface: "business", permission: "analytics.read", aiPageKey: "marketing-new-customer" } },
        { path: "marketing/shopping-gold", name: "marketing-shopping-gold", component: () => import("@/views/MarketingChannelView.vue"), meta: { title: "购物金", eyebrow: "营销活动", requiresDashboard: true, surface: "business", permission: "analytics.read", aiPageKey: "marketing-shopping-gold" } },
        { path: "marketing/bybt", name: "marketing-bybt", component: () => import("@/views/MarketingChannelView.vue"), meta: { title: "百亿补贴", eyebrow: "营销活动", requiresDashboard: true, surface: "business", permission: "analytics.read", aiPageKey: "marketing-bybt" } },
        { path: "marketing/utry", name: "marketing-utry", component: () => import("@/views/UtryView.vue"), meta: { title: "U先试用", eyebrow: "营销活动 / 派样与复购", requiresDashboard: false, surface: "business", permission: "analytics.read", aiPageKey: "marketing-utry" } },
        { path: "service", name: "service", component: () => import("@/views/CustomerServiceView.vue"), meta: { title: "客服概览", eyebrow: "客服经营", requiresDashboard: true, surface: "business", permission: "analytics.read", aiPageKey: "service" } },
        { path: "service/performance", name: "service-performance", redirect: { name: "service" }, meta: { title: "客服概览", eyebrow: "客服经营", requiresDashboard: true, surface: "business", permission: "analytics.read" } },
        { path: "content", name: "content", component: () => import("@/views/ContentView.vue"), meta: { title: "内容概览", eyebrow: "内容经营", requiresDashboard: true, surface: "business", permission: "analytics.read", aiPageKey: "content" } },
        { path: "live", name: "live", component: () => import("@/views/LiveView.vue"), meta: { title: "直播分析", eyebrow: "内容与服务 / 直播经营", requiresDashboard: true, surface: "business", permission: "analytics.read", aiPageKey: "live" } },
        { path: "market", name: "market", component: () => import("@/views/MarketView.vue"), meta: { title: "市场洞察", eyebrow: "市场分析", requiresDashboard: true, surface: "business", permission: "analytics.read", aiPageKey: "market" } },
        { path: "brand-assets", name: "brand-assets", component: () => import("@/views/BrandAssetsView.vue"), meta: { title: "品牌资产", eyebrow: "品牌", requiresDashboard: false, surface: "system", permission: "brand_assets.read", aiPageKey: "brand-assets" } },
        { path: "products/analysis", name: "product-analysis", component: () => import("@/views/ProductAnalysisView.vue"), meta: { title: "单品分析", eyebrow: "商品经营 / 单品下钻", requiresDashboard: true, surface: "business", permission: "analytics.read", aiPageKey: "product-analysis" } },
        { path: "brand-assets/products", redirect: { name: "product-analysis" } },
        { path: "imports", name: "imports", redirect: { name: "imports-tasks" }, meta: { title: "数据采集", eyebrow: "采集任务与增量反馈", requiresDashboard: false, surface: "system", permission: "data.manage" } },
        { path: "imports/tasks", name: "imports-tasks", component: () => import("@/views/ImportsView.vue"), meta: { title: "数据采集", eyebrow: "采集任务与增量反馈", requiresDashboard: false, surface: "system", permission: "data.manage" } },
        { path: "imports/overview", name: "imports-overview", component: () => import("@/views/CollectionOverviewView.vue"), meta: { title: "采集状态", eyebrow: "数据库完整性与到达情况", requiresDashboard: false, surface: "system", permission: "data.manage" } },
        { path: "store-data", name: "store-data", component: () => import("@/views/StoreDataView.vue"), meta: { title: "店铺数据", eyebrow: "查询与导出", requiresDashboard: false, surface: "system", permission: "data.manage" } },
        { path: "inventory", name: "inventory", component: () => import("@/views/InventoryView.vue"), meta: { title: "库存管理", eyebrow: "商品编码与库存快照", requiresDashboard: false, surface: "system", permission: "analytics.read", aiPageKey: "inventory" } },
        { path: "imports/settings", name: "imports-settings", component: () => import("@/views/CollectionSettingsView.vue"), meta: { title: "采集设置", eyebrow: "采集环境与安全边界", requiresDashboard: false, surface: "system", permission: "data.manage" } },
        { path: "reviews", name: "reviews", component: () => import("@/views/ReviewsView.vue"), meta: { title: "评价分析", eyebrow: "商品质量与用户反馈", requiresDashboard: false, surface: "system", permission: "analytics.read", aiPageKey: "reviews" } },
        { path: "captures", name: "captures", component: () => import("@/views/CapturesView.vue"), meta: { title: "采集实验室", eyebrow: "开发诊断", requiresDashboard: false, surface: "system", permission: "system.manage" } },
        { path: "contracts", name: "contracts", component: () => import("@/views/ContractsView.vue"), meta: { title: "接口契约", eyebrow: "开发诊断", requiresDashboard: false, surface: "system", permission: "system.manage" } },
        { path: "operations", name: "operations", component: () => import("@/views/OperationsView.vue"), meta: { title: "批量操作", eyebrow: "Preview First", requiresDashboard: false, surface: "system", permission: "system.manage" } },
        { path: "system/users", name: "system-users", component: () => import("@/views/AccessView.vue"), meta: { title: "用户管理", eyebrow: "系统设置", requiresDashboard: false, surface: "system", permission: "system.manage" } },
        { path: "system/roles", name: "system-roles", component: () => import("@/views/RoleManagementView.vue"), meta: { title: "角色管理", eyebrow: "系统设置", requiresDashboard: false, surface: "system", permission: "system.manage" } },
        { path: "system/menus", name: "system-menus", component: () => import("@/views/MenuManagementView.vue"), meta: { title: "菜单管理", eyebrow: "系统设置", requiresDashboard: false, surface: "system", permission: "system.manage" } },
        { path: "system/apis", name: "system-apis", component: () => import("@/views/ApiPermissionView.vue"), meta: { title: "接口权限", eyebrow: "系统设置", requiresDashboard: false, surface: "system", permission: "system.manage" } },
        { path: "system/notifications", name: "system-notifications", component: () => import("@/views/NotificationView.vue"), meta: { title: "消息通知", eyebrow: "系统设置", requiresDashboard: false, surface: "system", permission: "system.manage" } },
        { path: "system/ai", name: "system-ai", component: () => import("@/views/AIConfigurationView.vue"), meta: { title: "AI 配置", eyebrow: "系统设置", requiresDashboard: false, surface: "system", permission: "system.manage" } },
        { path: "access", name: "access", redirect: { name: "system-users" }, meta: { title: "用户管理", eyebrow: "系统设置", requiresDashboard: false, surface: "system", permission: "system.manage" } },
      ],
    },
    {
      path: "/login",
      name: "login",
      component: () => import("@/views/LoginView.vue"),
      meta: { title: "登录", eyebrow: "EchoMerch", requiresDashboard: false, surface: "system" },
    },
    {
      path: "/forbidden",
      name: "forbidden",
      component: () => import("@/views/ForbiddenView.vue"),
      meta: { title: "无访问权限", eyebrow: "EchoMerch", requiresDashboard: false, surface: "system" },
    },
    {
      path: "/:pathMatch(.*)*",
      name: "not-found",
      component: () => import("@/views/NotFoundView.vue"),
      meta: { title: "页面不存在", eyebrow: "EchoMerch", requiresDashboard: false, surface: "system" },
    },
  ],
})

const routeMenuCodes: Record<string, string> = {
  overview: "route:overview", ai: "route:ai", analytics: "route:analytics", traffic: "route:traffic",
  customers: "route:customers", "customer-members": "route:customer-members", products: "route:products",
  "product-analysis": "route:product-analysis", reviews: "route:reviews", promotions: "route:promotions",
  "promotions-cps": "route:promotions-cps", "marketing-activities": "route:marketing-activities",
  "marketing-flash-sale": "route:marketing-flash-sale", "marketing-new-customer": "route:marketing-new-customer",
  "marketing-shopping-gold": "route:marketing-shopping-gold", "marketing-bybt": "route:marketing-bybt",
  "marketing-utry": "route:marketing-utry",
  service: "route:service", content: "route:content", live: "route:live", market: "route:market",
  "brand-assets": "route:brand-assets", "store-data": "route:store-data", inventory: "route:inventory", imports: "route:imports-tasks",
  "imports-tasks": "route:imports-tasks", "imports-overview": "route:imports-overview", "imports-settings": "route:imports-settings", "system-users": "route:system-users",
  "system-roles": "route:system-roles", "system-menus": "route:system-menus", "system-apis": "route:system-apis",
  "system-notifications": "route:system-notifications", access: "route:system-users",
  "system-ai": "route:system-ai",
}

router.beforeEach(async (to) => {
  startNavigation()
  const { can, canMenu, isAuthenticated, loadSession } = useAuth()
  await loadSession()
  if (to.name === "login") {
    return isAuthenticated.value
      ? { path: typeof to.query.redirect === "string" ? to.query.redirect : "/" }
      : true
  }
  if (!isAuthenticated.value) {
    return { name: "login", query: { redirect: to.fullPath } }
  }
  if (to.meta.permission && !can(to.meta.permission)) {
    return { name: "forbidden" }
  }
  const menuCode = to.meta.menuCode || routeMenuCodes[String(to.name)]
  if (menuCode && !canMenu(menuCode)) {
    return { name: "forbidden" }
  }
  return true
})

router.afterEach((to) => {
  if (typeof document !== "undefined") {
    document.title = to.meta.title ? `${to.meta.title} - EchoMerch` : "EchoMerch"
  }
  finishNavigation()
})

router.onError(() => {
  finishNavigation()
})

export default router
