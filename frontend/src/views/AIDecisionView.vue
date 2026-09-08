<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import {
  Archive,
  BarChart3,
  Bot,
  CalendarDays,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleHelp,
  Clock3,
  FileCheck2,
  FileSearch,
  LoaderCircle,
  MessageSquare,
  PackageCheck,
  PackageSearch,
  Plus,
  Send,
  Sparkles,
  Square,
  Target,
  Trash2,
  TriangleAlert,
  X,
} from "lucide-vue-next"
import { analyzeWithAI, cancelAIStream, deleteAIConversation, fetchAIConversation, fetchAIConversations, streamAnalyzeWithAI, streamPeriodReport } from "@/api"
import type { AIStreamEvent } from "@/api"
import type { AIAnalysisResponse, PeriodReportResponse } from "@/types"
import { useDashboard } from "@/composables/useDashboard"
import BusinessChart from "@/components/BusinessChart.vue"
import { renderMarkdown } from "@/utils/markdown"
import { useAIStreamStatus } from "@/composables/useAIStreamStatus"

type ReportType = "daily" | "weekly" | "monthly" | "mtd" | "daily_series"
type ReportIntent = { report_type: ReportType; anchor_date?: string }
type StreamStep = { kind: string; name: string; status: string; detail: string; startedAt?: number; elapsedMs?: number }
type ChatMessage = {
  id: string
  role: "user" | "assistant"
  text?: string
  analysis?: AIAnalysisResponse
  report?: PeriodReportResponse
  loading?: boolean
  error?: boolean
  streamText?: string
  streamSteps?: StreamStep[]
  thinkingStartedAt?: number
  elapsedMs?: number
  activeSkill?: AIAnalysisResponse["skill"]
  supportingSkills?: AIAnalysisResponse["supporting_skills"]
  createdAt: number
}
type ChatSession = { id: string; title: string; updatedAt: number; messages: ChatMessage[] }
type AIArtifact = { type: string; title: string; columns?: Array<Record<string, string>>; rows?: Array<Record<string, any>>; option?: Record<string, any> }
type ReportCoverage = { missing_dates: string[]; missing_datasets: string[]; partial_datasets: string[]; failed_datasets: string[]; no_data_datasets: string[] }
type ReportQuality = { missing_sections?: string[]; no_data_sections?: string[]; missing_dates?: string[]; missing_datasets?: string[]; partial_datasets?: string[]; failed_datasets?: string[]; no_data_datasets?: string[] }

const STORAGE_KEY = "echomerch.ai.workbench.sessions.v2"
const { startDate, endDate, currentStoreId } = useDashboard()
const sessions = ref<ChatSession[]>([])
const activeSessionId = ref("")
const question = ref("")
const loading = ref(false)
const error = ref("")
const composer = ref<HTMLTextAreaElement | null>(null)
const conversation = ref<HTMLElement | null>(null)
const showHistory = ref(false)
const showInspector = ref(false)
const thinkingClock = ref(0)
let thinkingTimer: ReturnType<typeof setInterval> | undefined
const abortController = ref<AbortController | null>(null)
const streamStatus = useAIStreamStatus()
const streamStatusTitle = streamStatus.title
const streamStatusDetail = streamStatus.detail
const streamElapsedMs = streamStatus.elapsedMs

const quickActions = [
  { label: "查库存", prompt: "查一下大鱼 M 码库存", icon: PackageSearch, tone: "green" },
  { label: "经营诊断", prompt: "为什么最近成交下降？给我最重要的三个原因和动作", icon: Target, tone: "blue" },
  { label: "生成日报", prompt: "生成今天的经营日报", icon: FileCheck2, tone: "purple", report: "daily" as ReportType },
  { label: "渠道分析", prompt: "哪些渠道值得加预算？请结合投入产出分析", icon: BarChart3, tone: "amber" },
]
const suggestedQuestions = ["今天最应该先做什么？", "哪些商品库存低于安全线？", "当前还有哪些数据缺失？"]

const workbenchPageContext = computed(() => ({
  page_key: "ai",
  page: "AI 决策中心",
  section: "全域经营分析",
  data_domains: ["overview", "traffic", "product", "promotion", "customer", "customer-service", "reviews", "campaign", "live", "inventory"],
  datasets: ["store_overview", "traffic_sources", "products", "product_catalog", "promotion_campaigns", "customers", "members", "customer_service", "review_records", "inventory_snapshots"],
  page_goal: "根据用户问题自动编排相关店铺数据，输出证据、原因、风险和可验证动作",
}))

function businessDate(value: unknown): string | undefined {
  const match = String(value || "").match(/\b\d{4}-\d{2}-\d{2}\b/)
  return match?.[0]
}
const analysisStartDate = computed(() => businessDate(startDate.value))
const analysisEndDate = computed(() => businessDate(endDate.value))
const currentRange = computed(() => analysisEndDate.value || analysisStartDate.value || new Date().toISOString().slice(0, 10))
const currentRangeLabel = computed(() => {
  if (!analysisStartDate.value && !analysisEndDate.value) return "最新可用数据"
  if (analysisStartDate.value === analysisEndDate.value || !analysisStartDate.value) return analysisEndDate.value || analysisStartDate.value
  return `${analysisStartDate.value} 至 ${analysisEndDate.value}`
})
const activeSession = computed(() => sessions.value.find((item) => item.id === activeSessionId.value) || null)
const messages = computed(() => activeSession.value?.messages || [])
const lastAssistantMessage = computed(() => [...messages.value].reverse().find((item) => item.role === "assistant" && !item.loading) || null)
const inspectorQuestions = computed(() => {
  const dynamic = lastAssistantMessage.value?.analysis?.diagnosis?.next_questions || lastAssistantMessage.value?.report?.diagnosis?.next_questions || []
  return [...new Set([...dynamic, ...suggestedQuestions])]
})

function uid(prefix = "msg") { return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}` }

function loadSessions() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    if (Array.isArray(parsed)) sessions.value = parsed
  } catch {
    sessions.value = []
  }
  if (!sessions.value.length) createSession(false)
  else activeSessionId.value = sessions.value[0].id
}

function persistSessions() {
  const compact = sessions.value.slice(0, 30).map((session) => ({
    ...session,
    messages: session.messages
      .filter((message) => !message.loading)
      .slice(-20)
      .map((message) => ({
        id: message.id,
        role: message.role,
        text: message.text || message.analysis?.answer || message.report?.text,
        error: message.error,
        createdAt: message.createdAt,
      })),
  }))
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(compact)) } catch { /* Server history remains authoritative. */ }
}

async function syncServerSessions() {
  try {
    const remote = await fetchAIConversations(currentStoreId.value)
    const merged: ChatSession[] = remote.map((item) => ({
      id: item.conversation_id,
      title: item.title,
      updatedAt: new Date(item.updated_at).getTime() || Date.now(),
      // The authenticated server list is authoritative. Local-only IDs can
      // belong to a previous account/store and must not be opened remotely.
      messages: [],
    }))
    sessions.value = merged.slice(0, 30)
    if (!sessions.value.length) {
      createSession(false)
      return
    }
    if (!sessions.value.some((item) => item.id === activeSessionId.value)) activeSessionId.value = sessions.value[0].id
    persistSessions()
  } catch {
    // Local history remains usable when the API is temporarily unavailable.
  }
}

function createSession(focus = true) {
  stopCurrentRun()
  const session: ChatSession = { id: uid("session"), title: "新对话", updatedAt: Date.now(), messages: [] }
  sessions.value = [session, ...sessions.value]
  activeSessionId.value = session.id
  persistSessions()
  if (focus) nextTick(() => composer.value?.focus())
}

async function removeSession(id: string) {
  if (activeSessionId.value === id) stopCurrentRun()
  sessions.value = sessions.value.filter((item) => item.id !== id)
  if (!sessions.value.length) createSession(false)
  else if (activeSessionId.value === id) activeSessionId.value = sessions.value[0].id
  persistSessions()
  try { await deleteAIConversation(id) } catch { /* The local deletion still stands. */ }
}

async function selectSession(id: string) {
  if (activeSessionId.value && activeSessionId.value !== id) stopCurrentRun()
  activeSessionId.value = id
  showHistory.value = false
  const session = activeSession.value
  if (session && !session.messages.length) {
    try {
      const remote = await fetchAIConversation(id, currentStoreId.value)
      session.title = remote.title
      session.messages = remote.recent_messages.map((item, index) => ({
        id: `${id}-remote-${index}`,
        role: item.role,
        text: item.role === "user" || !item.payload ? item.text : undefined,
        analysis: item.payload?.kind === "analysis" ? item.payload.data as AIAnalysisResponse : undefined,
        report: item.payload?.kind === "report" ? item.payload.data as PeriodReportResponse : undefined,
        elapsedMs: item.payload?.kind === "analysis" ? Number((item.payload.data as AIAnalysisResponse)?.elapsed_ms || 0) || undefined : item.payload?.kind === "report" ? Number((item.payload.data as PeriodReportResponse)?.elapsed_ms || 0) || undefined : undefined,
        streamSteps: item.payload?.kind === "analysis" ? ((item.payload.data as AIAnalysisResponse)?.execution_steps || []).map((step) => ({ ...step, elapsedMs: step.elapsed_ms ?? undefined })) : item.payload?.kind === "report" ? ((item.payload.data as PeriodReportResponse)?.execution_steps || []).map((step) => ({ ...step, elapsedMs: step.elapsed_ms ?? undefined })) : undefined,
        createdAt: new Date(item.created_at).getTime() || Date.now(),
      }))
      persistSessions()
    } catch { /* Keep the local shell when server history is unavailable. */ }
  }
  nextTick(scrollConversation)
}

function updateSessionMessages(session: ChatSession, nextMessages: ChatMessage[]) {
  session.messages = nextMessages
  session.updatedAt = Date.now()
  if (session.title === "新对话") {
    const firstUser = nextMessages.find((item) => item.role === "user" && item.text)
    if (firstUser?.text) session.title = firstUser.text.slice(0, 24)
  }
  persistSessions()
}

function updateActiveMessages(nextMessages: ChatMessage[]) {
  const session = activeSession.value
  if (session) updateSessionMessages(session, nextMessages)
}

function scrollConversation() {
  nextTick(() => { if (conversation.value) conversation.value.scrollTop = conversation.value.scrollHeight })
}

function useQuestion(value: string) {
  question.value = value
  showInspector.value = false
  nextTick(() => composer.value?.focus())
}

function formatNumber(value: unknown, digits = 0) {
  if (value == null || value === "") return "--"
  return Number(value).toLocaleString("zh-CN", { maximumFractionDigits: digits, minimumFractionDigits: digits })
}
function money(value: unknown) { return value == null ? "--" : `¥${formatNumber(Number(value) / 10000, 2)}万` }
function signedMoney(value: unknown) {
  if (value == null || value === "") return "--"
  const amount = Number(value)
  return `${amount >= 0 ? "+" : "-"}¥${formatNumber(Math.abs(amount) / 10000, 2)}万`
}
function percent(value: unknown) { return value == null ? "--" : `${formatNumber(value, 2)}%` }
function statusText(value: string) { return value === "partial" ? "部分数据" : value === "ok" ? "已完成" : value === "no_data" ? "暂无数据" : value }
function messageTime(value: number) { return new Date(value).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }) }
function elapsedText(value: unknown) {
  const milliseconds = Math.max(0, Number(value || 0))
  if (milliseconds < 1000) return `${Math.round(milliseconds)}ms`
  return `${(milliseconds / 1000).toFixed(1)}秒`
}
function startThinkingClock(message: ChatMessage) {
  const startedAt = performance.now()
  message.thinkingStartedAt = startedAt
  thinkingClock.value = 0
  if (thinkingTimer) clearInterval(thinkingTimer)
  thinkingTimer = setInterval(() => { thinkingClock.value = performance.now() - startedAt }, 100)
}
function stopThinkingClock(message: ChatMessage) {
  if (thinkingTimer) { clearInterval(thinkingTimer); thinkingTimer = undefined }
  const startedAt = message.thinkingStartedAt || performance.now()
  message.elapsedMs = Math.max(0, performance.now() - startedAt)
  thinkingClock.value = message.elapsedMs
}
function stepElapsedText(step: { elapsedMs?: number; elapsed_ms?: number | null } | Record<string, any>) {
  const value = step.elapsedMs ?? step.elapsed_ms
  return value == null ? "进行中" : elapsedText(value)
}
function streamStepLabel(step: { kind: string; name: string }) {
  if (step.kind === "planner") return "经营问题路由"
  if (step.kind === "skill") return "Agent 能力编排"
  if (step.kind === "mcp") return `数据工具 · ${step.name}`
  if (step.kind === "model") return `分析模型 · ${step.name}`
  return step.name
}

function stopCurrentRun() {
  const controller = abortController.value
  if (!controller) return
  streamStatus.cancel()
  const runId = streamStatus.runId.value
  if (runId) void cancelAIStream(runId, currentStoreId.value).catch(() => undefined)
  controller.abort()
}

function artifactsFor(message: ChatMessage): AIArtifact[] { return (message.analysis?.diagnosis.artifacts || []) as AIArtifact[] }
function isGeneralChatMessage(message: ChatMessage | null | undefined) {
  return message?.analysis?.skill.name === "general-chat"
}
function inventoryData(message: ChatMessage) {
  return message.analysis?.mcp_results?.find((result) => result.tool === "inventory.query")?.data || null
}
function utryData(message: ChatMessage) {
  return message.analysis?.mcp_results?.find((result) => result.tool === "utry.get_repurchase_diagnosis")?.data || null
}
function utryCurrent(message: ChatMessage) {
  return utryData(message)?.current || null
}
function inventoryDecisionSummary(message: ChatMessage) {
  return inventoryData(message)?.decision_summary || null
}
function inventoryGroups(message: ChatMessage): Array<Record<string, any>> {
  return inventoryDecisionSummary(message)?.groups || []
}
function inventoryGroup(message: ChatMessage, key: string) {
  return inventoryGroups(message).find((item) => item.key === key) || null
}
function inventoryItems(message: ChatMessage): Array<Record<string, any>> {
  return (inventoryData(message)?.items || []) as Array<Record<string, any>>
}
function inventorySnapshotTime(message: ChatMessage) {
  const value = inventoryData(message)?.snapshot_collected_at || inventoryData(message)?.latest_snapshot_at
  if (!value) return "--"
  return String(value).replace("T", " ").replace(/\.\d+(?=[+-]\d{2}:?\d{2}$)/, "").replace(/[+-]\d{2}:?\d{2}$/, "")
}
function inventoryMatchText(message: ChatMessage) {
  const data = inventoryData(message)
  if (data?.ambiguous) return `编码候选 ${data.candidate_count || inventoryItems(message).length} 个`
  if (data?.match_type === "exact_code") return `编码精确命中 · ${(data.matched_by || []).join("、") || "标识字段"}`
  return inventoryReasonText(data?.reason)
}
function inventoryReasonText(value: unknown) {
  const labels: Record<string, string> = {
    not_configured: "未配置",
    not_collected: "未采集",
    date_not_available: "指定日期无快照",
    product_not_matched: "商品未匹配",
    sku_not_matched: "尺码/SKU 未匹配",
    code_known_no_snapshot: "编码已识别但快照未命中",
    ambiguous_code: "编码对应多个候选",
    zero_stock: "库存为 0",
    stockouts_found: "发现缺货",
    no_stockouts: "范围内无缺货",
    stockout_scope_partial: "部分 SKU 未匹配",
    matched: "已匹配",
  }
  return labels[String(value)] || "未知"
}
function inventoryScopeSummary(message: ChatMessage) {
  const data = inventoryData(message)
  const scope = data?.scope || {}
  if (!scope.checked_sku_count) return ""
  const stockouts = Number(scope.stockout_sku_count || 0)
  const unmatched = Number(scope.unmatched_sku_count || 0)
  return `${scope.label || "所选范围"}：已核对 ${scope.checked_sku_count} 个 SKU，缺货 ${stockouts} 个${unmatched ? `，未匹配 ${unmatched} 个` : ""}`
}
function memoryValue(message: ChatMessage) {
  return message.analysis?.conversation_memory || {}
}
function memoryFocus(message: ChatMessage): string[] {
  const value = memoryValue(message).focus
  if (!Array.isArray(value)) return []
  return value.map((item) => {
    if (item == null) return ""
    if (typeof item === "string" || typeof item === "number" || typeof item === "boolean") return String(item)
    if (typeof item === "object") {
      const record = item as Record<string, any>
      return String(record.title || record.name || record.label || record.goods_name || record.product_name || record.detail || "")
    }
    return ""
  }).filter(Boolean)
}
function memoryTimeline(message: ChatMessage): Array<{ question: string; headline: string; skill: string }> {
  const value = memoryValue(message).timeline
  if (!Array.isArray(value)) return []
  return value.map((item) => {
    if (!item || typeof item !== "object") return null
    const record = item as Record<string, any>
    return {
      question: String(record.question || ""),
      headline: String(record.headline || ""),
      skill: String(record.skill || ""),
    }
  }).filter((item): item is { question: string; headline: string; skill: string } => Boolean(item))
}
function memoryList(message: ChatMessage, key: string): string[] {
  const value = memoryValue(message)[key]
  return Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : []
}
function memoryText(message: ChatMessage, key: string) {
  const value = memoryValue(message)[key]
  if (value == null || value === "") return "--"
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value)
  if (Array.isArray(value)) return value.map((item) => String(item)).filter(Boolean).join("、") || "--"
  return "--"
}
function memoryLastQuestion(message: ChatMessage) {
  return memoryText(message, "last_question")
}
function memoryHeadline(message: ChatMessage) {
  return memoryText(message, "headline")
}
function memorySkill(message: ChatMessage) {
  return memoryText(message, "skill")
}
function memoryRange(message: ChatMessage) {
  const start = memoryText(message, "range_start")
  const end = memoryText(message, "range_end")
  if (start === "--" && end === "--") return "--"
  return `${start || "--"} 至 ${end || "--"}`
}
function memoryEvidenceRefs(message: ChatMessage) {
  return memoryList(message, "evidence_refs")
}
function nextQuestions(message: ChatMessage) {
  return message.analysis?.diagnosis.next_questions || message.report?.diagnosis.next_questions || []
}
function evidenceRefs(message: ChatMessage) {
  return message.analysis?.diagnosis.evidence_refs || []
}
function freshnessText(value: unknown) { return value === "stale" ? "已过期" : value === "fresh" ? "最新" : "未知" }
function artifactColumns(artifact: AIArtifact) {
  return artifact?.rows?.length ? Object.keys(artifact.rows[0]) : []
}
function artifactRows(artifact: AIArtifact) {
  return artifact?.title === "库存风险清单" ? (artifact.rows || []).slice(0, 30) : artifact?.title === "全部匹配库存" ? (artifact.rows || []) : (artifact.rows || []).slice(0, 10)
}
function analysisArtifact(message: ChatMessage, title: string): AIArtifact | null {
  return (message.analysis?.diagnosis.artifacts || []).find((item) => item.title === title) as AIArtifact || null
}
function factStatusLabel(value: unknown) {
  return ({ ok: "可用", partial: "部分覆盖", no_data: "平台无数据", failed: "调用失败" } as Record<string, string>)[String(value)] || "未确认"
}
function factStatusClass(value: unknown) {
  const key = ({ "可用": "ok", "部分覆盖": "partial", "平台无数据": "no-data", "调用失败": "failed" } as Record<string, string>)[String(value)] || "unknown"
  return `fact-status-${key}`
}
function isFullInventoryArtifact(artifact: AIArtifact) { return artifact?.title === "全部匹配库存" }
function chartOption(artifact: AIArtifact) {
  if (!artifact || !["bar_chart", "line_chart"].includes(artifact.type) || !artifact.rows?.length) return null
  const rows = artifact.rows
  const first = rows[0]
  const labelKey = Object.keys(first).find((key) => typeof first[key] === "string") || Object.keys(first)[0]
  const valueKeys = Object.keys(first).filter((key) => key !== labelKey && typeof first[key] === "number").slice(0, 2)
  return {
    color: ["#1f9d70", "#7787f2"], tooltip: { trigger: "axis" }, grid: { left: 44, right: 18, top: 18, bottom: 30 },
    xAxis: { type: "category", data: rows.map((row) => String(row[labelKey] ?? "--")), axisLabel: { color: "#7a8c84", interval: 0 } },
    yAxis: { type: "value", splitLine: { lineStyle: { color: "#edf2ef" } } },
    series: valueKeys.map((key) => ({ name: key, type: artifact.type === "line_chart" ? "line" : "bar", smooth: artifact.type === "line_chart", data: rows.map((row) => Number(row[key] ?? 0)) })),
  }
}
function formatCell(value: unknown) { return value == null || value === "" ? "--" : typeof value === "number" ? formatNumber(value, 2) : decodeHtmlEntities(value) }

function reportData(message: ChatMessage) { return message.report?.report }
function reportDiagnosis(message: ChatMessage) { return message.report?.diagnosis || null }
function reportOps(message: ChatMessage) { return reportData(message)?.operations || {} }
function reportComparison(message: ChatMessage, key: string) { return reportData(message)?.comparison?.[key] || null }
function reportChange(message: ChatMessage, key: string) {
  const value = reportComparison(message, key)?.change_percent
  return value == null ? null : Number(value)
}
function reportChangeText(message: ChatMessage, key: string) {
  const value = reportChange(message, key)
  return value == null ? "--" : `${value >= 0 ? "+" : ""}${formatNumber(value, 1)}%`
}
function reportChangeClass(message: ChatMessage, key: string) {
  const value = reportChange(message, key)
  return value == null ? "neutral" : value > 0 ? "up" : value < 0 ? "down" : "neutral"
}
function channelLabel(key: string) {
  return ({ member: "会员", shop_live: "自播间", bybt: "百亿补贴", cps_payment: "CPS 支付", cps_settlement: "CPS 出库" } as Record<string, string>)[key] || key
}
function reportChannelRows(message: ChatMessage): Array<Record<string, any> & { key: string; label: string }> {
  const channels = reportData(message)?.channels || {}
  const rows: Array<Record<string, any> & { key: string; label: string }> = Object.entries(channels).map(([key, value]) => {
    const item = value as Record<string, any>
    return { key, label: channelLabel(key), ...item }
  })
  return rows.filter((item) => ["available", "complete"].includes(String(item.status)))
}
function reportPromotionRows(message: ChatMessage) {
  return (reportData(message)?.promotions?.scenes || []).map((item: Record<string, any>) => ({
    ...item,
    display_name: item.scene_name || item.dimension_name || "未分类",
    spend_value: Number(item.spend || 0),
    gmv_value: Number(item.paid_amount || 0),
    roi_value: Number(item.roi || 0),
  })).sort((left: Record<string, any>, right: Record<string, any>) => right.spend_value - left.spend_value)
}
function reportTalentRows(message: ChatMessage) { return reportData(message)?.top_talents || [] }
function reportDriverRows(message: ChatMessage) { return reportData(message)?.gmv_driver_bridge?.drivers || [] }
function reportDriverBridge(message: ChatMessage) { return reportData(message)?.gmv_driver_bridge || null }
function reportChannelScope(message: ChatMessage) { return reportData(message)?.channel_scope || null }
function reportDecisionQuality(message: ChatMessage) { return reportData(message)?.decision_quality || null }
function confidenceText(value: unknown) { return value === "high" ? "高" : value === "low" ? "低" : "中" }
function decodeHtmlEntities(value: unknown) {
  const textarea = document.createElement("textarea")
  textarea.innerHTML = String(value || "")
  return textarea.value
}
function errorText(value: unknown): string {
  if (value instanceof Error) return value.message
  if (typeof value === "string") return value
  if (Array.isArray(value)) return value.map((item) => errorText(item)).filter(Boolean).join("；") || "分析失败"
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>
    return errorText(record.detail || record.message || record.error) || "分析失败"
  }
  return "分析失败"
}
function cleanReportNarrative(value: unknown) {
  return decodeHtmlEntities(value)
    .split(/\r?\n/)
    .filter((line) => !/^\s*\|/.test(line) && !/^\s*```/.test(line) && !/^\s*---+\s*$/.test(line))
    .map((line) => line.replace(/^\s{0,3}#{1,6}\s*/, "").replace(/\*\*/g, "").replace(/^\s*[-*]\s+/, "• "))
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim()
}
function renderReportNarrative(value: unknown) { return renderMarkdown(decodeHtmlEntities(value)) }
function reportDailyRows(message: ChatMessage) { return message.report?.report?.daily_series || [] }
function reportArtifacts(message: ChatMessage): AIArtifact[] { return (message.report?.diagnosis?.artifacts || []) as AIArtifact[] }
function reportDisplayTitle(message: ChatMessage) {
  const report = message.report
  if (!report) return "经营报告"
  const start = new Date(`${report.range_start}T00:00:00`)
  if (Number.isNaN(start.getTime())) return report.title
  const year = String(start.getFullYear()).slice(-2)
  const month = start.getMonth() + 1
  if (report.report_type === "daily_series") return `${year}年-${month}月逐日经营日报`
  if (report.report_type === "mtd") return `${year}年-${month}月MTD`
  if (report.report_type === "monthly") return `${year}年-${month}月月报`
  if (report.report_type === "daily") return `${year}年-${month}月${start.getDate()}日日报`
  return `${report.range_start} 至 ${report.range_end} 周报`
}
function reportCoverage(message: ChatMessage): ReportCoverage {
  const coverage = message.report?.diagnosis?.coverage
  return {
    missing_dates: coverage?.missing_dates || [],
    missing_datasets: coverage?.missing_datasets || [],
    partial_datasets: coverage?.partial_datasets || [],
    failed_datasets: (coverage as { failed_datasets?: string[] } | undefined)?.failed_datasets || [],
    no_data_datasets: coverage?.no_data_datasets || [],
  }
}
function reportQuality(message: ChatMessage) {
  const quality = (reportData(message)?.data_quality || {}) as ReportQuality
  const coverage = reportCoverage(message)
  return {
    missingSections: quality.missing_sections || [],
    noDataSections: quality.no_data_sections || [],
    missingDates: quality.missing_dates?.length ? quality.missing_dates : coverage.missing_dates || [],
    missingDatasets: quality.missing_datasets?.length ? quality.missing_datasets : coverage.missing_datasets || [],
    partialDatasets: quality.partial_datasets?.length ? quality.partial_datasets : coverage.partial_datasets || [],
    failedDatasets: quality.failed_datasets?.length ? quality.failed_datasets : coverage.failed_datasets || [],
    noDataDatasets: quality.no_data_datasets?.length ? quality.no_data_datasets : coverage.no_data_datasets || [],
  }
}

function lastDayOfMonth(year: number, month: number) {
  return new Date(year, month, 0).getDate()
}

function reportAnchorBaseDate() {
  const raw = currentRange.value || new Date().toISOString().slice(0, 10)
  const parsed = new Date(`${raw}T00:00:00`)
  return Number.isNaN(parsed.getTime()) ? new Date() : parsed
}

/**
 * Resolve report intent before dispatching to the period-report API.
 * An explicit natural month wins over the word “日报”: the API currently
 * returns one aggregate period, so “7月的经营日报” is treated as July's
 * monthly operating report instead of silently falling back to today's daily report.
 */
function inferReportIntent(text: string): ReportIntent | undefined {
  const hasReportRequest = /(日报|周报|月报|MTD|经营报告|经营复盘|销售目标|经营数据|经营情况)/i.test(text)
  const monthMatch = text.match(/(?:(20\d{2}|\d{2})\s*年\s*)?(1[0-2]|0?[1-9])\s*月/)
  const base = reportAnchorBaseDate()

  if (monthMatch) {
    let year = base.getFullYear()
    if (monthMatch[1]) {
      const rawYear = Number(monthMatch[1])
      year = rawYear < 100 ? 2000 + rawYear : rawYear
    } else if (Number(monthMatch[2]) > base.getMonth() + 1) {
      // “12月” asked near the start of a year normally refers to the latest
      // completed December, not a future period with no data yet.
      year -= 1
    }
    const month = Number(monthMatch[2])
    return {
      report_type: /(日报|逐日|每天|每日)/.test(text) && !/(月报|月度)/.test(text) ? "daily_series" : "monthly",
      anchor_date: `${year}-${String(month).padStart(2, "0")}-${String(lastDayOfMonth(year, month)).padStart(2, "0")}`,
    }
  }

  if (!hasReportRequest) return undefined
  if (/(MTD|本月至今|月初至今)/i.test(text)) return { report_type: "mtd", anchor_date: currentRange.value }
  if (/(日报|逐日|每天|每日)/.test(text) && /(本月|当月)/.test(text)) return { report_type: "daily_series", anchor_date: currentRange.value }
  if (/(月报|月度|本月|当月)/.test(text)) return { report_type: "monthly", anchor_date: currentRange.value }
  if (/(周报|周度|本周)/.test(text)) return { report_type: "weekly", anchor_date: currentRange.value }
  return { report_type: "daily", anchor_date: currentRange.value }
}
function isLightChatQuestion(text: string) {
  return /^(你好|您好|嗨|哈喽|hello|hi|在吗|在不在)[!！。,.，?？\s]*$/i.test(text.trim())
}
function extractTargetGmv(text: string): number | undefined {
  const match = text.match(/(?:销售目标|GMV目标|目标GMV|目标销售额)\s*(?:为|是|[:：=])?\s*([\d,.]+)\s*(亿|万|w|k|元)?/i)
  if (!match) return undefined
  const value = Number(String(match[1]).replace(/,/g, ""))
  if (!Number.isFinite(value)) return undefined
  const unit = String(match[2] || "元").toLowerCase()
  return value * ({ "亿": 100000000, "万": 10000, w: 10000, k: 1000, "元": 1 } as Record<string, number>)[unit]
}

async function runReport(type: ReportType) {
  if (loading.value) return
  const title = { daily: "生成今天的经营日报", weekly: "生成本周经营复盘", monthly: "生成本月经营复盘", mtd: "生成本月至今经营复盘", daily_series: "生成本月逐日经营日报" }[type]
  await send(title, type)
}

async function send(value = question.value, reportType?: ReportType) {
  const text = value.trim()
  if (!text || loading.value || !activeSession.value) return
  const targetSession = activeSession.value
  question.value = ""
  error.value = ""
  loading.value = true
  const userMessage: ChatMessage = { id: uid(), role: "user", text, createdAt: Date.now() }
  const pending: ChatMessage = { id: uid(), role: "assistant", loading: true, createdAt: Date.now() }
  startThinkingClock(pending)
  const controller = new AbortController()
  abortController.value = controller
  streamStatus.start()
  updateSessionMessages(targetSession, [...targetSession.messages, userMessage, pending])
  scrollConversation()
  const onStreamEvent = (event: AIStreamEvent) => {
    streamStatus.accept(event)
    const current = targetSession.messages.find((item) => item.id === pending.id)
    if (!current) return
    if (event.event === "token" && event.text) current.streamText = `${current.streamText || ""}${event.text}`
    if (event.event === "skill") {
      current.activeSkill = event.skill
      current.supportingSkills = event.supporting_skills || []
    }
    if (["planner", "skill", "mcp", "model"].includes(event.event)) {
      const steps = current.streamSteps || (current.streamSteps = [])
      const existing = [...steps].reverse().find((item) => item.kind === event.event && item.name === (event.name || event.event))
      if (existing && existing.status === "running") {
        const nextStatus = event.status || "completed"
        Object.assign(existing, { status: nextStatus, detail: event.detail || existing.detail })
        if (nextStatus !== "running" && existing.startedAt) existing.elapsedMs = performance.now() - existing.startedAt
      } else {
        const step: StreamStep = { kind: event.event, name: event.name || event.event, status: event.status || "running", detail: event.detail || "", startedAt: performance.now() }
        if (step.status !== "running") step.elapsedMs = 0
        steps.push(step)
      }
    }
    scrollConversation()
  }
  try {
    if (reportType) {
        const report = await streamPeriodReport({ report_type: reportType, conversation_id: targetSession.id, anchor_date: currentRange.value, store_id: currentStoreId.value, use_model: true }, onStreamEvent, controller.signal)
      stopThinkingClock(pending)
      updateSessionMessages(targetSession, [...targetSession.messages.filter((item) => item.id !== pending.id), { ...pending, loading: false, report }])
    } else {
      const inferredReportIntent = inferReportIntent(text)
      if (inferredReportIntent) {
        const report = await streamPeriodReport({ report_type: inferredReportIntent.report_type, conversation_id: targetSession.id, anchor_date: inferredReportIntent.anchor_date || currentRange.value, store_id: currentStoreId.value, target_gmv: extractTargetGmv(text), use_model: true }, onStreamEvent, controller.signal)
        stopThinkingClock(pending)
        updateSessionMessages(targetSession, [...targetSession.messages.filter((item) => item.id !== pending.id), { ...pending, loading: false, report }])
      } else {
        const request = { question: text, conversation_id: targetSession.id, store_id: currentStoreId.value, start_date: analysisStartDate.value, end_date: analysisEndDate.value, page_context: workbenchPageContext.value, use_model: true }
        const analysis = isLightChatQuestion(text)
          ? await analyzeWithAI(request, controller.signal)
          : await streamAnalyzeWithAI(request, onStreamEvent, controller.signal)
        stopThinkingClock(pending)
        updateSessionMessages(targetSession, [...targetSession.messages.filter((item) => item.id !== pending.id), { ...pending, loading: false, analysis }])
      }
    }
  } catch (err) {
    stopThinkingClock(pending)
    if (controller.signal.aborted) {
      updateSessionMessages(targetSession, [...targetSession.messages.filter((item) => item.id !== pending.id), { ...pending, loading: false, text: "已停止生成" }])
      return
    }
    console.error("AI request failed", err)
    error.value = errorText(err)
    updateSessionMessages(targetSession, [...targetSession.messages.filter((item) => item.id !== pending.id), { ...pending, loading: false, text: error.value, error: true }])
  } finally {
    if (abortController.value === controller) abortController.value = null
    streamStatus.finish(controller.signal.aborted ? "cancelled" : "complete")
    loading.value = false
    scrollConversation()
  }
}

function handleComposerKeydown(event: KeyboardEvent) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault()
    void send()
  }
}

onMounted(async () => {
  loadSessions()
  await syncServerSessions()
  if (activeSessionId.value) await selectSession(activeSessionId.value)
})
watch(activeSessionId, scrollConversation)
onBeforeUnmount(() => {
  stopCurrentRun()
  if (thinkingTimer) clearInterval(thinkingTimer)
})
</script>

<template>
  <div class="ai-workbench">
    <aside class="ai-workbench-sidebar" :class="{ open: showHistory }">
      <div class="ai-side-top"><div class="ai-brand-mark"><Sparkles :size="16" /></div><div><strong>AI 工作台</strong><small>经营数据助手</small></div><button class="ai-side-close" title="关闭会话栏" @click="showHistory = false"><X :size="16" /></button></div>
      <button class="ai-new-session" type="button" @click="createSession()"><Plus :size="16" />新建对话</button>
      <div class="ai-side-section"><div class="ai-side-section-title"><span>常用能力</span><small>快捷开始</small></div><button v-for="action in quickActions" :key="action.label" class="ai-capability" type="button" @click="action.report ? runReport(action.report) : useQuestion(action.prompt)"><span :class="`ai-capability-icon ${action.tone}`"><component :is="action.icon" :size="15" /></span><span>{{ action.label }}</span><ChevronRight :size="14" /></button></div>
      <div class="ai-side-section ai-history-section"><div class="ai-side-section-title"><span>最近对话</span><small>{{ sessions.length }}</small></div><div v-if="sessions.length" class="ai-session-list"><button v-for="session in sessions.slice(0, 8)" :key="session.id" class="ai-session" :class="{ active: session.id === activeSessionId }" type="button" @click="selectSession(session.id)"><MessageSquare :size="14" /><span>{{ session.title }}</span><small>{{ session.messages.length ? messageTime(session.updatedAt) : "空" }}</small><i title="删除对话" @click.stop="removeSession(session.id)"><Trash2 :size="13" /></i></button></div><div v-else class="ai-session-empty">还没有对话记录</div></div>
      <div class="ai-side-foot"><Archive :size="14" /><span>只读分析 · 数据可追溯</span></div>
    </aside>

    <section class="ai-chat-shell">
      <header class="ai-chat-header"><div class="ai-chat-title"><button class="ai-mobile-toggle" type="button" title="打开会话栏" @click="showHistory = true"><MessageSquare :size="17" /></button><div><span class="ai-eyebrow"><Bot :size="14" />AI 经营决策中心</span><h1>{{ activeSession?.title || "新对话" }}</h1></div></div><div class="ai-chat-actions"><span class="ai-live-badge"><span></span>已连接</span><button class="ai-inspector-toggle" type="button" @click="showInspector = !showInspector"><FileSearch :size="15" />数据范围</button></div></header>

      <main ref="conversation" class="ai-conversation">
        <div v-if="!messages.length" class="ai-welcome"><div class="ai-welcome-orb"><Sparkles :size="28" /></div><h2>把经营问题交给 AI</h2><p>直接提问库存、成交、流量或推广问题。AI 会先读取结构化数据，再给出结论、依据和下一步动作。</p><div class="ai-welcome-grid"><button v-for="item in suggestedQuestions" :key="item" type="button" @click="useQuestion(item)"><span>{{ item }}</span><ChevronRight :size="15" /></button></div></div>
        <template v-for="message in messages" :key="message.id">
          <div v-if="message.role === 'user'" class="ai-message ai-message-user"><div class="ai-message-body"><p>{{ message.text }}</p><time>{{ messageTime(message.createdAt) }}</time></div><div class="ai-user-avatar">A</div></div>
          <div v-else class="ai-message ai-message-assistant"><div class="ai-assistant-avatar"><Bot :size="17" /></div><div class="ai-message-body ai-result-body">
            <div v-if="message.loading" class="ai-thinking ai-agent-thinking">
              <div class="ai-thinking-head"><span class="ai-thinking-dots"><i></i><i></i><i></i></span><div><strong>{{ streamStatusTitle }}</strong><small>{{ streamStatusDetail }} · 已用 {{ elapsedText(streamElapsedMs) }}</small></div><button type="button" class="ai-stream-stop" title="停止生成" @click="stopCurrentRun"><Square :size="14" />停止</button></div>
              <div v-if="message.activeSkill" class="ai-agent-capabilities"><span>主 Agent</span><b>{{ message.activeSkill.display_name }}</b><em v-for="skill in message.supportingSkills || []" :key="skill.name">{{ skill.display_name }}</em></div>
              <div v-if="message.streamSteps?.length" class="ai-live-step-list"><div v-for="(step, index) in message.streamSteps" :key="`${step.kind}-${step.name}-${index}`" :class="`is-${step.status}`"><LoaderCircle v-if="step.status === 'running'" :size="13" class="spinning" /><CheckCircle2 v-else-if="step.status === 'completed'" :size="13" /><TriangleAlert v-else-if="step.status === 'failed'" :size="13" /><Clock3 v-else :size="13" /><span><b>{{ streamStepLabel(step) }}</b><small>{{ step.detail }}</small></span></div></div>
               <div v-if="message.streamText" class="ai-stream-answer ai-markdown-content" v-html="renderReportNarrative(message.streamText)"></div>
            </div>
            <div v-else-if="message.text && message.error" class="ai-error-message"><TriangleAlert :size="16" /><span>{{ message.text }}</span></div>
            <div v-else-if="message.text" class="ai-answer ai-markdown-content" v-html="renderReportNarrative(message.text)"></div>
            <template v-else-if="message.analysis">
              <template v-if="isGeneralChatMessage(message)">
                <div class="ai-chat-reply">
                  <h2>{{ cleanReportNarrative(message.analysis.diagnosis.headline) }}</h2>
                  <p>{{ cleanReportNarrative(message.analysis.diagnosis.summary) }}</p>
                  <div v-if="nextQuestions(message).length" class="ai-question-chips"><button v-for="item in nextQuestions(message).slice(0, 4)" :key="item" type="button" @click="useQuestion(item)">{{ cleanReportNarrative(item) }}</button></div>
                </div>
              </template>
              <template v-else>
              <div class="ai-result-top"><span class="ai-result-type"><CheckCircle2 :size="14" />{{ message.analysis.skill.display_name }}</span><span class="ai-result-status" :class="`status-${message.analysis.status}`">{{ statusText(message.analysis.status) }}</span><span class="ai-confidence">置信度 {{ message.analysis.diagnosis.confidence === 'high' ? '高' : message.analysis.diagnosis.confidence === 'low' ? '低' : '中' }}</span></div>
              <div class="ai-agent-capabilities ai-agent-capabilities-final"><span>Agent 能力</span><b>{{ message.analysis.skill.display_name }}</b><em v-for="skill in message.analysis.supporting_skills" :key="skill.name">{{ skill.display_name }}</em><small>{{ message.analysis.execution_steps.filter((step) => step.kind === 'mcp' && step.status === 'completed').length }} 个数据工具已完成</small></div>
              <h2>{{ cleanReportNarrative(message.analysis.diagnosis.headline) }}</h2><section v-if="message.analysis.provider !== 'rules' && cleanReportNarrative(message.analysis.answer)" class="ai-model-supplement"><div class="ai-block-title"><Sparkles :size="14" />AI 补充判断 <small>{{ message.analysis.model }}</small></div><div class="ai-answer ai-markdown-content" v-html="renderReportNarrative(message.analysis.answer)"></div></section>
              <div v-if="!inventoryData(message)" class="ai-coverage-card"><div><small>数据覆盖</small><strong>{{ message.analysis.diagnosis.coverage.covered_days || 0 }}/{{ message.analysis.diagnosis.coverage.expected_days || 0 }} 天</strong></div><div><small>最新业务日</small><strong>{{ message.analysis.diagnosis.coverage.latest_data_date || '--' }}</strong></div><div><small>辅助能力</small><strong>{{ message.analysis.supporting_skills.length }} 个</strong></div><span v-if="message.analysis.diagnosis.coverage.missing_dates.length" class="coverage-alert">缺失 {{ message.analysis.diagnosis.coverage.missing_dates.slice(0, 3).join('、') }}<span v-if="message.analysis.diagnosis.coverage.missing_dates.length > 3"> 等</span></span><span v-else-if="message.analysis.diagnosis.coverage.no_data_datasets.length" class="coverage-muted">平台无数据：{{ message.analysis.diagnosis.coverage.no_data_datasets.slice(0, 2).join('、') }}</span></div>
              <div v-if="utryCurrent(message)" class="ai-utry-summary">
                <article><small>同店 30 日回购</small><strong>{{ money(utryCurrent(message)?.store_30d_repurchase_amount) }}</strong><span>{{ formatNumber(utryCurrent(message)?.store_30d_repurchase_uv) }} UV</span></article>
                <article><small>同店 90 日回购</small><strong>{{ money(utryCurrent(message)?.store_90d_repurchase_amount) }}</strong><span>{{ formatNumber(utryCurrent(message)?.store_90d_repurchase_uv) }} UV</span></article>
                <article class="is-primary"><small>同店 365 日回购</small><strong>{{ money(utryCurrent(message)?.store_365d_repurchase_amount) }}</strong><span>{{ formatNumber(utryCurrent(message)?.store_365d_repurchase_uv) }} UV</span></article>
                <article><small>同品牌 365 日回购</small><strong>{{ money(utryCurrent(message)?.brand_365d_repurchase_amount) }}</strong><span>{{ formatNumber(utryCurrent(message)?.brand_365d_repurchase_uv) }} UV</span></article>
                <article><small>已绑定正装</small><strong>{{ formatNumber(utryCurrent(message)?.bound_regular_product_count) }} / {{ formatNumber(utryCurrent(message)?.product_count) }}</strong><span>{{ formatNumber(utryCurrent(message)?.bound_regular_product_share, 1) }}%</span></article>
                <article class="is-warning"><small>回购权益配置</small><strong>{{ formatNumber(utryCurrent(message)?.configured_coupon_count) }} / {{ formatNumber(utryCurrent(message)?.configured_gift_count) }}</strong><span>回购券 / 礼金</span></article>
              </div>
              <section v-if="analysisArtifact(message, '总盘口径校验') || analysisArtifact(message, '跨域数据状态')" class="ai-fact-sheet">
                <header><div><strong>全店事实底座</strong><small>总盘口径优先，跨域数据只用于解释与验证</small></div><span>证据已统一</span></header>
                <div v-if="analysisArtifact(message, '总盘口径校验')?.rows?.length" class="ai-fact-metric-grid">
                  <article v-for="row in analysisArtifact(message, '总盘口径校验')?.rows?.slice(0, 4)" :key="String(row['指标'])"><small>{{ row['指标'] }}</small><strong>{{ formatCell(row['本期']) }}</strong><em>{{ row['环比%'] == null ? '--' : `${Number(row['环比%']) >= 0 ? '+' : ''}${formatNumber(row['环比%'], 1)}%` }}</em><span>上期 {{ formatCell(row['上期']) }}</span></article>
                </div>
                <div v-if="analysisArtifact(message, '跨域数据状态')?.rows?.length" class="ai-fact-domain-list"><div v-for="row in analysisArtifact(message, '跨域数据状态')?.rows" :key="String(row['经营域'])"><strong>{{ row['经营域'] }}</strong><span :class="factStatusClass(row['状态'])">{{ row['状态'] }}</span><small>{{ row['证据记录'] }} 条证据 · {{ row['数据时效'] }} · {{ row['数据集'] }}</small></div></div>
              </section>
              <div v-if="inventoryDecisionSummary(message)" class="ai-inventory-summary">
                <article><small>匹配条目</small><strong>{{ formatNumber(inventoryDecisionSummary(message)?.matched_count) }}</strong></article>
                <article><small>有库存</small><strong>{{ formatNumber(inventoryDecisionSummary(message)?.available_sku_count) }}</strong></article>
                <article><small>零库存</small><strong>{{ formatNumber(inventoryDecisionSummary(message)?.zero_stock_sku_count) }}</strong></article>
                <article class="is-priority"><small>常规销售装零库存</small><strong>{{ formatNumber(inventoryGroup(message, 'regular')?.zero_stock_count || 0) }}</strong></article>
              </div>
              <div v-if="inventoryData(message)?.freshness_status === 'stale'" class="ai-inventory-freshness-alert"><TriangleAlert :size="15" /><div><strong>库存快照已过期</strong><span>约 {{ inventoryData(message)?.snapshot_age_minutes || '--' }} 分钟前采集，补货判断前建议先同步。</span></div></div>
              <div v-if="inventoryData(message)" class="ai-inventory-meta"><div><small>库存业务日</small><strong>{{ inventoryData(message)?.inventory_business_day || inventoryData(message)?.business_day || "--" }}</strong></div><div><small>快照采集时间</small><strong>{{ inventorySnapshotTime(message) }}</strong></div><div><small>快照时效</small><strong :class="`freshness-${inventoryData(message)?.freshness_status || 'unknown'}`">{{ freshnessText(inventoryData(message)?.freshness_status) }}<span v-if="inventoryData(message)?.snapshot_age_minutes != null"> · {{ inventoryData(message)?.snapshot_age_minutes }} 分钟前</span></strong></div><div><small>匹配状态</small><strong>{{ inventoryMatchText(message) }}</strong></div><div><small>覆盖记录</small><strong>{{ inventoryData(message)?.snapshot_row_count || 0 }} 条</strong></div><div><small>店铺</small><strong>{{ message.analysis.mcp_results.find((result) => result.tool === 'inventory.query')?.context?.store_id || currentStoreId || "--" }}</strong></div></div>
              <div v-if="inventoryData(message) && inventoryScopeSummary(message)" class="ai-result-block ai-inventory-scope-summary"><div class="ai-block-title"><PackageCheck :size="15" />缺货范围汇总</div><p>{{ inventoryScopeSummary(message) }}</p><small>按系列 → 类型 → 尺码 → 货品编码查看下方明细。</small></div>
              <div v-if="message.analysis.diagnosis.findings.length" class="ai-result-block"><div class="ai-block-title"><CircleHelp :size="15" />{{ inventoryData(message) ? '库存判断' : '判断依据' }}</div><div class="ai-finding-list"><article v-for="finding in message.analysis.diagnosis.findings" :key="finding.title" :class="`level-${finding.level}`"><strong>{{ cleanReportNarrative(finding.title) }}</strong><span>{{ cleanReportNarrative(finding.detail) }}</span></article></div></div>
              <template v-for="artifact in artifactsFor(message)" :key="artifact.title">
                <div v-if="chartOption(artifact)" class="ai-result-block"><div class="ai-block-title"><BarChart3 :size="15" />{{ artifact.title }}</div><BusinessChart :option="chartOption(artifact)!" ariaLabel="AI 分析图表" :height="220" /></div>
                <details v-else-if="artifact.rows?.length && isFullInventoryArtifact(artifact)" class="ai-result-block ai-collapsible-artifact"><summary><span><FileCheck2 :size="15" />{{ artifact.title }}</span><small>查看全部 {{ artifact.rows.length }} 个匹配条目</small></summary><div class="ai-evidence-scroll"><table><thead><tr><th v-for="column in artifactColumns(artifact)" :key="column">{{ column }}</th></tr></thead><tbody><tr v-for="(row, index) in artifactRows(artifact)" :key="index"><td v-for="column in artifactColumns(artifact)" :key="column">{{ formatCell(row[column]) }}</td></tr></tbody></table></div></details>
                <div v-else-if="artifact.rows?.length" class="ai-result-block"><div class="ai-block-title"><FileCheck2 :size="15" />{{ artifact.title }}</div><div class="ai-evidence-scroll"><table><thead><tr><th v-for="column in artifactColumns(artifact)" :key="column">{{ column }}</th></tr></thead><tbody><tr v-for="(row, index) in artifactRows(artifact)" :key="index"><td v-for="column in artifactColumns(artifact)" :key="column">{{ formatCell(row[column]) }}</td></tr></tbody></table></div></div>
              </template>
              <div v-if="message.analysis.diagnosis.actions.length" class="ai-result-block"><div class="ai-block-title"><Target :size="15" />建议动作</div><div class="ai-actions-list"><article v-for="action in message.analysis.diagnosis.actions" :key="`${action.priority}-${action.title}`"><b>{{ action.priority }}</b><div><strong>{{ cleanReportNarrative(action.title) }}</strong><span>{{ cleanReportNarrative(action.detail) }}</span><small>负责人：{{ action.owner }} · 验证：{{ cleanReportNarrative(action.validation || "--") }}</small><small>观察：{{ action.observation_window || "--" }} · 预期：{{ action.expected_impact || "--" }}</small></div></article></div></div>
              <div v-if="nextQuestions(message).length" class="ai-result-block ai-next-questions"><div class="ai-block-title"><Sparkles :size="15" />继续追问</div><div class="ai-question-chips"><button v-for="item in nextQuestions(message).slice(0, 4)" :key="item" type="button" @click="useQuestion(item)">{{ cleanReportNarrative(item) }}</button></div></div>
              <div v-if="message.analysis.diagnosis.missing_inputs.length || message.analysis.diagnosis.assumptions.length" class="ai-result-block ai-result-boundary"><div class="ai-block-title"><CircleHelp :size="15" />口径与待补输入</div><p v-if="message.analysis.diagnosis.missing_inputs.length">待补输入：{{ message.analysis.diagnosis.missing_inputs.join('、') }}</p><p v-for="item in message.analysis.diagnosis.assumptions" :key="item">{{ item }}</p><p v-if="message.analysis.diagnosis.causal_boundary">{{ message.analysis.diagnosis.causal_boundary }}</p></div>
              <div v-if="message.analysis.warnings.length" class="ai-result-warning"><TriangleAlert :size="14" />{{ message.analysis.warnings.join("；") }}</div>
              <details class="ai-result-block ai-reasoning-trace"><summary><span><Clock3 :size="15" />分析过程</span><small>耗时 {{ elapsedText(message.elapsedMs) }} · 点击展开</small></summary><div class="ai-live-step-list"><div v-for="(step, index) in message.streamSteps || message.analysis.execution_steps" :key="`${step.kind}-${step.name}-${index}`" :class="`is-${step.status}`"><CheckCircle2 :size="13" /><span><b>{{ streamStepLabel(step) }}</b><small>{{ step.detail }} · {{ stepElapsedText(step) }}</small></span></div></div></details>
              </template>
            </template>
            <template v-else-if="message.report">
              <div class="ai-result-top"><span class="ai-result-type"><FileCheck2 :size="14" />{{ message.report.title }}</span><span class="ai-result-status" :class="`status-${message.report.status}`">{{ statusText(message.report.status) }}</span><span v-if="reportDiagnosis(message)" class="ai-confidence">总盘置信度 {{ confidenceText(reportDecisionQuality(message)?.overall?.confidence || reportDiagnosis(message)?.confidence) }}</span></div>
              <details class="ai-result-block ai-reasoning-trace"><summary><span><Clock3 :size="15" />分析过程</span><small>耗时 {{ elapsedText(message.elapsedMs) }} · 点击展开</small></summary><div class="ai-live-step-list"><div v-for="(step, index) in message.streamSteps || message.report.execution_steps || []" :key="`${step.kind}-${step.name}-${index}`" :class="`is-${step.status}`"><CheckCircle2 :size="13" /><span><b>{{ streamStepLabel(step) }}</b><small>{{ step.detail }} · {{ stepElapsedText(step) }}</small></span></div></div></details>
              <div class="ai-report-period"><div><h2>{{ reportDisplayTitle(message) }}</h2><small>{{ message.report.range_start }} 至 {{ message.report.range_end }}<template v-if="message.report.report.previous_period"> · 对比 {{ message.report.report.previous_period.range_start }} 至 {{ message.report.report.previous_period.range_end }}</template></small></div><span v-if="message.report.report.data_quality?.latest_data_date">最新业务日 {{ message.report.report.data_quality.latest_data_date }}</span></div>
              <div v-if="reportDecisionQuality(message)?.modules?.length" class="ai-quality-strip"><article v-for="item in reportDecisionQuality(message)?.modules" :key="item.key" :class="`confidence-${item.confidence}`" :title="item.reason"><span>{{ item.label }}</span><strong>{{ confidenceText(item.confidence) }}</strong></article></div>
              <section v-if="reportDailyRows(message).length" class="ai-report-section"><div class="ai-section-title"><strong>逐日经营明细</strong><small>{{ reportDailyRows(message).length }} 天 · 支付金额口径</small></div><div class="ai-report-table-wrap"><table class="ai-report-table"><thead><tr><th>业务日</th><th>GMV</th><th>访客</th><th>支付买家</th><th>转化率</th><th>退款金额</th><th>推广花费</th></tr></thead><tbody><tr v-for="row in reportDailyRows(message)" :key="row.stat_date"><td>{{ row.stat_date }}</td><td>{{ money(row.paid_amount) }}</td><td>{{ formatNumber(row.visitors) }}</td><td>{{ formatNumber(row.buyers) }}</td><td>{{ percent(row.conversion_rate) }}</td><td>{{ money(row.refund_amount) }}</td><td>{{ money(row.promotion_plan_spend) }}</td></tr></tbody></table></div></section>
              <div class="ai-report-kpis ai-report-kpis-expanded">
                <article><small>GMV</small><strong>{{ money(reportOps(message).gmv) }}</strong><em :class="reportChangeClass(message, 'paid_amount')">{{ reportChangeText(message, 'paid_amount') }}</em></article>
                <article><small>去退 GMV</small><strong>{{ money(reportOps(message).net_gmv) }}</strong><em>退款后口径</em></article>
                <article><small>退款金额占比</small><strong>{{ percent(reportOps(message).refund_rate) }}</strong><em :class="reportChangeClass(message, 'paid_amount')">金额 {{ money(reportOps(message).refund_amount) }}</em></article>
                <article><small>访客 UV</small><strong>{{ formatNumber(reportOps(message).visitors) }}</strong><em :class="reportChangeClass(message, 'visitors')">{{ reportChangeText(message, 'visitors') }}</em></article>
                <article><small>支付买家</small><strong>{{ formatNumber(reportOps(message).buyers) }}</strong><em :class="reportChangeClass(message, 'buyers')">{{ reportChangeText(message, 'buyers') }}</em></article>
                <article><small>支付转化率</small><strong>{{ percent(reportOps(message).conversion_rate) }}</strong><em :class="reportChangeClass(message, 'conversion_rate')">{{ reportChangeText(message, 'conversion_rate') }}</em></article>
                <article><small>客单价</small><strong>¥{{ formatNumber(reportOps(message).customer_unit_price, 2) }}</strong><em :class="reportChangeClass(message, 'customer_unit_price')">{{ reportChangeText(message, 'customer_unit_price') }} · 支付金额 ÷ 支付买家</em></article>
                <article><small>新客支付占比</small><strong>{{ percent(reportOps(message).new_customer_buyer_share) }}</strong><em>新客买家 ÷ 支付买家</em></article>
              </div>
              <div v-if="message.report.report.target" class="ai-report-target"><div><small>销售目标</small><strong>{{ money(message.report.report.target.target_gmv) }}</strong></div><div><small>当前完成率</small><strong>{{ percent(message.report.report.target.completion_rate) }}</strong></div><div><small>时间进度</small><strong>{{ percent(message.report.report.target.time_progress) }}</strong></div><div><small>进度差</small><strong :class="Number(message.report.report.target.pace_gap || 0) < 0 ? 'down' : 'up'">{{ message.report.report.target.pace_gap == null ? '--' : `${Number(message.report.report.target.pace_gap) >= 0 ? '+' : ''}${formatNumber(message.report.report.target.pace_gap, 1)} 个百分点` }}</strong></div><div v-if="message.report.report.target.remaining_days"><small>剩余目标</small><strong>{{ money(message.report.report.target.remaining_gmv) }}</strong><em>剩余 {{ message.report.report.target.remaining_days }} 天 · 日均 {{ money(message.report.report.target.required_daily_gmv) }}</em></div></div>
              <section v-if="reportDiagnosis(message)" class="ai-report-section ai-report-summary"><div class="ai-section-title"><strong>今日结论</strong><small>先看结果，再看原因</small></div><h3>{{ reportDiagnosis(message)?.headline }}</h3><p>{{ reportDiagnosis(message)?.summary }}</p></section>
              <section v-if="reportDriverRows(message).length" class="ai-report-section ai-driver-section"><div class="ai-section-title"><strong>GMV 变化驱动</strong><small>影响金额合计回勾 GMV 差额</small></div><div class="ai-driver-bridge"><article v-for="row in reportDriverRows(message)" :key="row.key" :class="Number(row.impact_amount) < 0 ? 'negative' : 'positive'"><div><span>{{ row.label }}</span><small>{{ row.change_percent == null ? '无可比环比' : `${Number(row.change_percent) >= 0 ? '+' : ''}${formatNumber(row.change_percent, 1)}%` }}</small></div><strong>{{ signedMoney(row.impact_amount) }}</strong></article></div><p>{{ reportDriverBridge(message)?.note }}</p></section>
              <section v-if="message.report.provider !== 'rules' && cleanReportNarrative(message.report.text) && cleanReportNarrative(message.report.text) !== reportDiagnosis(message)?.summary" class="ai-report-section ai-report-narrative"><div class="ai-section-title"><strong>AI 补充判断</strong><small>{{ message.report.model }} · 不复述页面表格</small></div><div class="ai-answer ai-markdown-content" v-html="renderReportNarrative(message.report.text)"></div></section>
              <section v-if="reportDiagnosis(message)?.actions?.length" class="ai-report-section"><div class="ai-section-title"><strong>今日动作</strong><small>按优先级执行</small></div><div class="ai-report-actions"><article v-for="action in reportDiagnosis(message)?.actions.slice(0, 5) || []" :key="`${action.priority}-${action.title}`"><b>{{ action.priority }}</b><div><strong>{{ action.title }}</strong><span>{{ action.detail }}</span><small>验证：{{ action.validation || '--' }}</small></div></article></div><div v-if="nextQuestions(message).length" class="ai-question-chips"><button v-for="item in nextQuestions(message).slice(0, 4)" :key="item" type="button" @click="useQuestion(item)">{{ item }}</button></div></section>
              <section v-if="reportDiagnosis(message)?.findings?.length" class="ai-report-section"><div class="ai-section-title"><strong>问题定位</strong><small>{{ reportDiagnosis(message)?.findings.length }} 项判断</small></div><div class="ai-report-findings"><article v-for="finding in reportDiagnosis(message)?.findings.slice(0, 5) || []" :key="finding.title" :class="`level-${finding.level}`"><strong>{{ finding.title }}</strong><span>{{ finding.detail }}</span></article></div></section>
              <section v-if="reportChannelRows(message).length" class="ai-report-section"><div class="ai-section-title"><strong>渠道成交标签</strong><small>各自以店铺 GMV 为分母 · 不可相加</small></div><p v-if="reportChannelScope(message)" class="ai-scope-note"><TriangleAlert :size="13" />{{ reportChannelScope(message)?.note }}</p><div class="ai-report-table-wrap"><table class="ai-report-table"><thead><tr><th>渠道/标签</th><th>成交金额</th><th>销售占比</th><th>已知费用</th><th>状态</th></tr></thead><tbody><tr v-for="row in reportChannelRows(message)" :key="row.key"><td>{{ row.label }}</td><td>{{ money(row.paid_amount) }}</td><td>{{ percent(row.sales_share) }}</td><td>{{ row.expense == null ? '--' : money(row.expense) }}</td><td><span class="ai-table-status">可用</span></td></tr></tbody></table></div></section>
              <section v-if="reportPromotionRows(message).length" class="ai-report-section"><div class="ai-section-title"><strong>推广投入产出</strong><small>15 天归因窗口 · 归因成交不等于因果增量</small></div><div class="ai-report-table-wrap"><table class="ai-report-table"><thead><tr><th>场景</th><th>花费</th><th>归因成交</th><th>ROI</th><th>直接/间接成交</th></tr></thead><tbody><tr v-for="row in reportPromotionRows(message).slice(0, 8)" :key="row.display_name" :class="{ 'is-low-efficiency': row.roi_value < 1 }"><td>{{ row.display_name }}</td><td>{{ money(row.spend_value) }}</td><td>{{ money(row.gmv_value) }}</td><td><strong>{{ formatNumber(row.roi_value, 2) }}</strong></td><td>{{ money(row.direct_paid_amount) }} / {{ money(row.indirect_paid_amount) }}</td></tr></tbody></table></div></section>
              <section v-if="reportTalentRows(message).length" class="ai-report-section"><div class="ai-section-title"><strong>直播 / 达人贡献</strong><small>缺少完整佣金时不判断盈利</small></div><div class="ai-report-table-wrap"><table class="ai-report-table"><thead><tr><th>达人</th><th>成交金额</th><th>合作场次</th><th>支付买家</th><th>单场 GMV</th><th>单买家产出</th></tr></thead><tbody><tr v-for="row in reportTalentRows(message)" :key="row.name"><td>{{ row.name || '--' }}</td><td>{{ money(row.gmv) }}</td><td>{{ formatNumber(row.sessions) }}</td><td>{{ formatNumber(row.buyers) }}</td><td>{{ row.sessions ? money(Number(row.gmv || 0) / Number(row.sessions)) : '--' }}</td><td>{{ row.buyers ? `¥${formatNumber(Number(row.gmv || 0) / Number(row.buyers), 2)}` : '--' }}</td></tr></tbody></table></div></section>
              <section v-if="reportQuality(message).missingSections.length || reportQuality(message).noDataSections.length || reportQuality(message).missingDates.length || reportQuality(message).missingDatasets.length || reportQuality(message).partialDatasets.length || reportQuality(message).failedDatasets.length || reportQuality(message).noDataDatasets.length || message.report.warnings.length" class="ai-report-section ai-report-quality"><div class="ai-section-title"><strong>数据状态</strong><small>不把缺失数据当作 0</small></div><p v-if="reportQuality(message).missingSections.length">待补采模块：{{ reportQuality(message).missingSections.join('、') }}</p><p v-if="reportQuality(message).missingDatasets.length">待补采数据集：{{ reportQuality(message).missingDatasets.join('、') }}</p><p v-if="reportQuality(message).partialDatasets.length">部分覆盖：{{ reportQuality(message).partialDatasets.join('、') }}</p><p v-if="reportQuality(message).failedDatasets.length">采集失败：{{ reportQuality(message).failedDatasets.join('、') }}</p><p v-if="reportQuality(message).noDataSections.length">平台无数据模块：{{ reportQuality(message).noDataSections.join('、') }}</p><p v-if="reportQuality(message).noDataDatasets.length">平台无数据集：{{ reportQuality(message).noDataDatasets.join('、') }}</p><p v-if="reportQuality(message).missingDates.length">缺失日期：{{ reportQuality(message).missingDates.join('、') }}</p><p v-for="warning in message.report.warnings" :key="warning">{{ warning }}</p></section>
            </template>
            <footer v-if="!message.loading" class="ai-message-meta"><Clock3 :size="12" />{{ messageTime(message.createdAt) }}<span v-if="message.elapsedMs != null && !isGeneralChatMessage(message)">· 分析耗时 {{ elapsedText(message.elapsedMs) }}</span><span v-if="message.analysis && !isGeneralChatMessage(message)">· {{ message.analysis.provider === "rules" ? "规则引擎" : message.analysis.model }}</span><span v-if="message.report">· 保留口径与覆盖提示</span></footer>
          </div></div>
        </template>
      </main>

      <footer class="ai-composer-shell"><div class="ai-composer-hint"><span><CalendarDays :size="13" />{{ currentRangeLabel }}</span><span><Archive :size="13" />只读分析</span></div><form class="ai-workbench-composer" @submit.prevent="send()"><textarea ref="composer" v-model="question" rows="1" placeholder="问问你的经营数据，例如：查大鱼 M 码库存，或为什么昨天成交下降？" @keydown="handleComposerKeydown"></textarea><button type="submit" :disabled="loading || !question.trim()" title="发送问题"><LoaderCircle v-if="loading" :size="18" class="spinning" /><Send v-else :size="18" /></button></form><div class="ai-composer-footer"><span>Enter 发送 · Shift + Enter 换行</span><button type="button" @click="createSession()"><Plus :size="13" />新对话</button></div></footer>
    </section>

    <aside class="ai-inspector" :class="{ open: showInspector }"><div class="ai-inspector-header"><div><span>本轮上下文</span><strong>{{ isGeneralChatMessage(lastAssistantMessage) ? '继续提问' : '数据与证据' }}</strong></div><button type="button" title="关闭数据范围" @click="showInspector = false"><X :size="16" /></button></div><section v-if="!isGeneralChatMessage(lastAssistantMessage)" class="ai-context-card"><div class="ai-context-card-icon"><CalendarDays :size="16" /></div><div><small>统计范围</small><strong>{{ currentRangeLabel }}</strong><span>经营分析使用页面范围；库存使用最新时点快照</span></div></section><section v-if="!isGeneralChatMessage(lastAssistantMessage)" class="ai-context-card"><div class="ai-context-card-icon blue"><Check :size="16" /></div><div><small>分析模式</small><strong>只读 · 可追溯</strong><span>不直接修改店铺数据</span></div></section><section v-if="lastAssistantMessage?.analysis && inventoryData(lastAssistantMessage)" class="ai-context-card"><div class="ai-context-card-icon amber"><Clock3 :size="16" /></div><div><small>库存更新</small><strong>{{ freshnessText(inventoryData(lastAssistantMessage)?.freshness_status) }}</strong><span>每小时同步；最近 {{ inventorySnapshotTime(lastAssistantMessage) }}</span></div></section><section class="ai-inspector-section"><div class="ai-inspector-title"><span>建议追问</span><small>{{ lastAssistantMessage?.analysis?.diagnosis?.next_questions?.length ? '来自本轮分析' : '快速继续' }}</small></div><button v-for="item in inspectorQuestions" :key="`inspector-${item}`" type="button" @click="useQuestion(item)">{{ cleanReportNarrative(item) }}<ChevronRight :size="14" /></button></section><section v-if="lastAssistantMessage?.analysis && !isGeneralChatMessage(lastAssistantMessage)" class="ai-inspector-section"><div class="ai-inspector-title"><span>本轮记忆</span><small>{{ memoryLastQuestion(lastAssistantMessage) !== '--' ? '已记录' : '暂无' }}</small></div><div class="ai-step-list"><div><CheckCircle2 :size="13" /><span><b>上轮问题</b><small>{{ memoryLastQuestion(lastAssistantMessage) }}</small></span></div><div><CheckCircle2 :size="13" /><span><b>本轮结论</b><small>{{ memoryHeadline(lastAssistantMessage) }}</small></span></div><div><CheckCircle2 :size="13" /><span><b>分析能力</b><small>{{ memorySkill(lastAssistantMessage) }}</small></span></div><div><CheckCircle2 :size="13" /><span><b>分析范围</b><small>{{ memoryRange(lastAssistantMessage) }}</small></span></div></div></section><section v-if="lastAssistantMessage?.analysis && !isGeneralChatMessage(lastAssistantMessage) && memoryEvidenceRefs(lastAssistantMessage).length" class="ai-inspector-section"><div class="ai-inspector-title"><span>证据引用</span><small>{{ memoryEvidenceRefs(lastAssistantMessage).length }} 项</small></div><div class="ai-step-list"><div v-for="item in memoryEvidenceRefs(lastAssistantMessage).slice(0, 6)" :key="item"><CheckCircle2 :size="13" /><span>{{ item }}</span></div></div></section><section v-if="lastAssistantMessage?.analysis && !isGeneralChatMessage(lastAssistantMessage)" class="ai-inspector-section"><div class="ai-inspector-title"><span>本轮执行</span><small>{{ lastAssistantMessage.analysis.execution_steps.length }} 步</small></div><div class="ai-step-list"><div v-for="step in lastAssistantMessage.analysis.execution_steps" :key="`${step.kind}-${step.name}`"><CheckCircle2 :size="13" /><span>{{ step.detail }}</span></div></div></section><div class="ai-inspector-foot"><Bot :size="15" />回答只使用本地结构化数据和已配置的分析模型</div></aside>
    <button v-if="showHistory || showInspector" class="ai-mobile-backdrop" type="button" aria-label="关闭侧栏" @click="showHistory = false; showInspector = false"></button>
  </div>
</template>
