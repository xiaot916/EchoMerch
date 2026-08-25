<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { Bot, CheckCircle2, ChevronRight, Clock3, LoaderCircle, Send, TriangleAlert, X } from "lucide-vue-next"
import { streamAnalyzeWithAI } from "@/api"
import type { AIStreamEvent } from "@/api"
import type { AIAnalysisResponse } from "@/types"
import { renderMarkdown } from "@/utils/markdown"

const props = withDefaults(defineProps<{
  open: boolean
  domain?: "auto" | "overview" | "traffic" | "promotion" | "market" | "product" | "customer" | "customer-service" | "content" | "live" | "campaign" | "reviews"
  title?: string
  storeId?: number | null
  startDate?: string | null
  endDate?: string | null
  pageContext?: Record<string, unknown>
}>(), { domain: "auto", title: "AI 经营助手", storeId: null, startDate: null, endDate: null })
const emit = defineEmits<{ close: [] }>()
const question = ref("")
const loading = ref(false)
const error = ref("")
const result = ref<AIAnalysisResponse | null>(null)
const streamText = ref("")
const streamSteps = ref<Array<{ kind: string; name: string; status: string; detail: string }>>([])
const activeSkill = ref<AIAnalysisResponse["skill"] | null>(null)
const supportingSkills = ref<AIAnalysisResponse["supporting_skills"]>([])
const conversationId = ref<string | null>(null)
const conversationStorageKey = computed(() => `echomerch.ai.drawer.conversation.v1:${props.storeId || "global"}`)
const quickQuestions = computed(() => {
  const pageQuestions = props.pageContext?.recommended_questions
  if (Array.isArray(pageQuestions) && pageQuestions.length) return pageQuestions.slice(0, 3).map((item) => String(item))
  if (props.domain === "traffic") return ["哪些流量来源值得加预算？", "有没有高流量低转化的来源？", "流量数据缺什么？"]
  if (props.domain === "promotion") return ["哪些推广场景应该降预算？", "当前推广 ROI 是否健康？", "帮我找高花费低产出的计划"]
  if (props.domain === "market") return ["当前市场有哪些竞品机会？", "哪些搜索词值得小预算验证？", "市场数据缺哪些日期？"]
  return ["为什么昨天成交下降？", "今天最应该先做什么？", "这段经营数据缺什么？"]
})
function artifacts() { return result.value?.diagnosis.artifacts || [] }
function inventoryData() { return result.value?.mcp_results?.find((item) => item.tool === "inventory.query")?.data || null }
function inventoryItems(): Array<Record<string, any>> { return (inventoryData()?.items || []) as Array<Record<string, any>> }
function inventorySnapshotTime() {
  const value = inventoryData()?.snapshot_collected_at || inventoryData()?.latest_snapshot_at
  return value ? String(value).replace("T", " ").replace(/\.\d+(?=[+-]\d{2}:?\d{2}$)/, "").replace(/[+-]\d{2}:?\d{2}$/, "") : "--"
}
function inventoryStatus() {
  const data = inventoryData()
  if (!data) return "--"
  if (data.ambiguous) return `编码候选 ${data.candidate_count || inventoryItems().length} 个`
  if (data.match_type === "exact_code") return `编码精确命中 · ${(data.matched_by || []).join("、") || "标识字段"}`
  const labels: Record<string, string> = { product_not_matched: "商品未匹配", sku_not_matched: "尺码/SKU 未匹配", code_known_no_snapshot: "编码已识别但快照未命中", zero_stock: "库存为 0", matched: "已匹配" }
  return labels[String(data.reason)] || "未知"
}
function memoryValue() { return result.value?.conversation_memory || {} }
function memoryText(key: string) {
  const value = memoryValue()[key]
  if (value == null || value === "") return "--"
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value)
  if (Array.isArray(value)) return value.map((item) => String(item)).filter(Boolean).join("、") || "--"
  return "--"
}
function memoryFocus(): string[] {
  const value = memoryValue().focus
  if (!Array.isArray(value)) return []
  return value.map((item) => {
    if (item == null) return ""
    if (typeof item === "string" || typeof item === "number" || typeof item === "boolean") return String(item)
    const record = item as Record<string, any>
    return String(record.title || record.name || record.label || record.goods_name || record.product_name || record.detail || "")
  }).filter(Boolean)
}
function memoryTimeline(): Array<{ question: string; headline: string }> {
  const value = memoryValue().timeline
  if (!Array.isArray(value)) return []
  return value.map((item) => {
    if (!item || typeof item !== "object") return null
    const record = item as Record<string, any>
    return { question: String(record.question || ""), headline: String(record.headline || "") }
  }).filter((item): item is { question: string; headline: string } => Boolean(item))
}
function memoryEvidenceRefs() {
  const value = memoryValue().evidence_refs
  return Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : []
}
function nextQuestions() {
  return result.value?.diagnosis.next_questions || []
}
function artifactColumns(artifact: { rows?: Array<Record<string, unknown>> }) { return artifact.rows?.length ? Object.keys(artifact.rows[0]) : [] }
function cell(value: unknown) { return value == null || value === "" ? "--" : typeof value === "number" ? Number(value).toLocaleString("zh-CN", { maximumFractionDigits: 2 }) : String(value) }
function streamStepLabel(step: { kind: string; name: string }) {
  if (step.kind === "planner") return "经营问题路由"
  if (step.kind === "skill") return "Agent 能力编排"
  if (step.kind === "mcp") return `数据工具 · ${step.name}`
  if (step.kind === "model") return `分析模型 · ${step.name}`
  return step.name
}
function cleanAnswer(value: unknown): string { return renderMarkdown(value) }

async function ask(value = question.value): Promise<void> {
  const text = value.trim()
  if (!text || loading.value) return
  question.value = text
  loading.value = true
  error.value = ""
  result.value = null
  streamText.value = ""
  streamSteps.value = []
  activeSkill.value = null
  supportingSkills.value = []
  try {
    result.value = await streamAnalyzeWithAI(
      { question: text, conversation_id: conversationId.value, store_id: props.storeId, start_date: props.startDate, end_date: props.endDate, domain: props.domain, page_context: { ...props.pageContext, page: props.title, route: window.location.pathname }, use_model: true },
      (event: AIStreamEvent) => {
        if (event.event === "token" && event.text) streamText.value += event.text
        if (event.event === "skill") {
          activeSkill.value = event.skill || null
          supportingSkills.value = event.supporting_skills || []
        }
        if (["planner", "skill", "mcp", "model"].includes(event.event)) {
          const existing = [...streamSteps.value].reverse().find((item) => item.kind === event.event && item.name === (event.name || event.event))
          if (existing && existing.status === "running") Object.assign(existing, { status: event.status || "completed", detail: event.detail || existing.detail })
          else streamSteps.value.push({ kind: event.event, name: event.name || event.event, status: event.status || "running", detail: event.detail || "" })
        }
      },
    )
    conversationId.value = result.value.conversation_id || conversationId.value
    if (conversationId.value) localStorage.setItem(conversationStorageKey.value, conversationId.value)
  } catch (err) {
    const message = err instanceof Error ? err.message : "分析失败"
    if (conversationId.value && /(?:会话不存在|不属于当前账号|请求失败：400|请求失败：404)/.test(message)) {
      // A stale ID can happen after account or local database changes.
      conversationId.value = null
      localStorage.removeItem(conversationStorageKey.value)
    }
    error.value = message
  } finally {
    loading.value = false
  }
}

watch(conversationStorageKey, (key) => {
  conversationId.value = localStorage.getItem(key)
}, { immediate: true })
</script>

<template>
  <aside v-if="open" class="ai-assistant-drawer" aria-label="AI 经营助手">
    <header class="ai-assistant-header"><div><span><Bot :size="15" />AI 赋能</span><strong>{{ title }}</strong></div><button class="icon-button" title="关闭 AI 助手" @click="emit('close')"><X :size="17" /></button></header>
    <div class="ai-assistant-body">
      <div v-if="!result && !loading" class="ai-assistant-welcome"><Bot :size="28" /><strong>把当前页面的数据变成行动</strong><p>问题会自动带上当前店铺、日期和业务上下文。</p></div>
      <div v-if="!result && !loading" class="ai-quick-list"><button v-for="item in quickQuestions" :key="item" @click="ask(item)">{{ item }}<ChevronRight :size="14" /></button></div>
        <section v-if="loading" class="ai-loading ai-drawer-agent-loading"><div class="ai-thinking-head"><LoaderCircle :size="22" class="spinning" /><div><strong>{{ streamText ? "正在流式生成回答" : "正在执行分析能力" }}</strong><small>实时展示可审计的能力与数据调用</small></div></div><div v-if="activeSkill" class="ai-agent-capabilities"><span>主 Agent</span><b>{{ activeSkill.display_name }}</b><em v-for="skill in supportingSkills" :key="skill.name">{{ skill.display_name }}</em></div><div v-if="streamSteps.length" class="ai-live-step-list"><div v-for="(step, index) in streamSteps" :key="`${step.kind}-${step.name}-${index}`" :class="`is-${step.status}`"><LoaderCircle v-if="step.status === 'running'" :size="13" class="spinning" /><CheckCircle2 v-else-if="step.status === 'completed'" :size="13" /><TriangleAlert v-else-if="step.status === 'failed'" :size="13" /><Clock3 v-else :size="13" /><span><b>{{ streamStepLabel(step) }}</b><small>{{ step.detail }}</small></span></div></div><div v-if="streamText" class="ai-stream-answer ai-markdown-content" v-html="cleanAnswer(streamText)"></div></section>
      <section v-if="error" class="ai-error">{{ error }}</section>
      <section v-if="result" class="ai-result">
        <div class="ai-status-line"><span :class="`ai-status-${result.status}`">{{ result.status === "partial" ? "部分数据" : result.status === "no_data" ? "暂无数据" : "已完成" }}</span><small>{{ result.skill.display_name }} · 置信度 {{ result.diagnosis.confidence === "high" ? "高" : result.diagnosis.confidence === "low" ? "低" : "中" }}</small></div>
        <h3>{{ result.diagnosis.headline }}</h3><div class="ai-answer ai-markdown-content" v-html="cleanAnswer(result.answer)"></div>
        <div class="ai-drawer-coverage"><span>{{ inventoryData() ? "库存快照覆盖" : "覆盖" }} {{ result.diagnosis.coverage.covered_days || 0 }}/{{ result.diagnosis.coverage.expected_days || 0 }} 天</span><span v-if="!inventoryData()">最新业务日 {{ result.diagnosis.coverage.latest_data_date || "--" }}</span><span v-if="result.diagnosis.coverage.missing_dates.length">缺失 {{ result.diagnosis.coverage.missing_dates.slice(0, 2).join("、") }}</span><span v-else-if="result.diagnosis.coverage.no_data_datasets.length">平台无数据</span></div>
        <div v-if="result.supporting_skills.length" class="ai-agent-capabilities ai-agent-capabilities-final"><span>Agent 能力</span><b>{{ result.skill.display_name }}</b><em v-for="skill in result.supporting_skills" :key="skill.name">{{ skill.display_name }}</em><small>{{ result.execution_steps.filter((step) => step.kind === 'mcp' && step.status === 'completed').length }} 个数据工具已完成</small></div>
        <div v-if="memoryText('last_question') !== '--' || memoryText('headline') !== '--'" class="ai-drawer-memory">
          <strong>本轮记忆</strong>
          <div class="ai-drawer-memory-grid">
            <div><small>上轮问题</small><b>{{ memoryText('last_question') }}</b></div>
            <div><small>本轮结论</small><b>{{ memoryText('headline') }}</b></div>
            <div><small>分析能力</small><b>{{ memoryText('skill') }}</b></div>
            <div><small>分析范围</small><b>{{ memoryText('range_start') }} 至 {{ memoryText('range_end') }}</b></div>
          </div>
          <div v-if="memoryFocus().length" class="ai-drawer-memory-tags"><span v-for="item in memoryFocus()" :key="item">{{ item }}</span></div>
          <div v-if="memoryTimeline().length" class="ai-drawer-memory-timeline"><article v-for="(item, index) in memoryTimeline().slice(-3)" :key="`${item.question}-${index}`"><b>{{ item.question || '--' }}</b><small>{{ item.headline || '--' }}</small></article></div>
        </div>
        <div v-if="memoryEvidenceRefs().length" class="ai-drawer-memory-evidence"><strong>证据引用</strong><span v-for="item in memoryEvidenceRefs().slice(0, 6)" :key="item">{{ item }}</span></div>
        <div v-if="nextQuestions().length" class="ai-drawer-next-questions"><strong>下一步追问</strong><div class="ai-question-chips"><button v-for="item in nextQuestions().slice(0, 4)" :key="item" type="button" @click="ask(item)">{{ item }}</button></div></div>
        <div v-if="inventoryData()" class="ai-drawer-inventory-meta"><div><small>库存业务日</small><strong>{{ inventoryData()?.inventory_business_day || inventoryData()?.business_day || "--" }}</strong></div><div><small>快照采集时间</small><strong>{{ inventorySnapshotTime() }}</strong></div><div><small>匹配状态</small><strong>{{ inventoryStatus() }}</strong></div><div><small>快照时效</small><strong>{{ inventoryData()?.snapshot_age_minutes == null ? "--" : `${inventoryData()?.snapshot_age_minutes} 分钟` }}</strong></div></div>
        <div v-if="inventoryItems().length" class="ai-drawer-inventory-table"><strong>库存候选</strong><div class="ai-drawer-table"><table><thead><tr><th>商品</th><th>货品编码</th><th>尺码</th><th>片数</th><th>库存 / 关系</th></tr></thead><tbody><tr v-for="(item, index) in inventoryItems().slice(0, 8)" :key="index"><td>{{ item.goods_name || item.sku_name || "--" }}</td><td>{{ item.goods_no || item.sku_no || "--" }}</td><td>{{ item.size || "--" }}</td><td>{{ item.pieces ?? "--" }}</td><td>{{ item.item_type === "package" ? `组合关系 ${item.components?.length || 0} 个 SKU` : item.available_quantity }}</td></tr></tbody></table></div></div>
        <div v-if="result.diagnosis.actions.length" class="ai-action-list"><strong>优先动作</strong><article v-for="action in result.diagnosis.actions" :key="`${action.priority}-${action.title}`"><span>{{ action.priority }}</span><div><b>{{ action.title }}</b><small>{{ action.detail }}</small><small>负责人：{{ action.owner }} · 验证：{{ action.validation || "--" }}</small><small>观察：{{ action.observation_window || "--" }} · 预期：{{ action.expected_impact || "--" }}</small></div></article></div>
        <div v-for="artifact in artifacts()" :key="artifact.title" class="ai-drawer-artifact"><strong>{{ artifact.title }}</strong><div v-if="artifact.rows?.length" class="ai-drawer-table"><table><thead><tr><th v-for="column in artifactColumns(artifact)" :key="column">{{ column }}</th></tr></thead><tbody><tr v-for="(row, index) in artifact.rows.slice(0, 6)" :key="index"><td v-for="column in artifactColumns(artifact)" :key="column">{{ cell(row[column]) }}</td></tr></tbody></table></div></div>
        <div v-if="result.diagnosis.missing_inputs.length" class="ai-drawer-boundary">待补输入：{{ result.diagnosis.missing_inputs.join("、") }}</div>
        <div v-if="result.warnings.length" class="ai-warning-list"><strong>数据提示</strong><p v-for="warning in result.warnings" :key="warning">{{ warning }}</p></div>
        <button class="ai-follow-up" @click="result = null">继续追问</button>
      </section>
    </div>
    <form class="ai-composer" @submit.prevent="ask()"><input v-model="question" placeholder="问一个经营问题…" /><button type="submit" title="发送问题" :disabled="loading"><Send :size="16" /></button></form>
  </aside>
</template>
