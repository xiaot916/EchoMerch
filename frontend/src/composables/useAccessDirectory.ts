import { ref } from "vue"

import { fetchAccessDirectory } from "@/api"
import type { AccessDirectory } from "@/types"

const directory = ref<AccessDirectory | null>(null)
const loading = ref(false)
const error = ref("")

export function useAccessDirectory() {
  async function loadAccessDirectory(force = false): Promise<void> {
    if (loading.value || (directory.value && !force)) return
    loading.value = true
    error.value = ""
    try {
      directory.value = await fetchAccessDirectory()
    } catch (requestError) {
      error.value = requestError instanceof Error ? requestError.message : "权限目录读取失败。"
    } finally {
      loading.value = false
    }
  }

  return { directory, loading, error, loadAccessDirectory }
}
