import { computed, ref } from "vue"

import { fetchCaptureSummary } from "@/api"
import type { CaptureSummary } from "@/types"

const summary = ref<CaptureSummary>()
const loading = ref(false)
const error = ref("")
let initialized = false

async function loadCaptureSummary() {
  loading.value = true
  error.value = ""
  try {
    summary.value = await fetchCaptureSummary()
    initialized = true
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : "无法读取抓包分析库"
  } finally {
    loading.value = false
  }
}

export function useCaptureSummary() {
  async function ensureCaptureSummary() {
    if (initialized || loading.value) return
    await loadCaptureSummary()
  }

  return {
    summary,
    loading,
    error,
    hasSummary: computed(() => Boolean(summary.value?.file_count)),
    ensureCaptureSummary,
    loadCaptureSummary,
  }
}
