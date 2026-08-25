import { computed, ref } from "vue"

const navigating = ref(false)
const progress = ref(0)
let finishTimer: ReturnType<typeof setTimeout> | undefined
let progressTimer: ReturnType<typeof setInterval> | undefined
let pendingNavigations = 0
let startedAt = 0
const MIN_VISIBLE_MS = 260

export function startNavigation(): void {
  if (finishTimer) clearTimeout(finishTimer)
  if (progressTimer) clearInterval(progressTimer)
  if (pendingNavigations === 0) startedAt = Date.now()
  pendingNavigations += 1
  progress.value = Math.max(progress.value, 8)
  navigating.value = true
  progressTimer = setInterval(() => {
    if (progress.value < 86) progress.value += Math.max(1, (86 - progress.value) * 0.12)
  }, 180)
}

export function finishNavigation(): void {
  if (finishTimer) clearTimeout(finishTimer)
  pendingNavigations = Math.max(0, pendingNavigations - 1)
  if (pendingNavigations > 0) return
  if (progressTimer) clearInterval(progressTimer)
  progress.value = 100
  const remaining = Math.max(80, MIN_VISIBLE_MS - (Date.now() - startedAt))
  finishTimer = setTimeout(() => {
    navigating.value = false
    progress.value = 0
    finishTimer = undefined
  }, remaining)
}

export function useNavigationLoading() {
  return {
    isNavigating: computed(() => navigating.value),
    progress: computed(() => progress.value),
  }
}
