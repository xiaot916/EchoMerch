<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { FileSearch, LoaderCircle, RefreshCw, Route, ShieldCheck } from "lucide-vue-next"

import { fetchContractSummary, fetchDailyContracts } from "@/api"
import type { ContractCatalog, ContractSummary, EndpointContract } from "@/types"
import { number } from "@/lib/format"

const summary = ref<ContractSummary | null>(null)
const catalog = ref<ContractCatalog | null>(null)
const loading = ref(false)
const error = ref("")

const priorityPaths = computed(() => summary.value?.priority_paths ?? [])
const dailyContracts = computed(() => catalog.value?.contracts ?? [])
const dailyCoverage = computed(() => summary.value?.endpoint_contracts ? Math.min(100, (dailyContracts.value.length / summary.value.endpoint_contracts) * 100) : 0)

function datesLabel(contract: EndpointContract): string {
  const entries = Object.entries(contract.business_dates)
  if (!entries.length) return "-"
  return entries.map(([day, count]) => `${day} (${count})`).join(", ")
}

function paramsPreview(contract: EndpointContract): string {
  const keys = ["dateType", "dateRange", "date", "domainCode", "showType", "indexCode", "indexCodes", "page", "pageSize"]
  const values = keys.filter((key) => contract.sample_params[key]).map((key) => `${key}=${contract.sample_params[key]}`)
  return values.slice(0, 4).join(" | ") || "-"
}

async function loadContracts(): Promise<void> {
  loading.value = true
  error.value = ""
  try {
    const [summaryPayload, catalogPayload] = await Promise.all([
      fetchContractSummary(),
      fetchDailyContracts(36),
    ])
    summary.value = summaryPayload
    catalog.value = catalogPayload
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : "接口契约中心暂不可用"
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void loadContracts()
})
</script>

<template>
  <section class="module-hero contract-hero">
    <div>
      <p>接口契约中心</p>
      <h2>把抓包样本沉淀成可演进的 API Catalog</h2>
      <span>这里展示的是 Reqable 本地分析产物：请求契约、按日参数、响应候选和字段形状。Worker 以后从这里读取计划，不直接读散落脚本。</span>
    </div>
    <button class="capture-refresh" :disabled="loading" @click="loadContracts">
      <RefreshCw :size="16" :class="{ spinning: loading }" />
      刷新
    </button>
  </section>

  <section v-if="loading && !summary" class="loading-panel">
    <LoaderCircle :size="28" class="spinning" />
    <span>正在读取接口契约</span>
  </section>

  <section v-else-if="error" class="error-panel">
    <FileSearch :size="24" />
    <div><strong>接口契约不可用</strong><p>{{ error }}</p></div>
    <button @click="loadContracts">重试</button>
  </section>

  <template v-else-if="summary">
    <section class="architecture-metrics">
      <article class="panel capture-stat">
        <span>请求观察</span>
        <strong>{{ number(summary.api_observations) }}</strong>
        <small>Reqable telemetry contracts</small>
      </article>
      <article class="panel capture-stat">
        <span>端点契约</span>
        <strong>{{ number(summary.endpoint_contracts) }}</strong>
        <small>按 host/path/method 聚合</small>
      </article>
      <article class="panel capture-stat">
        <span>按日观察</span>
        <strong>{{ number(summary.daily_observations) }}</strong>
        <small>dateRange/date/startDate</small>
      </article>
      <article class="panel capture-stat">
        <span>重点路径</span>
        <strong>{{ number(priorityPaths.length) }}</strong>
        <small>采集优先候选</small>
      </article>
      <article class="panel capture-stat capture-stat-progress">
        <span>按日契约覆盖</span>
        <strong>{{ dailyCoverage.toFixed(0) }}%</strong>
        <i><em :style="{ width: `${dailyCoverage}%` }"></em></i>
        <small>{{ dailyContracts.length }} / {{ summary.endpoint_contracts }} 个端点</small>
      </article>
    </section>

    <section class="panel architecture-panel">
      <div class="panel-heading">
        <div><p>优先契约</p><h2>第一批按日采集候选</h2></div>
        <ShieldCheck :size="18" />
      </div>
      <div class="contract-table">
        <div class="contract-row contract-head">
          <span>路径</span><span>方法</span><span>调用次数</span><span>业务日期</span><span>响应样本</span>
        </div>
        <div v-for="item in priorityPaths" :key="`${item.path}-${item.method}`" class="contract-row">
          <span class="mono-path">{{ item.path }}</span>
          <strong>{{ item.method || "-" }}</strong>
          <span>{{ item.calls }} / daily {{ item.daily_calls }}</span>
          <span>{{ datesLabel(item) }}</span>
          <span>{{ item.response.files }} files · {{ item.response.json_like_files }} json</span>
        </div>
      </div>
    </section>

    <section class="panel architecture-panel">
      <div class="panel-heading">
          <div><p>按日契约</p><h2>抓包中已经出现过按日参数的接口</h2></div>
        <Route :size="18" />
      </div>
      <div class="daily-contract-list">
        <article v-for="item in dailyContracts" :key="`${item.host}-${item.path}-${item.method}`">
          <div>
            <strong>{{ item.path }}</strong>
            <span>{{ item.host }} · {{ item.method }} · {{ datesLabel(item) }}</span>
          </div>
          <small>{{ paramsPreview(item) }}</small>
        </article>
      </div>
    </section>
  </template>
</template>
