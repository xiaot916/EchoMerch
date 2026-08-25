<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { AlertTriangle, ChevronLeft, ChevronRight, CheckCircle2, Clock3, Database, LoaderCircle, PackageSearch, RefreshCw, Search, ShieldCheck } from "lucide-vue-next"

import { fetchInventoryAnalysis, fetchInventoryManagement, fetchInventorySyncStatus, fetchStores, syncInventoryNow } from "@/api"
import type { InventoryAnalysisResponse, InventoryManagementResponse, InventorySyncStatusResponse, StoreRecord } from "@/types"
import { useAuth } from "@/composables/useAuth"
import { number } from "@/lib/format"

const stores = ref<StoreRecord[]>([])
const selectedStoreId = ref<number | null>(null)
const data = ref<InventoryManagementResponse | null>(null)
const analysis = ref<InventoryAnalysisResponse | null>(null)
const syncStatus = ref<InventorySyncStatusResponse | null>(null)
const loading = ref(false)
const analysisLoading = ref(false)
const error = ref("")
const query = ref("")
const series = ref("")
const specification = ref("")
const size = ref("")
const stockStatus = ref("")
const page = ref(1)
const pageSize = ref(50)
const activeView = ref<"store" | "company" | "packages">("store")
const analysisQuery = ref("")
const analysisStatus = ref("")
const syncing = ref(false)
const syncNotice = ref("")
const syncNoticeTone = ref<"success" | "warning" | "error">("success")
let autoRefreshTimer: ReturnType<typeof setInterval> | null = null
const { can } = useAuth()
const canSync = computed(() => can("data.manage"))

const pageCount = computed(() => Math.max(1, Math.ceil((data.value?.total || 0) / (data.value?.page_size || pageSize.value))))
const summary = computed(() => data.value?.summary || {})
const statusLabel = (value: string) => value || "未知"
const formatQuantity = (value: number | null) => value == null ? "未采集" : number(value)
const metric = (value: unknown) => typeof value === "number" ? value : Number(value || 0)
const snapshotLabel = computed(() => {
  if (!data.value?.latest_snapshot_at) return "暂无库存快照"
  const stamp = data.value.latest_snapshot_at.replace("T", " ").replace(/\+.*$/, "")
  return `${data.value.latest_business_day || "--"} · ${stamp}`
})
const snapshotAgeLabel = computed(() => {
  const age = data.value?.snapshot_age_minutes
  if (age === null || age === undefined) return "暂无可用快照"
  if (age < 1) return "刚刚更新"
  return `${age} 分钟前更新`
})
const refreshMinutes = computed(() => syncStatus.value?.refresh_minutes || 60)
const nextRefreshLabel = computed(() => {
  const anchor = syncStatus.value?.last_attempt_at || syncStatus.value?.latest_snapshot_at
  if (!anchor) return "等待首次采集"
  const timestamp = Date.parse(anchor)
  if (Number.isNaN(timestamp)) return "等待下一次采集"
  const remaining = Math.ceil((timestamp + refreshMinutes.value * 60_000 - Date.now()) / 60_000)
  return remaining <= 0 ? "已到刷新时间" : `约 ${remaining} 分钟后`
})
const refreshPlanLabel = computed(() => syncStatus.value?.configured ? `后台每 ${refreshMinutes.value} 分钟自动采集` : "配置凭证后自动采集")
const collectionStatusLabel = computed(() => {
  const status = syncStatus.value?.status
  if (syncStatus.value?.credential_status === "invalid" || status === "credential_invalid") return "凭证异常"
  if (syncStatus.value?.credential_status === "refresh_required") return "凭证待刷新"
  if (status === "success") return "采集正常"
  if (status === "no_data") return "平台返回空数据"
  if (status === "failed") return "最近采集失败"
  if (status === "not_configured" || syncStatus.value?.credential_status === "not_configured") return "未配置凭证"
  if (status === "never_run") return "尚未采集"
  return "需要关注"
})
const collectionStatusDetail = computed(() => {
  const status = syncStatus.value
  if (!status) return "正在读取采集状态。"
  if (status.credential_status === "invalid" || status.status === "credential_invalid") return "凭证校验失败，请到“采集设置”重新填写 Refresh Token。"
  if (status.credential_status === "refresh_required") return "Access Token 已过期；可点击“验证并刷新”，或填写新的 Refresh Token。"
  if (status.status === "failed") return `${status.error_message || "吉客云接口请求失败"}；上次有效快照会保留。`
  if (status.status === "no_data") return "本次接口没有返回库存行，未将空结果当作零库存。"
  if (status.status === "not_configured" || status.credential_status === "not_configured") return "请到“采集设置”填写或更新 Refresh Token。"
  if (status.status === "never_run") return "还没有库存快照，请先点击“立即同步库存”。"
  if (status.freshness_status === "stale") return `快照已超过 ${status.refresh_minutes} 分钟未更新，建议重新采集。`
  return `最近尝试 ${status.last_attempt_at ? status.last_attempt_at.replace("T", " ").replace(/\+.*$/, "") : "--"} · ${status.row_count} 条快照`
})

async function load(): Promise<void> {
  loading.value = true
  error.value = ""
  try {
    if (!stores.value.length) {
      stores.value = await fetchStores()
      selectedStoreId.value = stores.value[0]?.store_id ?? null
    }
    const [management, companyAnalysis, latestSyncStatus] = await Promise.all([
      fetchInventoryManagement({
      storeId: selectedStoreId.value,
      query: query.value.trim() || undefined,
      series: series.value || undefined,
      specification: specification.value || undefined,
      size: size.value || undefined,
      stockStatus: stockStatus.value || undefined,
      page: page.value,
      pageSize: pageSize.value,
      }),
      fetchInventoryAnalysis({ storeId: selectedStoreId.value }),
      fetchInventorySyncStatus(selectedStoreId.value),
    ])
    data.value = management
    analysis.value = companyAnalysis
    syncStatus.value = latestSyncStatus
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : "库存管理数据暂不可用"
  } finally {
    loading.value = false
  }
}

async function loadAnalysis(): Promise<void> {
  if (!selectedStoreId.value) return
  analysisLoading.value = true
  try {
    analysis.value = await fetchInventoryAnalysis({
      storeId: selectedStoreId.value,
      query: analysisQuery.value.trim() || undefined,
      stockStatus: analysisStatus.value || undefined,
    })
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : "库存分析数据暂不可用"
  } finally {
    analysisLoading.value = false
  }
}

async function applyAnalysisFilters(): Promise<void> {
  await loadAnalysis()
}

async function applyFilters(): Promise<void> {
  page.value = 1
  await load()
}

async function changePage(nextPage: number): Promise<void> {
  if (nextPage < 1 || nextPage > pageCount.value) return
  page.value = nextPage
  await load()
}

async function syncNow(): Promise<void> {
  syncing.value = true
  syncNotice.value = ""
  syncNoticeTone.value = "success"
  error.value = ""
  try {
    const result = await syncInventoryNow(selectedStoreId.value)
    const first = result.results[0]
    if (!result.configured || first?.status === "not_configured") {
      syncNoticeTone.value = "warning"
      syncNotice.value = "吉客云库存凭证尚未配置，请到“采集设置”填写 Refresh Token 后再同步。"
    } else if (first?.status === "failed") {
      syncNoticeTone.value = "error"
      syncNotice.value = `库存采集失败：${first.error_message || "吉客云接口请求失败"}。库存页会保留上次有效快照，请验证凭证后重试。`
    } else if (first?.status === "no_data") {
      syncNoticeTone.value = "warning"
      syncNotice.value = "吉客云本次返回空数据，未覆盖上次库存快照；这不等于真实零库存。"
    } else if (!first) {
      syncNoticeTone.value = "warning"
      syncNotice.value = "没有找到可同步的店铺，请先配置店铺与吉客云库存接口。"
    } else {
      syncNotice.value = `库存采集完成：${first.row_count ?? 0} 条快照，货品主档 ${first.goods_master_count ?? 0} 条。`
    }
    await load()
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : "库存同步失败"
  } finally {
    syncing.value = false
  }
}

watch([selectedStoreId, pageSize], () => {
  if (selectedStoreId.value) {
    page.value = 1
    void load()
  }
})

onMounted(() => { void load() })
onMounted(() => {
  autoRefreshTimer = setInterval(() => {
    if (!loading.value && !syncing.value) void load()
  }, 60_000)
})
onBeforeUnmount(() => {
  if (autoRefreshTimer) clearInterval(autoRefreshTimer)
  autoRefreshTimer = null
})
</script>

<template>
  <section class="module-hero inventory-hero">
    <div class="inventory-hero-copy">
      <div class="inventory-eyebrow"><span>库存与商品编码</span><span class="inventory-live-badge" :class="{ 'is-pending': !syncStatus?.configured }"><i></i>{{ syncStatus?.configured ? "自动同步" : "等待配置" }}</span></div>
      <h2>库存管理</h2>
      <span>按系列、规格、尺码和货品编码查看最新库存快照，未采集与真实零库存分开判断。</span>
      <div class="inventory-hero-meta"><span><Clock3 :size="13" />{{ refreshPlanLabel }}</span><span><Database :size="13" />{{ snapshotAgeLabel }}</span></div>
    </div>
    <div class="hero-actions">
      <button class="capture-refresh secondary-action" :disabled="loading" title="重新读取当前库存页面数据" @click="load"><RefreshCw :size="16" :class="{ spinning: loading }" />刷新视图</button>
      <button v-if="canSync" class="capture-refresh" :disabled="loading || syncing" title="从吉客云读取库存快照与货品主档" @click="syncNow"><RefreshCw :size="16" :class="{ spinning: syncing }" />{{ syncing ? "同步中" : "立即同步库存" }}</button>
    </div>
  </section>

  <section v-if="loading && !data" class="loading-panel"><LoaderCircle :size="28" class="spinning" /><span>正在读取库存目录与快照</span></section>
  <section v-else-if="error" class="error-panel"><PackageSearch :size="22" /><div><strong>库存数据不可用</strong><p>{{ error }}</p></div><button @click="load">重试</button></section>
  <template v-else-if="data">
    <div v-if="syncNotice" class="collection-alert" :class="syncNoticeTone === 'error' ? 'collection-alert-error' : syncNoticeTone === 'warning' ? 'collection-alert-warning' : 'collection-context-note'"><AlertTriangle v-if="syncNoticeTone !== 'success'" :size="16" /><CheckCircle2 v-else :size="16" /><span>{{ syncNotice }}</span></div>
    <section class="architecture-metrics inventory-metrics">
      <article class="panel capture-stat inventory-stat-card"><span>商品映射</span><strong>{{ number(summary.catalog_count || 0) }}</strong><small>店铺日常商品编码</small></article>
      <article class="panel capture-stat inventory-stat-card"><span>已匹配库存</span><strong>{{ number(summary.matched_count || 0) }}</strong><small>有快照记录的映射</small></article>
      <article class="panel capture-stat inventory-stat-card"><span>低 / 零库存</span><strong>{{ number((summary.low_stock_count || 0) + (summary.zero_stock_count || 0)) }}</strong><small>低库存 {{ summary.low_stock_count || 0 }} · 零库存 {{ summary.zero_stock_count || 0 }}</small></article>
      <article class="panel capture-stat inventory-stat-card"><span>未匹配快照</span><strong>{{ number(summary.unmatched_count || 0) }}</strong><small>不能直接判定为 0</small></article>
    </section>

    <section class="panel inventory-status-bar">
      <div class="inventory-snapshot-card"><span class="inventory-status-icon"><Database :size="18" /></span><div><p>最新库存快照</p><strong>{{ snapshotLabel }}</strong><span>{{ snapshotAgeLabel }}</span></div></div>
      <div class="inventory-collection-state" :class="`state-${syncStatus?.status || 'unknown'}`"><div class="inventory-state-heading"><i></i><strong>{{ collectionStatusLabel }}</strong></div><span>{{ collectionStatusDetail }}</span><small v-if="syncStatus?.credential_detail"><ShieldCheck :size="12" />{{ syncStatus.credential_detail }}</small></div>
      <div class="inventory-refresh-plan"><div class="inventory-plan-heading"><RefreshCw :size="14" />自动刷新计划</div><strong>{{ refreshPlanLabel }}</strong><span>下次检查：{{ nextRefreshLabel }}</span><small>货品主档与组合关系每日同步一次 · 页面每分钟检查状态</small></div>
    </section>

    <section class="inventory-view-tabs" role="tablist" aria-label="库存分析视图">
      <button type="button" :class="{ active: activeView === 'store' }" @click="activeView = 'store'">店铺商品库存 <small>{{ number(data.total) }}</small></button>
      <button type="button" :class="{ active: activeView === 'company' }" @click="activeView = 'company'">公司货品库存 <small>{{ number(analysis?.company_summary.sku_count || 0) }}</small></button>
      <button type="button" :class="{ active: activeView === 'packages' }" @click="activeView = 'packages'">组合货品 <small>{{ number(metric(analysis?.package_summary.package_count)) }}</small></button>
    </section>

    <section v-if="activeView === 'store'" class="panel inventory-panel">
      <div class="panel-heading"><div><p>商品库存清单</p><h2>系列 → 规格 → 尺码 → 编码</h2></div><strong class="inventory-total">{{ number(data.total) }} 条</strong></div>
      <div class="inventory-filters">
        <label><span>店铺</span><select v-model.number="selectedStoreId"><option v-for="store in stores" :key="store.store_id" :value="store.store_id">{{ store.store_name }}</option></select></label>
        <label><span>系列</span><select v-model="series"><option value="">全部系列</option><option v-for="item in data.dimensions.series" :key="item" :value="item">{{ item }}</option></select></label>
        <label><span>规格</span><select v-model="specification"><option value="">全部规格</option><option v-for="item in data.dimensions.specification" :key="item" :value="item">{{ item }}</option></select></label>
        <label><span>尺码</span><select v-model="size"><option value="">全部尺码</option><option v-for="item in data.dimensions.size" :key="item" :value="item">{{ item }}</option></select></label>
        <label><span>库存状态</span><select v-model="stockStatus"><option value="">全部状态</option><option value="有库存">有库存</option><option value="低库存">低库存</option><option value="零库存">零库存</option><option value="未匹配库存">未匹配库存</option></select></label>
        <label class="inventory-search"><span>编码 / 商品</span><div><Search :size="14" /><input v-model="query" placeholder="如 L56L01" @keyup.enter="applyFilters" /></div></label>
        <button class="capture-refresh" :disabled="loading" @click="applyFilters"><Search :size="15" />查询</button>
      </div>
      <div class="inventory-table-wrap">
        <table class="inventory-table">
          <thead><tr><th>系列</th><th>规格</th><th>尺码</th><th>片数</th><th>货品编码</th><th>可用库存</th><th>仓库</th><th>状态</th></tr></thead>
          <tbody>
            <tr v-for="row in data.rows" :key="row.id">
              <td class="strong-cell">{{ row.series || "未归类" }}</td><td>{{ row.specification || "--" }}</td><td>{{ row.size || "--" }}</td><td>{{ row.pieces ?? "--" }}</td>
              <td><code>{{ row.goods_no }}</code><small v-if="row.catalog_match_count > 1">编码对应 {{ row.catalog_match_count }} 个商品</small></td>
              <td class="quantity-cell">{{ formatQuantity(row.available_quantity) }}</td><td>{{ row.warehouse_count ? `${row.warehouse_count} 个` : "--" }}</td>
              <td><span class="inventory-status" :class="row.stock_status === '有库存' ? 'is-good' : row.stock_status === '低库存' ? 'is-low' : row.stock_status === '零库存' ? 'is-zero' : 'is-unmatched'">{{ statusLabel(row.stock_status) }}</span></td>
            </tr>
            <tr v-if="!data.rows.length"><td colspan="8" class="inventory-empty">当前筛选条件没有商品记录</td></tr>
          </tbody>
        </table>
      </div>
      <div class="inventory-pagination"><span>第 {{ data.page }} / {{ pageCount }} 页</span><div><label><span>每页</span><select v-model.number="pageSize"><option :value="20">20</option><option :value="50">50</option><option :value="100">100</option></select></label><button :disabled="data.page <= 1 || loading" @click="changePage(data.page - 1)"><ChevronLeft :size="14" />上一页</button><button :disabled="data.page >= pageCount || loading" @click="changePage(data.page + 1)">下一页<ChevronRight :size="14" /></button></div></div>
    </section>

    <section v-else class="inventory-analysis-stack">
      <section class="inventory-analysis-toolbar panel">
        <div><p>{{ activeView === 'company' ? '公司货品库存分析' : '组合货品关系' }}</p><strong>{{ activeView === 'company' ? '看公司仓库真实可用货品，和店铺编码映射分开' : '查看 ERP 组合主档与组成 SKU，组合关系每天同步一次' }}</strong></div>
        <div class="inventory-analysis-actions">
          <label v-if="activeView === 'company'"><span>筛选状态</span><select v-model="analysisStatus" @change="applyAnalysisFilters"><option value="">全部货品</option><option value="零库存">缺货</option><option value="低库存">低库存</option><option value="有库存">有库存</option></select></label>
          <label class="inventory-analysis-search"><span>查询货品 / 编码</span><input v-model="analysisQuery" placeholder="如 Z27L42 或 大鱼" @keyup.enter="applyAnalysisFilters" /></label>
          <button class="capture-refresh" :disabled="analysisLoading" @click="applyAnalysisFilters"><Search :size="15" />查询</button>
        </div>
      </section>

      <template v-if="analysis">
        <section v-if="activeView === 'company'" class="inventory-company-layout">
          <div class="architecture-metrics inventory-analysis-metrics">
            <article class="panel capture-stat"><span>公司货品 SKU</span><strong>{{ number(analysis.company_summary.sku_count || 0) }}</strong><small>最新快照去重后</small></article>
            <article class="panel capture-stat"><span>可用库存总量</span><strong>{{ number(analysis.company_summary.available_quantity || 0) }}</strong><small>{{ number(analysis.company_summary.warehouse_count || 0) }} 个仓库</small></article>
            <article class="panel capture-stat"><span>缺货 SKU</span><strong class="metric-danger">{{ number(analysis.company_summary.zero_stock_count || 0) }}</strong><small>可用库存 ≤ 0</small></article>
            <article class="panel capture-stat"><span>低库存 SKU</span><strong class="metric-warning">{{ number(analysis.company_summary.low_stock_count || 0) }}</strong><small>可用库存 1–10</small></article>
          </div>
          <section class="panel inventory-panel">
            <div class="panel-heading"><div><p>公司货品明细</p><h2>货品编码 → SKU → 可用库存</h2></div><strong class="inventory-total">{{ number(analysis.company_rows.length) }} 条</strong></div>
            <div class="inventory-table-wrap"><table class="inventory-table company-inventory-table"><thead><tr><th>货品编码</th><th>货品 / SKU</th><th>系列</th><th>可用库存</th><th>仓库</th><th>映射状态</th><th>状态</th></tr></thead><tbody><tr v-for="row in analysis.company_rows" :key="row.key"><td><code>{{ row.goods_no || row.sku_no || '--' }}</code><small v-if="row.sku_barcode">条码 {{ row.sku_barcode }}</small></td><td><strong>{{ row.goods_name || '--' }}</strong><small>{{ row.sku_name || '--' }}</small></td><td>{{ row.series || '未映射' }}<small>{{ row.specification || '' }} {{ row.size || '' }}</small></td><td class="quantity-cell">{{ number(row.available_quantity) }}</td><td>{{ row.warehouse_count }} 个</td><td><span class="mapping-pill" :class="row.catalog_match_count ? 'mapped' : 'unmapped'">{{ row.catalog_match_count ? '已映射店铺商品' : '公司货品未映射' }}</span></td><td><span class="inventory-status" :class="row.stock_status === '有库存' ? 'is-good' : row.stock_status === '低库存' ? 'is-low' : 'is-zero'">{{ row.stock_status }}</span></td></tr><tr v-if="!analysis.company_rows.length"><td colspan="7" class="inventory-empty">没有匹配到公司货品</td></tr></tbody></table></div>
          </section>
          <section class="panel warehouse-summary-panel"><div class="panel-heading"><div><p>仓库分布</p><h2>按仓库识别缺货与库存集中</h2></div></div><div class="warehouse-grid"><article v-for="warehouse in analysis.warehouse_summary" :key="warehouse.warehouse_id"><div><strong>{{ warehouse.warehouse_name || warehouse.warehouse_id }}</strong><span>{{ warehouse.sku_count }} 个 SKU · 可用 {{ number(warehouse.available_quantity) }}</span></div><div class="warehouse-status"><em class="is-good">有货 {{ warehouse.in_stock_count }}</em><em class="is-low">低库存 {{ warehouse.low_stock_count }}</em><em class="is-zero">缺货 {{ warehouse.zero_stock_count }}</em></div></article></div></section>
        </section>

        <section v-else class="panel inventory-panel">
          <div class="panel-heading"><div><p>组合货品清单</p><h2>组合编码 → 组成 SKU → 单套用量</h2></div><strong class="inventory-total">{{ number(analysis.package_rows.length) }} 条</strong></div>
          <div class="package-explanation"><PackageSearch :size="17" /><span>这里只展示 ERP 组合主档和组成关系，不计算组合库存，也不把组合装库存与普通 SKU 相加；实际库存请到“公司货品库存”查看。</span></div>
          <div v-if="analysis.warnings.length" class="inventory-warning-list"><span v-for="warning in analysis.warnings" :key="warning">{{ warning }}</span></div>
          <div class="architecture-metrics inventory-analysis-metrics package-metrics"><article class="panel capture-stat"><span>组合货品</span><strong>{{ number(metric(analysis.package_summary.package_count)) }}</strong><small>已同步组合主档</small></article><article class="panel capture-stat"><span>已同步明细</span><strong>{{ number(metric(analysis.package_summary.with_components)) }}</strong><small>已有组成 SKU 关系</small></article><article class="panel capture-stat"><span>组成 SKU</span><strong>{{ number(metric(analysis.package_summary.component_count)) }}</strong><small>全部组合明细行</small></article><article class="panel capture-stat"><span>待补组合明细</span><strong class="metric-warning">{{ number(metric(analysis.package_summary.without_components)) }}</strong><small>主档存在但组成关系为空</small></article></div>
          <div class="inventory-table-wrap"><table class="inventory-table package-table"><thead><tr><th>组合货品编码</th><th>组合货品</th><th>组成 SKU 与用量</th><th>同步状态</th></tr></thead><tbody><tr v-for="row in analysis.package_rows" :key="row.key"><td><code>{{ row.goods_no || row.sku_no || '--' }}</code></td><td><strong>{{ row.goods_name || '--' }}</strong><small>{{ row.sku_name || '--' }}</small></td><td><span v-if="row.component_summary.length" class="component-list">{{ row.component_summary.join(' · ') }}</span><span v-else class="muted-text">尚未同步组成明细</span></td><td><span class="inventory-status" :class="row.stock_status === '已同步明细' ? 'is-good' : 'is-unmatched'">{{ row.stock_status }}</span></td></tr><tr v-if="!analysis.package_rows.length"><td colspan="4" class="inventory-empty">当前没有组合货品数据；请先完成每日组合主档同步</td></tr></tbody></table></div>
        </section>
      </template>
      <section v-else class="loading-panel"><LoaderCircle :size="22" class="spinning" /><span>正在读取库存分析</span></section>
    </section>
  </template>
</template>

<style scoped>
.inventory-hero { display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.inventory-status-bar { display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 14px 16px; }
.inventory-status-bar > div { display: flex; align-items: center; gap: 10px; }
.inventory-status-bar svg { color: var(--accent); }
.inventory-status-bar strong, .inventory-status-bar span, .inventory-status-bar small { display: block; }
.inventory-status-bar span, .inventory-status-bar small { margin-top: 3px; color: var(--text-muted); font-size: 11px; }
.inventory-collection-state { display: grid !important; min-width: 220px; gap: 2px !important; border-left: 1px solid var(--line); padding-left: 16px; }
.inventory-collection-state strong { font-size: 11px; }
.inventory-collection-state span, .inventory-collection-state small { color: var(--text-muted); font-size: 10px; line-height: 1.45; }
.inventory-collection-state.state-success strong { color: #19734a; }
.inventory-collection-state.state-failed strong, .inventory-collection-state.state-credential_invalid strong { color: #b24f4f; }
.inventory-collection-state.state-no_data strong, .inventory-collection-state.state-not_configured strong { color: #956a1d; }
.collection-alert-error { border-color: #efccc6; color: #b64d3e; background: #fff1ef; }
.collection-alert-warning { border-color: #f0d5ab; color: #9a631a; background: #fff9ed; }
.inventory-panel { overflow: hidden; }
.inventory-view-tabs { display: flex; gap: 4px; margin: 2px 0 10px; padding: 4px; border: 1px solid var(--line); border-radius: 7px; background: #f7faf8; }
.inventory-view-tabs button { display: inline-flex; align-items: center; gap: 7px; border: 0; border-radius: 5px; padding: 9px 13px; color: var(--text-muted); background: transparent; font-size: 12px; cursor: pointer; }
.inventory-view-tabs button.active { color: #174d37; background: #fff; box-shadow: 0 1px 4px rgba(25, 65, 45, .09); font-weight: 650; }
.inventory-view-tabs small { color: var(--accent); font-size: 10px; }
.inventory-analysis-stack { display: grid; gap: 10px; }
.inventory-analysis-toolbar { display: flex; align-items: end; justify-content: space-between; gap: 18px; padding: 14px 16px; }
.inventory-analysis-toolbar p, .warehouse-summary-panel p { margin: 0 0 4px; color: var(--text-muted); font-size: 11px; }
.inventory-analysis-toolbar strong { color: var(--text); font-size: 14px; }
.inventory-analysis-actions { display: flex; align-items: end; gap: 9px; }
.inventory-analysis-actions label { display: grid; gap: 5px; min-width: 130px; }
.inventory-analysis-actions label > span { color: var(--text-muted); font-size: 11px; }
.inventory-analysis-actions select, .inventory-analysis-actions input { min-height: 34px; border: 1px solid var(--line); border-radius: 4px; padding: 0 9px; background: #fff; font-size: 12px; }
.inventory-analysis-search { min-width: 220px !important; }
.inventory-analysis-metrics { margin: 0; }
.metric-danger { color: #b24f4f !important; }.metric-warning { color: #956a1d !important; }
.inventory-company-layout { display: grid; gap: 10px; }
.warehouse-summary-panel { padding: 14px 16px; }
.warehouse-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 8px; }
.warehouse-grid article { display: grid; gap: 9px; border: 1px solid #e6eee9; border-radius: 6px; padding: 11px; background: #fbfdfc; }
.warehouse-grid article > div:first-child { display: grid; gap: 3px; }.warehouse-grid span, .warehouse-grid small { color: var(--text-muted); font-size: 10px; }
.warehouse-status { display: flex; flex-wrap: wrap; gap: 5px; }.warehouse-status em { border-radius: 4px; padding: 3px 5px; font-style: normal; font-size: 10px; }.warehouse-status .is-good { color: #19734a; background: #eff9f2; }.warehouse-status .is-low { color: #956a1d; background: #fff9e9; }.warehouse-status .is-zero { color: #b24f4f; background: #fff3f3; }
.mapping-pill { display: inline-flex; border-radius: 4px; padding: 3px 6px; font-size: 10px; }.mapping-pill.mapped { color: #19734a; background: #eff9f2; }.mapping-pill.unmapped { color: #956a1d; background: #fff9e9; }
.package-explanation { display: flex; align-items: center; gap: 8px; margin: 0 16px 12px; border: 1px solid #e3eee7; border-radius: 6px; padding: 9px 10px; color: #5d7466; background: #f7fbf8; font-size: 11px; line-height: 1.5; }.package-explanation svg { flex: 0 0 auto; color: var(--accent); }
.inventory-warning-list { display: grid; gap: 5px; margin: 0 16px 12px; }.inventory-warning-list span { border-radius: 5px; padding: 7px 9px; color: #956a1d; background: #fff9e9; font-size: 11px; }
.package-metrics { margin: 0 16px 12px; }.component-list { color: #536d5f; font-size: 11px; }.muted-text { color: var(--text-subtle); font-size: 11px; }
.inventory-total { color: var(--accent); font-size: 13px; }
.inventory-filters { display: flex; flex-wrap: wrap; align-items: end; gap: 10px; padding: 0 16px 16px; }
.inventory-filters label { display: grid; gap: 5px; min-width: 118px; }
.inventory-filters label > span { color: var(--text-muted); font-size: 11px; }
.inventory-filters select, .inventory-filters input { min-height: 34px; border: 1px solid var(--line); border-radius: 4px; padding: 0 9px; background: #fff; font-size: 12px; }
.inventory-search { min-width: 190px !important; flex: 1; }
.inventory-search > div { display: flex; align-items: center; gap: 6px; min-height: 34px; border: 1px solid var(--line); border-radius: 4px; padding: 0 9px; background: #fff; }
.inventory-search input { min-height: 30px; flex: 1; border: 0; padding: 0; outline: 0; }
.inventory-table-wrap { overflow-x: auto; border-top: 1px solid var(--line); }
.inventory-table { width: 100%; min-width: 820px; border-collapse: collapse; font-size: 12px; }
.inventory-table th { padding: 11px 12px; color: var(--text-muted); background: #f7faf8; font-size: 11px; font-weight: 650; text-align: left; white-space: nowrap; }
.inventory-table td { padding: 12px; border-top: 1px solid #edf2ef; color: #52655b; vertical-align: middle; white-space: nowrap; }
.inventory-table tr:hover td { background: #fbfdfc; }
.strong-cell, .quantity-cell { color: #203b2c !important; font-weight: 650; }
.inventory-table code { color: #2e654c; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; }
.inventory-table td small { display: block; margin-top: 4px; color: var(--warning); font-size: 10px; }
.inventory-status { display: inline-flex; min-width: 60px; justify-content: center; border: 1px solid; border-radius: 3px; padding: 3px 6px; font-size: 11px; }
.inventory-status.is-good { border-color: #b9dfc8; color: #19734a; background: #eff9f2; }
.inventory-status.is-low { border-color: #ead7a7; color: #956a1d; background: #fff9e9; }
.inventory-status.is-zero { border-color: #edc7c7; color: #b24f4f; background: #fff3f3; }
.inventory-status.is-unmatched { border-color: #cfdad4; color: #6e7d75; background: #f5f7f6; }
.inventory-empty { padding: 36px !important; color: var(--text-subtle) !important; text-align: center; }
.inventory-pagination { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 16px; color: var(--text-muted); font-size: 11px; }
.inventory-pagination > div, .inventory-pagination label { display: flex; align-items: center; gap: 8px; }
.inventory-pagination select { min-height: 28px; border: 1px solid var(--line); border-radius: 4px; padding: 0 6px; background: #fff; }
.inventory-pagination button { display: inline-flex; align-items: center; gap: 4px; min-height: 29px; border: 1px solid var(--line); border-radius: 4px; padding: 0 8px; color: #5c7166; background: #fff; font-size: 11px; }
.inventory-pagination button:disabled { cursor: not-allowed; opacity: .45; }
@media (max-width: 760px) { .inventory-hero, .inventory-status-bar, .inventory-pagination, .inventory-analysis-toolbar { align-items: flex-start; flex-direction: column; } .inventory-filters, .inventory-analysis-actions { align-items: stretch; width: 100%; } .inventory-filters label, .inventory-analysis-actions label { flex: 1 1 135px; } .inventory-view-tabs { overflow-x: auto; } .inventory-collection-state { width: 100%; border-top: 1px solid var(--line); border-left: 0; padding-top: 10px; padding-left: 0; } }

/* Inventory first-screen hierarchy: make freshness and automation scannable. */
.inventory-hero {
  min-height: 142px;
  align-items: flex-start;
  padding: 24px 26px;
  border-color: #d9e5df;
  background: #fbfdfc;
}
.inventory-hero-copy { display: grid; min-width: 0; gap: 8px; }
.inventory-eyebrow { display: flex; align-items: center; gap: 9px; color: #718178; font-size: 11px; font-weight: 650; }
.inventory-live-badge { display: inline-flex; align-items: center; gap: 5px; border: 1px solid #bfe3d0; border-radius: 999px; padding: 3px 8px; color: #18744c; background: #effaf4; font-size: 10px; font-weight: 600; }
.inventory-live-badge.is-pending { border-color: #e7d4aa; color: #956a1d; background: #fff9e9; }
.inventory-live-badge i, .inventory-state-heading i { display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: #2e9b69; box-shadow: 0 0 0 3px rgba(46, 155, 105, .12); }
.inventory-live-badge.is-pending i { background: #c08a29; box-shadow: 0 0 0 3px rgba(192, 138, 41, .12); }
.inventory-hero h2 { margin: 0; color: #18382a; font-size: 27px; letter-spacing: 0; }
.inventory-hero-copy > span { max-width: 700px; color: #61736a; font-size: 12px; line-height: 1.55; }
.inventory-hero-meta { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 3px; }
.inventory-hero-meta span { display: inline-flex; align-items: center; gap: 5px; border: 1px solid #e1ebe5; border-radius: 4px; padding: 5px 8px; color: #597267; background: #f7fbf8; font-size: 10px; }
.inventory-hero-meta svg { color: #23825a; }
.inventory-hero .hero-actions { padding-top: 4px; }
.inventory-hero .capture-refresh { min-height: 38px; padding-inline: 13px; }
.inventory-hero .capture-refresh:not(.secondary-action) { box-shadow: 0 4px 12px rgba(38, 132, 91, .14); }
.inventory-metrics { gap: 10px; margin-top: 10px; }
.inventory-stat-card { min-height: 112px; border-color: #dfe9e3; border-top: 3px solid #73b998; background: #ffffff; }
.inventory-stat-card:nth-child(2) { border-top-color: #4c91d0; }
.inventory-stat-card:nth-child(3) { border-top-color: #d9a645; }
.inventory-stat-card:nth-child(4) { border-top-color: #a8b8b0; }
.inventory-stat-card > span { color: #718178; font-size: 11px; font-weight: 600; }
.inventory-stat-card > strong { margin-top: 5px; color: #193b2c; font-size: 29px; letter-spacing: 0; }
.inventory-stat-card > small { color: #7b8c83; font-size: 10px; }
.inventory-status-bar {
  display: grid;
  grid-template-columns: minmax(245px, 1.05fr) minmax(230px, .95fr) minmax(300px, 1.35fr);
  align-items: stretch;
  gap: 0;
  min-height: 108px;
  padding: 0;
  border-color: #d9e5df;
  background: #ffffff;
}
.inventory-snapshot-card, .inventory-collection-state, .inventory-refresh-plan { min-width: 0; padding: 17px 19px; }
.inventory-snapshot-card { display: flex !important; align-items: center; gap: 11px !important; }
.inventory-status-icon { display: grid; width: 36px; height: 36px; flex: 0 0 auto; place-items: center; border: 1px solid #cde7d8; border-radius: 7px; color: #23825a; background: #effaf4; }
.inventory-snapshot-card p { margin: 0 0 4px; color: #718178; font-size: 10px; }
.inventory-snapshot-card strong { color: #203b2c; font-size: 14px; line-height: 1.35; }
.inventory-snapshot-card span:not(.inventory-status-icon) { margin-top: 4px; color: #687d71; font-size: 10px; }
.inventory-collection-state { display: grid !important; align-content: center; gap: 4px !important; border-top: 0; border-right: 1px solid #e5eee8; border-left: 1px solid #e5eee8; padding-left: 19px; }
.inventory-state-heading { display: flex; align-items: center; gap: 7px; }
.inventory-state-heading strong { font-size: 13px; }
.inventory-collection-state span { margin-top: 0; color: #5f7468; font-size: 10px; line-height: 1.45; }
.inventory-collection-state small { display: inline-flex; align-items: center; gap: 4px; margin-top: 2px; color: #72857b; font-size: 10px; }
.inventory-collection-state small svg { color: #23825a; }
.inventory-collection-state.state-failed .inventory-state-heading i, .inventory-collection-state.state-credential_invalid .inventory-state-heading i { background: #c9534e; box-shadow: 0 0 0 3px rgba(201, 83, 78, .12); }
.inventory-collection-state.state-no_data .inventory-state-heading i, .inventory-collection-state.state-not_configured .inventory-state-heading i { background: #c08a29; box-shadow: 0 0 0 3px rgba(192, 138, 41, .12); }
.inventory-status-bar > .inventory-refresh-plan { display: grid; align-content: center; gap: 4px; }
.inventory-plan-heading { display: inline-flex; align-items: center; gap: 6px; color: #23825a; font-size: 10px; font-weight: 650; }
.inventory-refresh-plan > strong { color: #294a3a; font-size: 12px; }
.inventory-refresh-plan > span { color: #5f7468; font-size: 10px; }
.inventory-refresh-plan > small { margin-top: 3px; color: #82928a; font-size: 10px; line-height: 1.4; }

@media (max-width: 900px) {
  .inventory-status-bar { grid-template-columns: 1fr 1fr; }
  .inventory-refresh-plan { grid-column: 1 / -1; border-top: 1px solid #e5eee8; }
  .inventory-collection-state { border-right: 0; }
}

@media (max-width: 760px) {
  .inventory-hero { min-height: 0; padding: 19px; }
  .inventory-hero h2 { font-size: 23px; }
  .inventory-hero .hero-actions { width: 100%; padding-top: 6px; }
  .inventory-hero .hero-actions .capture-refresh { flex: 1; }
  .inventory-status-bar { display: block; min-height: 0; }
  .inventory-snapshot-card, .inventory-collection-state, .inventory-refresh-plan { min-height: 86px; border-right: 0; border-bottom: 1px solid #e5eee8; }
  .inventory-refresh-plan { border-bottom: 0; }
  .inventory-stat-card { min-height: 104px; }
}
</style>
