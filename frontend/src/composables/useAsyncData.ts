import { onScopeDispose, shallowRef, type ShallowRef } from "vue"

interface AsyncDataOptions<T> {
  initialData?: T
  immediate?: boolean
  errorMessage?: string
}

interface AsyncDataState<T> {
  data: ShallowRef<T | undefined>
  loading: ShallowRef<boolean>
  error: ShallowRef<string>
  refresh: () => Promise<T | undefined>
  cancel: () => void
}

interface InitializedAsyncDataState<T> extends Omit<AsyncDataState<T>, "data"> {
  data: ShallowRef<T>
}

export function useAsyncData<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  options: AsyncDataOptions<T> & { initialData: T },
): InitializedAsyncDataState<T>
export function useAsyncData<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  options?: AsyncDataOptions<T>,
): AsyncDataState<T>
export function useAsyncData<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  options: AsyncDataOptions<T> = {},
): AsyncDataState<T> {
  const data = shallowRef<T | undefined>(options.initialData) as ShallowRef<T | undefined>
  const loading = shallowRef(false)
  const error = shallowRef("")
  let requestVersion = 0
  let activeController: AbortController | null = null

  function cancel(): void {
    requestVersion += 1
    activeController?.abort()
    activeController = null
    loading.value = false
  }

  async function refresh(): Promise<T | undefined> {
    const version = ++requestVersion
    activeController?.abort()
    const controller = new AbortController()
    activeController = controller
    loading.value = true
    error.value = ""
    try {
      const result = await fetcher(controller.signal)
      if (version !== requestVersion) return undefined
      data.value = result
      return result
    } catch (requestError) {
      if (version !== requestVersion || controller.signal.aborted) return undefined
      error.value = requestError instanceof Error
        ? requestError.message
        : options.errorMessage || "数据读取失败。"
      return undefined
    } finally {
      if (version === requestVersion) {
        loading.value = false
        activeController = null
      }
    }
  }

  onScopeDispose(cancel)
  if (options.immediate !== false) void refresh()

  return { data, loading, error, refresh, cancel }
}
