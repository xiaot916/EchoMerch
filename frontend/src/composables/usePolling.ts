import { ref, onMounted, onUnmounted, type Ref } from "vue"

export type PollingControl = {
  running: Ref<boolean>
  start: () => void
  stop: () => void
  setRunning: (next: boolean) => void
}

/**
 * 后台轮询控制。
 *
 * 各采集页面会按"某任务正在运行"的语义定时刷新数据。这里把三处重复的
 * `setInterval` / `clearInterval` / `visibilitychange` 逻辑收敛成一个可复用
 * 的组合式函数，避免 ImportsView 里再手写多套定时器。
 *
 * 用法：
 *   const crawlPoll = usePolling({ intervalMs: 2500, tick: () => loadCrawlRuns() })
 *   crawlPoll.setRunning(activeCrawl.value?.status === "running")
 *   onUnmounted(() => crawlPoll.stop())
 *
 * 行为：
 * - 页面隐藏（document.visibilityState === "hidden"）时自动暂停，可见时恢复；
 * - `setRunning(false)` 立即停止，不会留下空转的定时器。
 */
export function usePolling(options: {
  intervalMs: number
  tick: () => void | Promise<void>
}): PollingControl {
  const running = ref(false)
  let timer: number | undefined

  function stop(): void {
    if (timer !== undefined) {
      window.clearInterval(timer)
      timer = undefined
    }
  }

  function start(): void {
    stop()
    timer = window.setInterval(async () => {
      if (document.visibilityState !== "hidden") {
        try {
          await options.tick()
        } catch (error) {
          // 轮询属于后台静默刷新，单次失败不应打断整条链路；
          // 下一次 tick 会继续重试。这里吞掉以避免控制台刷错误。
          void error
        }
      }
    }, options.intervalMs)
  }

  function setRunning(next: boolean): void {
    const shouldRun = next && document.visibilityState !== "hidden"
    if (running.value === shouldRun) return
    running.value = shouldRun
    if (shouldRun) start()
    else stop()
  }

  function handleVisibility(): void {
    setRunning(running.value)
  }

  onMounted(() => {
    document.addEventListener("visibilitychange", handleVisibility)
  })

  onUnmounted(() => {
    document.removeEventListener("visibilitychange", handleVisibility)
    stop()
  })

  return { running, start, stop, setRunning }
}
