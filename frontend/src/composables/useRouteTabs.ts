import { ref, watch } from "vue"
import type { RouteLocationNormalizedLoaded, Router } from "vue-router"

export type WorkspaceRouteTab = {
  path: string
  title: string
  pinned?: boolean
}

const ROUTE_TABS_KEY = "echomerch.workspace.tabs"
const MAX_ROUTE_TABS = 7
const defaultTab: WorkspaceRouteTab = { path: "/", title: "经营概览", pinned: true }
const ROUTE_ALIASES: Record<string, string> = {
  "/brand-assets/products": "/products/analysis",
  "/service/performance": "/service",
  "/imports": "/imports/tasks",
}

function canonicalTab(tab: WorkspaceRouteTab): WorkspaceRouteTab {
  const path = ROUTE_ALIASES[tab.path] || tab.path
  return { ...tab, path, title: path === "/service" ? "客服概览" : tab.title }
}

function readTabs(): WorkspaceRouteTab[] {
  if (typeof window === "undefined") return [{ ...defaultTab }]

  try {
    const saved = JSON.parse(window.localStorage.getItem(ROUTE_TABS_KEY) || "[]")
    if (!Array.isArray(saved)) return [{ ...defaultTab }]

    const restored = saved.filter((tab): tab is WorkspaceRouteTab => (
      typeof tab?.path === "string"
      && tab.path.startsWith("/")
      && typeof tab?.title === "string"
      && tab.path !== "/login"
      && tab.path !== "/forbidden"
    ))
    const withoutHome = restored.map(canonicalTab).filter((tab) => tab.path !== "/")
    const unique = withoutHome.filter((tab, index, all) => all.findIndex((item) => item.path === tab.path) === index)
    return [{ ...defaultTab }, ...unique.slice(-MAX_ROUTE_TABS + 1)]
  } catch {
    return [{ ...defaultTab }]
  }
}

const tabs = ref<WorkspaceRouteTab[]>(readTabs())

watch(tabs, (value) => {
  if (typeof window === "undefined") return
  window.localStorage.setItem(ROUTE_TABS_KEY, JSON.stringify(value))
}, { deep: true })

function isWorkspaceRoute(route: RouteLocationNormalizedLoaded): boolean {
  return route.path !== "/login" && route.name !== "forbidden" && route.name !== "not-found"
}

function routeTitle(route: RouteLocationNormalizedLoaded): string {
  return typeof route.meta.title === "string" ? route.meta.title : "工作台"
}

export function useRouteTabs() {
  function syncCurrentRoute(route: RouteLocationNormalizedLoaded): void {
    if (!isWorkspaceRoute(route)) return

    const existing = tabs.value.find((tab) => tab.path === route.fullPath)
    if (existing) {
      existing.title = routeTitle(route)
      return
    }

    tabs.value.push({ path: route.fullPath, title: routeTitle(route) })
    const removableTabs = tabs.value.filter((tab) => !tab.pinned)
    if (removableTabs.length > MAX_ROUTE_TABS - 1) {
      const oldest = removableTabs[0]
      tabs.value.splice(tabs.value.findIndex((tab) => tab.path === oldest.path), 1)
    }
  }

  async function closeTab(path: string, router: Router, activePath: string): Promise<void> {
    const index = tabs.value.findIndex((tab) => tab.path === path)
    if (index < 0 || tabs.value[index].pinned) return

    const wasActive = path === activePath
    tabs.value.splice(index, 1)

    if (!wasActive) return
    const next = tabs.value[Math.min(index, tabs.value.length - 1)] || defaultTab
    await router.push(next.path)
  }

  async function reloadTab(path: string, router: Router): Promise<void> {
    if (router.currentRoute.value.fullPath !== path) {
      await router.push(path)
      return
    }
    if (typeof window !== "undefined") window.location.reload()
  }

  async function closeOtherTabs(path: string, router: Router, activePath: string): Promise<void> {
    tabs.value = tabs.value.filter((tab) => tab.pinned || tab.path === path)
    if (activePath !== path && router.currentRoute.value.fullPath !== path) await router.push(path)
  }

  async function closeTabsToSide(path: string, side: "left" | "right", router: Router, activePath: string): Promise<void> {
    const index = tabs.value.findIndex((tab) => tab.path === path)
    if (index < 0) return
    tabs.value = tabs.value.filter((tab, tabIndex) => {
      if (tab.pinned) return true
      return side === "left" ? tabIndex >= index : tabIndex <= index
    })
    if (activePath !== path && !tabs.value.some((tab) => tab.path === activePath)) {
      await router.push(path)
    }
  }

  return {
    tabs,
    syncCurrentRoute,
    closeTab,
    reloadTab,
    closeOtherTabs,
    closeTabsToSide,
  }
}
