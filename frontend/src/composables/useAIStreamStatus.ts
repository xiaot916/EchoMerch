import { computed, onBeforeUnmount, ref } from "vue"
import type { AIStreamEvent } from "@/api"

type StreamPhase = "idle" | "preparing" | "streaming" | "stopping" | "complete" | "error" | "cancelled"

const FIRST_TOKEN_WAIT_MS = 10_000
const NEXT_TOKEN_WAIT_MS = 15_000

export function useAIStreamStatus() {
  const phase = ref<StreamPhase>("idle")
  const runId = ref<string | null>(null)
  const revision = ref(0)
  const now = ref(performance.now())
  const startedAt = ref(0)
  const modelStartedAt = ref(0)
  const firstTokenAt = ref(0)
  const lastTokenAt = ref(0)
  const latestStep = ref("")
  let timer: ReturnType<typeof setInterval> | undefined

  function ensureTimer() {
    if (timer) return
    timer = setInterval(() => { now.value = performance.now() }, 250)
  }

  function stopTimer() {
    if (timer) clearInterval(timer)
    timer = undefined
  }

  function start() {
    const timestamp = performance.now()
    phase.value = "preparing"
    runId.value = null
    revision.value = 0
    now.value = timestamp
    startedAt.value = timestamp
    modelStartedAt.value = 0
    firstTokenAt.value = 0
    lastTokenAt.value = 0
    latestStep.value = "正在准备数据"
    ensureTimer()
  }

  function accept(event: AIStreamEvent) {
    const timestamp = performance.now()
    now.value = timestamp
    if (event.run_id) runId.value = event.run_id
    if (typeof event.revision === "number" && event.revision >= revision.value) revision.value = event.revision
    if (event.event === "run" && event.phase) phase.value = event.phase as StreamPhase
    if (event.event === "run" && event.status) phase.value = event.status as StreamPhase
    if (event.event === "planner") latestStep.value = "正在理解经营问题"
    if (event.event === "skill") latestStep.value = "正在编排分析能力"
    if (event.event === "mcp") latestStep.value = event.status === "running" ? "正在读取经营数据" : (event.detail || latestStep.value)
    if (event.event === "model" && event.status === "running") {
      phase.value = "streaming"
      modelStartedAt.value = timestamp
      latestStep.value = "模型正在生成"
    }
    if (event.event === "token") {
      phase.value = "streaming"
      if (!firstTokenAt.value) firstTokenAt.value = timestamp
      lastTokenAt.value = timestamp
      latestStep.value = "模型正在生成"
    }
    if (event.event === "final") finish("complete")
    if (event.event === "error") finish("error")
  }

  function finish(nextPhase: Extract<StreamPhase, "complete" | "error" | "cancelled"> = "complete") {
    phase.value = nextPhase
    now.value = performance.now()
    stopTimer()
  }

  function cancel() {
    if (phase.value === "idle" || phase.value === "complete" || phase.value === "error" || phase.value === "cancelled") return
    phase.value = "stopping"
    latestStep.value = "正在停止生成"
  }

  const elapsedMs = computed(() => startedAt.value ? Math.max(0, now.value - startedAt.value) : 0)
  const title = computed(() => {
    if (phase.value === "stopping") return "正在停止生成"
    if (modelStartedAt.value && !firstTokenAt.value && now.value - modelStartedAt.value >= FIRST_TOKEN_WAIT_MS) return "正在等待模型首包"
    if (lastTokenAt.value && now.value - lastTokenAt.value >= NEXT_TOKEN_WAIT_MS) return "等待下一段模型输出"
    return latestStep.value || "正在准备数据"
  })
  const detail = computed(() => {
    if (modelStartedAt.value && !firstTokenAt.value && now.value - modelStartedAt.value >= FIRST_TOKEN_WAIT_MS) return "连接正常，模型仍在处理结构化证据"
    if (lastTokenAt.value && now.value - lastTokenAt.value >= NEXT_TOKEN_WAIT_MS) return "已保留当前内容，继续等待后续响应"
    return "实时展示可审计的能力与数据调用"
  })

  onBeforeUnmount(stopTimer)

  return { phase, runId, revision, elapsedMs, title, detail, start, accept, finish, cancel }
}
