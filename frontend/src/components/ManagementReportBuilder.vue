<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { CalendarRange, ChevronDown, FileChartColumn, Sparkles, Target, X } from "lucide-vue-next"

export type ManagementReportRequest = {
  report_type: "business_review"
  start_date: string
  end_date: string
  comparison_mode: "previous_period" | "same_period_last_year" | "custom"
  comparison_start_date?: string | null
  comparison_end_date?: string | null
  report_title?: string | null
  target_gmv?: number | null
  planning_targets: Record<string, number | null>
  business_events: string[]
  strategy_notes: string
}

const props = defineProps<{ defaultStart?: string; defaultEnd?: string; loading?: boolean }>()
const emit = defineEmits<{ generate: [request: ManagementReportRequest]; close: [] }>()

const startDate = ref(props.defaultStart || "")
const endDate = ref(props.defaultEnd || "")
const comparisonMode = ref<ManagementReportRequest["comparison_mode"]>("same_period_last_year")
const comparisonStartDate = ref("")
const comparisonEndDate = ref("")
const reportTitle = ref("")
const targetGmv = ref<number | null>(null)
const targetNetGmv = ref<number | null>(null)
const targetVisitors = ref<number | null>(null)
const targetBuyers = ref<number | null>(null)
const targetConversion = ref<number | null>(null)
const targetUnitPrice = ref<number | null>(null)
const businessEvents = ref("")
const strategyNotes = ref("")
const showPlanning = ref(false)

watch(() => props.defaultStart, (value) => { if (value) startDate.value = value })
watch(() => props.defaultEnd, (value) => { if (value) endDate.value = value })

const canSubmit = computed(() => Boolean(
  startDate.value && endDate.value && startDate.value <= endDate.value
  && (comparisonMode.value !== "custom" || (
    comparisonStartDate.value && comparisonEndDate.value && comparisonStartDate.value <= comparisonEndDate.value
  )),
))

function yuanFromWan(value: number | null) {
  return value == null || !Number.isFinite(Number(value)) ? null : Number(value) * 10000
}

function countFromWan(value: number | null) {
  return value == null || !Number.isFinite(Number(value)) ? null : Number(value) * 10000
}

function submit() {
  if (!canSubmit.value || props.loading) return
  emit("generate", {
    report_type: "business_review",
    start_date: startDate.value,
    end_date: endDate.value,
    comparison_mode: comparisonMode.value,
    comparison_start_date: comparisonMode.value === "custom" ? comparisonStartDate.value : null,
    comparison_end_date: comparisonMode.value === "custom" ? comparisonEndDate.value : null,
    report_title: reportTitle.value.trim() || null,
    target_gmv: yuanFromWan(targetGmv.value),
    planning_targets: {
      net_gmv: yuanFromWan(targetNetGmv.value),
      visitors: countFromWan(targetVisitors.value),
      buyers: countFromWan(targetBuyers.value),
      conversion_rate: targetConversion.value,
      customer_unit_price: targetUnitPrice.value,
    },
    business_events: businessEvents.value.split(/\r?\n|；|;/).map((item) => item.trim()).filter(Boolean),
    strategy_notes: strategyNotes.value.trim(),
  })
}
</script>

<template>
  <section class="management-report-builder" aria-label="经营复盘配置">
    <header>
      <div class="management-builder-title">
        <FileChartColumn :size="18" />
        <div><strong>经营复盘</strong><small>历史事实与经营规划分开核验</small></div>
      </div>
      <button type="button" title="关闭经营复盘配置" @click="emit('close')"><X :size="17" /></button>
    </header>

    <div class="management-builder-body">
      <div class="management-builder-section">
        <div class="management-builder-section-title"><CalendarRange :size="15" /><strong>统计与对比</strong></div>
        <div class="management-builder-grid">
          <label><span>开始日期</span><input v-model="startDate" type="date" /></label>
          <label><span>结束日期</span><input v-model="endDate" type="date" /></label>
          <label class="is-wide"><span>报告标题</span><input v-model="reportTitle" type="text" placeholder="例如：26年1-8月经营复盘" maxlength="120" /></label>
        </div>
        <div class="management-comparison-control" aria-label="对比方式">
          <button type="button" :class="{ active: comparisonMode === 'same_period_last_year' }" @click="comparisonMode = 'same_period_last_year'">去年同期</button>
          <button type="button" :class="{ active: comparisonMode === 'previous_period' }" @click="comparisonMode = 'previous_period'">相邻周期</button>
          <button type="button" :class="{ active: comparisonMode === 'custom' }" @click="comparisonMode = 'custom'">自定义</button>
        </div>
        <div v-if="comparisonMode === 'custom'" class="management-builder-grid custom-comparison">
          <label><span>对比开始</span><input v-model="comparisonStartDate" type="date" /></label>
          <label><span>对比结束</span><input v-model="comparisonEndDate" type="date" /></label>
        </div>
      </div>

      <div class="management-builder-section">
        <div class="management-builder-section-title"><Sparkles :size="15" /><strong>经营背景</strong></div>
        <div class="management-builder-grid">
          <label class="is-wide"><span>经营事件</span><textarea v-model="businessEvents" rows="3" placeholder="每行一个事件，例如：6月舆情事件"></textarea></label>
          <label class="is-wide"><span>策略与约束</span><textarea v-model="strategyNotes" rows="3" placeholder="价格政策、重点系列、渠道安排、达人合作等"></textarea></label>
        </div>
      </div>

      <details class="management-planning-panel" :open="showPlanning" @toggle="showPlanning = ($event.target as HTMLDetailsElement).open">
        <summary><span><Target :size="15" /><strong>规划目标</strong><small>选填 · 自动校验支付金额方程</small></span><ChevronDown :size="15" /></summary>
        <div class="management-builder-grid planning-grid">
          <label><span>支付目标（万）</span><input v-model.number="targetGmv" type="number" min="0" step="0.1" /></label>
          <label><span>净支付目标（万）</span><input v-model.number="targetNetGmv" type="number" min="0" step="0.1" /></label>
          <label><span>访客目标（万）</span><input v-model.number="targetVisitors" type="number" min="0" step="0.1" /></label>
          <label><span>支付买家目标（万）</span><input v-model.number="targetBuyers" type="number" min="0" step="0.1" /></label>
          <label><span>转化率目标（%）</span><input v-model.number="targetConversion" type="number" min="0" max="100" step="0.1" /></label>
          <label><span>客单价目标（元）</span><input v-model.number="targetUnitPrice" type="number" min="0" step="0.1" /></label>
        </div>
      </details>
    </div>

    <footer>
      <span>事实由系统计算，事件与规划按人工输入标记</span>
      <button type="button" :disabled="!canSubmit || loading" @click="submit"><Sparkles :size="15" />{{ loading ? "生成中" : "生成经营复盘" }}</button>
    </footer>
  </section>
</template>
