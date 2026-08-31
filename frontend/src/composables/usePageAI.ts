import { computed, ref } from "vue"

import { fetchAIPageProfiles } from "@/api"
import type { AIPageProfile } from "@/types"

const profiles = ref<AIPageProfile[]>([])
const loading = ref(false)
const error = ref("")
let pending: Promise<void> | null = null

async function ensureProfiles(): Promise<void> {
  if (profiles.value.length) return
  if (pending) return pending
  loading.value = true
  error.value = ""
  pending = fetchAIPageProfiles()
    .then((items) => {
      profiles.value = items
    })
    .catch((reason) => {
      error.value = reason instanceof Error ? reason.message : "页面 AI 配置加载失败"
    })
    .finally(() => {
      loading.value = false
      pending = null
    })
  return pending
}

export function usePageAI() {
  const profilesByKey = computed(() => new Map(profiles.value.map((item) => [item.key, item])))
  return {
    profiles,
    loading,
    error,
    ensureProfiles,
    profileFor: (pageKey: string | null | undefined) => profilesByKey.value.get(String(pageKey || "")) || null,
  }
}
