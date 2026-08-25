<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import { ArrowRight, ChevronLeft, ChevronRight, Database, Download, FileSearch, LoaderCircle, RefreshCw, Search } from "lucide-vue-next"

import EmptyState from "@/components/EmptyState.vue"
import { downloadStoreData, fetchStores, fetchStoreDataCatalog, fetchStoreDataPreview } from "@/api"
import type { StoreDataCatalog, StoreDataPreview, StoreRecord } from "@/types"
import { number } from "@/lib/format"

const stores = ref<StoreRecord[]>([])
const catalog = ref<StoreDataCatalog | null>(null)
const preview = ref<StoreDataPreview | null>(null)
const selectedStoreId = ref<number | null>(null)
const selectedKey = ref("")
const startDate = ref("")
const endDate = ref("")
const search = ref("")
const page = ref(1)
const pageSize = ref(50)
const loading = ref(false)
const previewLoading = ref(false)
const exporting = ref<"csv" | "xlsx" | "">("")
const error = ref("")
const previewError = ref("")

const selectedStore = computed(() => stores.value.find((item) => item.store_id === selectedStoreId.value) || stores.value[0])
const selectedDataset = computed(() => catalog.value?.datasets.find((item) => item.key === selectedKey.value) || catalog.value?.datasets[0])
const countTotal = computed(() => catalog.value?.datasets.reduce((total, item) => total + item.row_count, 0) ?? 0)
const pageCount = computed(() => Math.max(1, Math.ceil((preview.value?.total ?? 0) / (preview.value?.page_size ?? pageSize.value))))
const attentionCount = computed(() => (catalog.value?.stale_count ?? 0) + (catalog.value?.empty_count ?? 0))

function datasetStatusLabel(status: string, lagDays?: number | null): string {
  if (status === "current") return "已同步"
  if (status === "stale") return lagDays ? `落后 ${lagDays} 天` : "更新较慢"
  return "暂无数据"
}

async function loadCatalog(): Promise<void> {
  const store = selectedStore.value
  if (!store) return
  loading.value = true
  error.value = ""
  try {
    catalog.value = await fetchStoreDataCatalog(store.store_id)
    if (!catalog.value.datasets.some((item) => item.key === selectedKey.value)) selectedKey.value = catalog.value.datasets[0]?.key || ""
    const dataset = selectedDataset.value
    startDate.value = dataset?.first_date || ""
    endDate.value = dataset?.latest_date || ""
    page.value = 1
    await loadPreview()
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : "店铺数据暂不可用"
  } finally {
    loading.value = false
  }
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ""
  try {
    stores.value = await fetchStores()
    if (!selectedStoreId.value) selectedStoreId.value = stores.value[0]?.store_id ?? null
    await loadCatalog()
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : "店铺数据暂不可用"
  } finally {
    loading.value = false
  }
}

async function loadPreview(): Promise<void> {
  const store = selectedStore.value
  const dataset = selectedDataset.value
  if (!store || !dataset) return
  previewLoading.value = true
  previewError.value = ""
  try {
    preview.value = await fetchStoreDataPreview({
      storeId: store.store_id,
      dataset: dataset.key,
      startDate: startDate.value || undefined,
      endDate: endDate.value || undefined,
      page: page.value,
      pageSize: pageSize.value,
      search: search.value.trim() || undefined,
    })
  } catch (requestError) {
    preview.value = null
    previewError.value = requestError instanceof Error ? requestError.message : "预览数据暂不可用"
  } finally {
    previewLoading.value = false
  }
}

async function applyFilters(): Promise<void> {
  page.value = 1
  await loadPreview()
}

async function changePage(nextPage: number): Promise<void> {
  page.value = Math.min(Math.max(nextPage, 1), pageCount.value)
  await loadPreview()
}

async function exportData(format: "csv" | "xlsx"): Promise<void> {
  const store = selectedStore.value
  const dataset = selectedDataset.value
  if (!store || !dataset) return
  exporting.value = format
  previewError.value = ""
  try {
    const file = await downloadStoreData({
      storeId: store.store_id,
      dataset: dataset.key,
      format,
      startDate: startDate.value || undefined,
      endDate: endDate.value || undefined,
      search: search.value.trim() || undefined,
    })
    const url = URL.createObjectURL(file.blob)
    const anchor = document.createElement("a")
    anchor.href = url
    anchor.download = file.filename
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
  } catch (requestError) {
    previewError.value = requestError instanceof Error ? requestError.message : "导出失败"
  } finally {
    exporting.value = ""
  }
}

watch(selectedStoreId, () => { if (catalog.value) void loadCatalog() })
watch(selectedKey, () => {
  if (!catalog.value) return
  const dataset = selectedDataset.value
  startDate.value = dataset?.first_date || ""
  endDate.value = dataset?.latest_date || ""
  page.value = 1
  void loadPreview()
})
watch(pageSize, () => { page.value = 1; void loadPreview() })
onMounted(() => { void load() })
</script>

<template>
  <section class="module-hero capture-hero"><div><p>查询、预览与导出</p><h2>店铺数据</h2><span>按店铺和数据类型查看本地数据库，支持筛选、分页预览并导出 CSV 或 Excel。</span></div><div class="hero-actions"><RouterLink class="capture-refresh secondary-action" to="/imports/tasks">数据采集<ArrowRight :size="15" /></RouterLink><RouterLink class="capture-refresh secondary-action" to="/imports/overview">采集状态<ArrowRight :size="15" /></RouterLink><button class="capture-refresh" :disabled="loading" @click="load"><RefreshCw :size="16" :class="{ spinning: loading }" />刷新目录</button></div></section>
  <section v-if="loading && !catalog" class="loading-panel"><LoaderCircle :size="28" class="spinning" /><span>正在读取店铺数据目录</span></section>
  <section v-else-if="error" class="error-panel"><FileSearch :size="24" /><div><strong>店铺数据不可用</strong><p>{{ error }}</p></div><button @click="load">重试</button></section>
  <template v-else-if="catalog">
    <section class="architecture-metrics"><article class="panel capture-stat"><span>可查询数据集</span><strong>{{ number(catalog.available_count) }} / {{ number(catalog.datasets.length) }}</strong><small>{{ catalog.empty_count }} 个数据集尚无记录</small></article><article class="panel capture-stat"><span>记录总量</span><strong>{{ number(countTotal) }}</strong><small>各数据集记录数加总</small></article><article class="panel capture-stat"><span>数据库最新日期</span><strong>{{ catalog.reference_date || "--" }}</strong><small>以当前店铺最新入库日期为准</small></article><article class="panel capture-stat"><span>需要关注</span><strong>{{ number(attentionCount) }}</strong><small>{{ catalog.stale_count }} 个落后 · {{ catalog.empty_count }} 个为空</small></article></section>
    <section class="panel store-data-bridge"><div><Database :size="18" /><div><strong>本地数据库与采集任务已联动</strong><span>目录负责查数和导出；采集状态按表核对到达情况；采集任务统一执行经营数据、评价和问大家的增量更新。</span></div></div><div><RouterLink to="/imports/overview">检查缺失数据<ArrowRight :size="14" /></RouterLink><RouterLink to="/imports/tasks">进入采集任务<ArrowRight :size="14" /></RouterLink></div></section>
    <section class="panel store-data-panel">
      <div class="panel-heading store-data-heading"><div><p>本地数据库</p><h2>{{ selectedDataset?.label || "数据预览" }}<span v-if="selectedDataset" class="store-dataset-status" :class="selectedDataset.status">{{ datasetStatusLabel(selectedDataset.status, selectedDataset.lag_days) }}</span></h2></div><div class="store-data-actions"><button :disabled="Boolean(exporting) || previewLoading" @click="exportData('csv')"><Download :size="14" />{{ exporting === "csv" ? "导出中" : "导出 CSV" }}</button><button class="primary" :disabled="Boolean(exporting) || previewLoading" @click="exportData('xlsx')"><Download :size="14" />{{ exporting === "xlsx" ? "导出中" : "导出 Excel" }}</button></div></div>
      <p class="architecture-note">{{ selectedDataset?.description }}。仅开放白名单数据集，Cookie、Token、请求头与原始响应不会出现在预览和导出中。</p>
      <div class="store-data-filter"><label><span>店铺</span><select v-model.number="selectedStoreId"><option v-for="store in stores" :key="store.store_id" :value="store.store_id">{{ store.store_name }}</option></select></label><label><span>数据类型</span><select v-model="selectedKey"><option v-for="item in catalog.datasets" :key="item.key" :value="item.key">{{ item.label }} · {{ datasetStatusLabel(item.status, item.lag_days) }}</option></select></label><label><span>开始日期</span><input v-model="startDate" type="date" /></label><label><span>结束日期</span><input v-model="endDate" type="date" /></label><label class="store-search"><span>关键词</span><div><Search :size="14" /><input v-model="search" placeholder="搜索当前数据集" @keyup.enter="applyFilters" /></div></label><button class="capture-refresh" :disabled="previewLoading" @click="applyFilters"><Search :size="15" />查询</button></div>
      <div class="store-data-meta"><span><Database :size="14" />日期覆盖 {{ selectedDataset?.first_date || "--" }} 至 {{ selectedDataset?.latest_date || "--" }}</span><strong>筛选结果 {{ number(preview?.total || 0) }} 条</strong></div>
      <div v-if="previewLoading" class="loading-panel store-data-loading"><LoaderCircle :size="24" class="spinning" /><span>正在读取预览</span></div><div v-else-if="previewError" class="error-panel store-data-inline-error"><FileSearch :size="20" /><div><strong>数据读取失败</strong><p>{{ previewError }}</p></div></div><div v-else-if="preview?.rows.length" class="store-data-table-wrap"><table class="store-data-table"><thead><tr><th v-for="column in preview.columns" :key="column.key">{{ column.label }}</th></tr></thead><tbody><tr v-for="(row, index) in preview.rows" :key="index"><td v-for="column in preview.columns" :key="column.key" :title="String(row[column.key] ?? '')">{{ String(row[column.key] ?? "--") }}</td></tr></tbody></table></div><EmptyState v-else title="暂无预览数据" detail="当前筛选条件没有可展示的数据。" />
      <div class="store-data-pagination"><span>第 {{ preview?.page || page }} / {{ pageCount }} 页</span><div><label class="store-data-page-size"><span>每页</span><select v-model.number="pageSize"><option :value="20">20</option><option :value="50">50</option><option :value="100">100</option></select></label><button :disabled="page <= 1 || previewLoading" @click="changePage(page - 1)"><ChevronLeft :size="14" />上一页</button><button :disabled="page >= pageCount || previewLoading" @click="changePage(page + 1)">下一页<ChevronRight :size="14" /></button></div></div>
    </section>
  </template>
</template>
