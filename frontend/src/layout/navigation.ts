import type { Component } from "vue"
import {
  Activity,
  Bot,
  BarChart3,
  BadgeCheck,
  ChartNoAxesCombined,
  Database,
  FileSearch,
  FolderKanban,
  Headphones,
  KeyRound,
  LayoutDashboard,
  LineChart,
  Menu,
  Megaphone,
  MessageSquareText,
  Settings2,
  PackageSearch,
  Rocket,
  Route,
  ShoppingCart,
  ShieldCheck,
  Store,
  Timer,
  UserCog,
  UsersRound,
} from "lucide-vue-next"

export type NavigationItem = {
  to: string
  label: string
  icon: Component
  note?: string
  permission?: string
  menuCode?: string
}

export type NavigationDomain = NavigationItem & {
  key: string
  items: NavigationItem[]
}

export type SidebarGroup = {
  key: string
  label: string
  icon: Component
  domainKeys: string[]
  domains: NavigationDomain[]
}

export const navigationDomains: NavigationDomain[] = [
  {
    key: "ai",
    to: "/ai",
    label: "AI 赋能",
    icon: Bot,
    items: [{ to: "/ai", label: "AI 决策中心", icon: Bot, permission: "analytics.read", menuCode: "route:ai" }],
  },
  {
    key: "home",
    to: "/",
    label: "首页",
    icon: LayoutDashboard,
    items: [{ to: "/", label: "经营概览", icon: LayoutDashboard, permission: "analytics.read", menuCode: "route:overview" }],
  },
  {
    key: "transaction",
    to: "/analytics",
    label: "交易",
    icon: ShoppingCart,
    items: [{ to: "/analytics", label: "交易分析", icon: ChartNoAxesCombined, permission: "analytics.read", menuCode: "route:analytics" }],
  },
  {
    key: "traffic",
    to: "/traffic",
    label: "流量",
    icon: Route,
    items: [{ to: "/traffic", label: "流量总览", icon: Route, permission: "analytics.read", menuCode: "route:traffic" }],
  },
  {
    key: "customers",
    to: "/customers",
    label: "客户",
    icon: UsersRound,
    items: [
      { to: "/customers", label: "客户概况", icon: UsersRound, permission: "analytics.read", menuCode: "route:customers" },
      { to: "/customers/members", label: "会员分析", icon: Activity, permission: "analytics.read", menuCode: "route:customer-members" },
    ],
  },
  {
    key: "products",
    to: "/products",
    label: "商品",
    icon: PackageSearch,
    items: [
      { to: "/products", label: "商品表现", icon: PackageSearch, permission: "analytics.read", menuCode: "route:products" },
      { to: "/products/analysis", label: "单品分析", icon: PackageSearch, permission: "analytics.read", menuCode: "route:product-analysis" },
      { to: "/reviews", label: "评价分析", icon: FileSearch, permission: "analytics.read", menuCode: "route:reviews" },
    ],
  },
  {
    key: "promotion",
    to: "/promotions",
    label: "商品推广",
    icon: Megaphone,
    items: [
      { to: "/promotions", label: "推广分析", icon: Megaphone, permission: "analytics.read", menuCode: "route:promotions" },
      { to: "/promotions/cps", label: "CPS 分析", icon: ChartNoAxesCombined, permission: "analytics.read", menuCode: "route:promotions-cps" },
    ],
  },
  {
    key: "marketing-activities",
    to: "/marketing/activities",
    label: "营销活动",
    icon: Rocket,
    items: [
      { to: "/marketing/activities", label: "活动复盘", icon: Activity, permission: "analytics.read", menuCode: "route:marketing-activities" },
      { to: "/marketing/flash-sale", label: "淘宝秒杀", icon: Timer, permission: "analytics.read", menuCode: "route:marketing-flash-sale" },
      { to: "/marketing/new-customer", label: "新客礼金", icon: UsersRound, permission: "analytics.read", menuCode: "route:marketing-new-customer" },
      { to: "/marketing/shopping-gold", label: "购物金", icon: Store, permission: "analytics.read", menuCode: "route:marketing-shopping-gold" },
      { to: "/marketing/bybt", label: "百亿补贴", icon: BarChart3, permission: "analytics.read", menuCode: "route:marketing-bybt" },
      { to: "/marketing/utry", label: "U先试用", icon: PackageSearch, permission: "analytics.read", menuCode: "route:marketing-utry" },
    ],
  },
  {
    key: "service",
    to: "/service",
    label: "客服",
    icon: Headphones,
    items: [
      { to: "/service", label: "客服概览", icon: Headphones, permission: "analytics.read", menuCode: "route:service" },
    ],
  },
  {
    key: "content",
    to: "/content",
    label: "内容",
    icon: Activity,
    items: [
      { to: "/content", label: "内容概览", icon: Activity, permission: "analytics.read", menuCode: "route:content" },
      { to: "/live", label: "直播分析", icon: Activity, permission: "analytics.read", menuCode: "route:live" },
    ],
  },
  {
    key: "market",
    to: "/market",
    label: "市场",
    icon: ChartNoAxesCombined,
    items: [{ to: "/market", label: "市场洞察", icon: ChartNoAxesCombined, permission: "analytics.read", menuCode: "route:market" }],
  },
  {
    key: "brand-assets",
    to: "/brand-assets",
    label: "品牌资产",
    icon: BadgeCheck,
    items: [
      { to: "/brand-assets", label: "品牌总览", icon: BadgeCheck, permission: "brand_assets.read", menuCode: "route:brand-assets" },
    ],
  },
  {
    key: "data",
    to: "/imports/tasks",
    label: "数据管理",
    icon: Database,
    items: [
      { to: "/store-data", label: "店铺数据", icon: Database, permission: "data.manage", menuCode: "route:store-data" },
      { to: "/inventory", label: "库存管理", icon: PackageSearch, permission: "analytics.read", menuCode: "route:inventory" },
      { to: "/imports/tasks", label: "数据采集", icon: Activity, permission: "data.manage", menuCode: "route:imports-tasks" },
      { to: "/imports/overview", label: "采集状态", icon: FileSearch, permission: "data.manage", menuCode: "route:imports-overview" },
      { to: "/imports/settings", label: "采集设置", icon: ShieldCheck, permission: "data.manage", menuCode: "route:imports-settings" },
    ],
  },
  {
    key: "system",
    to: "/access",
    label: "系统",
    icon: ShieldCheck,
    items: [
      { to: "/system/users", label: "用户管理", icon: UsersRound, permission: "system.manage", menuCode: "route:system-users" },
      { to: "/system/roles", label: "角色管理", icon: UserCog, permission: "system.manage", menuCode: "route:system-roles" },
      { to: "/system/menus", label: "菜单管理", icon: Menu, permission: "system.manage", menuCode: "route:system-menus" },
      { to: "/system/apis", label: "接口权限", icon: KeyRound, permission: "system.manage", menuCode: "route:system-apis" },
      { to: "/system/notifications", label: "消息通知", icon: MessageSquareText, permission: "system.manage", menuCode: "route:system-notifications" },
      { to: "/system/ai", label: "AI 配置", icon: Settings2, permission: "system.manage", menuCode: "route:system-ai" },
    ],
  },
]

const sidebarGroupDefinitions: Omit<SidebarGroup, "domains">[] = [
  {
    key: "workbench",
    label: "经营工作台",
    icon: LayoutDashboard,
    domainKeys: ["home", "transaction", "traffic", "ai"],
  },
  {
    key: "analysis",
    label: "经营分析",
    icon: LineChart,
    domainKeys: ["customers", "products", "brand-assets"],
  },
  {
    key: "promotion",
    label: "商品推广",
    icon: Megaphone,
    domainKeys: ["promotion"],
  },
  {
    key: "marketing-activities",
    label: "营销活动",
    icon: Rocket,
    domainKeys: ["marketing-activities"],
  },
  {
    key: "service-content",
    label: "内容与服务",
    icon: Headphones,
    domainKeys: ["service", "content", "market"],
  },
  {
    key: "data",
    label: "数据管理",
    icon: FolderKanban,
    domainKeys: ["data"],
  },
  {
    key: "system",
    label: "系统管理",
    icon: ShieldCheck,
    domainKeys: ["system"],
  },
]

function isPathMatch(path: string, target: string): boolean {
  return target === "/" ? path === "/" : path === target || path.startsWith(`${target}/`)
}

export function isNavigationItemActive(path: string, item: NavigationItem): boolean {
  return isPathMatch(path, item.to)
}

export function activeNavigationItemForPath(
  path: string,
  items: NavigationItem[],
): NavigationItem | undefined {
  return items
    .filter((item) => isPathMatch(path, item.to))
    .sort((left, right) => right.to.length - left.to.length)[0]
}

export function filterNavigation(
  can: (permission?: string) => boolean,
  canMenu: (menuCode?: string) => boolean = () => true,
): NavigationDomain[] {
  return navigationDomains.flatMap((domain) => {
    const items = domain.items.filter((item) => can(item.permission) && canMenu(item.menuCode))
    return items.length ? [{ ...domain, to: items[0].to, items }] : []
  })
}

export function filterSidebarGroups(
  can: (permission?: string) => boolean,
  canMenu: (menuCode?: string) => boolean = () => true,
): SidebarGroup[] {
  const visibleDomains = filterNavigation(can, canMenu)
  const domainsByKey = new Map(visibleDomains.map((domain) => [domain.key, domain]))

  return sidebarGroupDefinitions.flatMap((group) => {
    const domains = group.domainKeys
      .map((key) => domainsByKey.get(key))
      .filter((domain): domain is NavigationDomain => Boolean(domain))
    return domains.length ? [{ ...group, domains }] : []
  })
}

export function navigationDomainForPath(path: string, domains = navigationDomains): NavigationDomain {
  return domains.find((domain) => domain.items.some((item) => isPathMatch(path, item.to)))
    ?? domains[0]
    ?? navigationDomains[0]
}

export const brandIcon = Activity
