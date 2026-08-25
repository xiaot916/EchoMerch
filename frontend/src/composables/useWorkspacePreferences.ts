import { ref, watch } from "vue"

const SIDEBAR_COLLAPSED_KEY = "echomerch.sidebar.collapsed"

function readSidebarPreference(): boolean {
  if (typeof window === "undefined") return false
  return window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "true"
}

const sidebarCollapsed = ref(readSidebarPreference())

watch(sidebarCollapsed, (collapsed) => {
  if (typeof window === "undefined") return
  window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(collapsed))
})

export function useWorkspacePreferences() {
  function toggleSidebar(): void {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  return {
    sidebarCollapsed,
    toggleSidebar,
  }
}
