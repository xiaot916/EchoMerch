import { computed, ref } from "vue"

import { fetchCapabilities } from "@/api"
import type { SystemCapabilities } from "@/types"

const capabilities = ref<SystemCapabilities>()
const loading = ref(false)
const error = ref("")
let initialized = false

async function loadCapabilities() {
  loading.value = true
  error.value = ""
  try {
    capabilities.value = await fetchCapabilities()
    initialized = true
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : "无法读取系统能力"
  } finally {
    loading.value = false
  }
}

export function useCapabilities() {
  async function ensureCapabilities() {
    if (initialized || loading.value) return
    await loadCapabilities()
  }

  return {
    capabilities,
    loading,
    error,
    isReadOnly: computed(() => capabilities.value?.mode === "read_only"),
    ensureCapabilities,
    loadCapabilities,
  }
}
