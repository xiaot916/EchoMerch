import { computed, ref } from "vue"

import { fetchDashboard } from "@/api"
import type { DashboardResponse } from "@/types"

const dashboard = ref<DashboardResponse>()
const loading = ref(false)
const error = ref("")
const startDate = ref("")
const endDate = ref("")
const currentStoreId = ref<number | null>(null)
let requestVersion = 0
let activeController: AbortController | null = null

async function loadDashboard(useFilter = false, storeId?: number) {
  const version = ++requestVersion
  activeController?.abort()
  const controller = new AbortController()
  activeController = controller
  loading.value = true
  error.value = ""
  try {
    dashboard.value = await fetchDashboard(
      useFilter ? startDate.value || undefined : undefined,
      useFilter ? endDate.value || undefined : undefined,
      storeId,
      controller.signal,
    )
    if (version !== requestVersion) return
    startDate.value = dashboard.value.range_start
    endDate.value = dashboard.value.range_end
    currentStoreId.value = storeId ?? null
  } catch (requestError) {
    if (version !== requestVersion || controller.signal.aborted) return
    error.value = requestError instanceof Error ? requestError.message : "无法读取数据"
  } finally {
    if (version === requestVersion) {
      loading.value = false
      activeController = null
    }
  }
}

export function useDashboard() {
  async function ensureDashboard(storeId?: number) {
    if (loading.value) return
    if (dashboard.value && (storeId === undefined || currentStoreId.value === storeId)) return
    await loadDashboard(false, storeId)
  }

  return {
    dashboard,
    loading,
    error,
    startDate,
    endDate,
    currentStoreId,
    dateLabel: computed(() =>
      dashboard.value ? `${dashboard.value.range_start} 至 ${dashboard.value.range_end}` : "等待数据",
    ),
    ensureDashboard,
    loadDashboard,
  }
}
