<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { CalendarDays, ChevronLeft, ChevronRight, Eye, LoaderCircle, ShoppingBag } from "lucide-vue-next"

import type { StoreRecord } from "@/types"
import { compactRange, shortDate } from "@/lib/format"

const props = defineProps<{
  store: StoreRecord | null
  startDate: string
  endDate: string
  loading: boolean
}>()

const emit = defineEmits<{
  "update:startDate": [value: string]
  "update:endDate": [value: string]
  submit: []
}>()

type RangeMode = "7天" | "30天" | "日" | "周" | "月" | "自定义"
type CalendarCell = { date: string; day: number; inCurrentMonth: boolean; disabled: boolean }

const rangeMode = ref<RangeMode>("7天")
const initializedRange = ref(false)
const dropdownOpen = ref(false)
const calendarCursor = ref(props.endDate ? props.endDate.slice(0, 7) : "2026-08")
const availableEndDate = ref(props.endDate)
const rangeOptions: RangeMode[] = ["7天", "30天", "日", "周", "月", "自定义"]
const monthNames = Array.from({ length: 12 }, (_, index) => `${index + 1}月`)
const isDirectRange = computed(() => rangeMode.value === "7天" || rangeMode.value === "30天")
const isCalendarMode = computed(() => rangeMode.value === "日" || rangeMode.value === "周")

watch(() => props.endDate, (value) => {
  if (value && !availableEndDate.value) availableEndDate.value = value
  if (value && !dropdownOpen.value) calendarCursor.value = value.slice(0, 7)
})

watch([() => props.startDate, () => props.endDate], ([start, end]) => {
  if (initializedRange.value || !start || !end) return
  initializedRange.value = true
  if (start === shiftDate(end, -6)) rangeMode.value = "7天"
  else if (start === shiftDate(end, -29)) rangeMode.value = "30天"
  else if (start === end) rangeMode.value = "日"
  else if (start === currentWeekStart(end)) rangeMode.value = "周"
  else if (start === `${end.slice(0, 7)}-01`) rangeMode.value = "月"
  else rangeMode.value = "自定义"
}, { immediate: true })

function formatLocalDate(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, "0")
  const day = String(date.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

function parseDate(value: string): Date {
  return new Date(`${value}T12:00:00`)
}

function shiftDate(value: string, amount: number): string {
  const date = parseDate(value)
  date.setDate(date.getDate() + amount)
  return formatLocalDate(date)
}

function currentWeekStart(value: string): string {
  const date = parseDate(value)
  const weekday = date.getDay() || 7
  date.setDate(date.getDate() - weekday + 1)
  return formatLocalDate(date)
}

function endOfMonth(year: number, month: number): string {
  const lastDay = new Date(year, month + 1, 0).getDate()
  return `${year}-${String(month + 1).padStart(2, "0")}-${String(lastDay).padStart(2, "0")}`
}

function setPeriod(start: string, end: string): void {
  emit("update:startDate", start)
  emit("update:endDate", end)
  dropdownOpen.value = false
  emit("submit")
}

function selectRange(mode: RangeMode): void {
  if (!props.endDate) return
  if (mode === "7天" || mode === "30天") {
    rangeMode.value = mode
    setPeriod(shiftDate(props.endDate, mode === "7天" ? -6 : -29), props.endDate)
    return
  }
  rangeMode.value = mode
  calendarCursor.value = props.endDate.slice(0, 7)
  dropdownOpen.value = !dropdownOpen.value
}

function chooseCalendarDay(value: string): void {
  if (value > availableEndDate.value) return
  if (rangeMode.value === "日") {
    setPeriod(value, value)
    return
  }
  const start = currentWeekStart(value)
  const proposedEnd = shiftDate(start, 6)
  setPeriod(start, proposedEnd > availableEndDate.value ? availableEndDate.value : proposedEnd)
}

function chooseMonth(value: string): void {
  if (value > availableEndDate.value.slice(0, 7)) return
  const [yearText, monthText] = value.split("-")
  const end = value === availableEndDate.value.slice(0, 7)
    ? availableEndDate.value
    : endOfMonth(Number(yearText), Number(monthText) - 1)
  calendarCursor.value = value
  setPeriod(`${value}-01`, end)
}

function shiftCursor(amount: number): void {
  const date = parseDate(`${calendarCursor.value}-01`)
  date.setMonth(date.getMonth() + amount)
  const next = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`
  if (amount > 0 && next > availableEndDate.value.slice(0, 7)) return
  calendarCursor.value = next
}

function shiftYear(amount: number): void {
  const date = parseDate(`${calendarCursor.value}-01`)
  date.setFullYear(date.getFullYear() + amount)
  const next = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`
  if (amount > 0 && next > availableEndDate.value.slice(0, 7)) return
  calendarCursor.value = next
}

function updateStartDate(event: Event): void {
  emit("update:startDate", (event.target as HTMLInputElement).value)
}

function updateEndDate(event: Event): void {
  emit("update:endDate", (event.target as HTMLInputElement).value)
}

function submitCustomRange(): void {
  if (!props.startDate || !props.endDate || props.startDate > props.endDate) return
  emit("submit")
  dropdownOpen.value = false
}

const cursorDate = computed(() => parseDate(`${calendarCursor.value}-01`))
const cursorYear = computed(() => cursorDate.value.getFullYear())
const cursorMonth = computed(() => cursorDate.value.getMonth())
const cursorLabel = computed(() => `${cursorYear.value}年 ${cursorMonth.value + 1}月`)
const weekDays = ["一", "二", "三", "四", "五", "六", "日"]
const calendarCells = computed<CalendarCell[]>(() => {
  const firstDay = new Date(cursorYear.value, cursorMonth.value, 1)
  const offset = (firstDay.getDay() + 6) % 7
  const start = new Date(cursorYear.value, cursorMonth.value, 1 - offset)
  return Array.from({ length: 42 }, (_, index) => {
    const current = new Date(start)
    current.setDate(start.getDate() + index)
    const value = formatLocalDate(current)
    return {
      date: value,
      day: current.getDate(),
      inCurrentMonth: current.getMonth() === cursorMonth.value,
      disabled: Boolean(availableEndDate.value && value > availableEndDate.value),
    }
  })
})
const selectedRangeLabel = computed(() => props.startDate && props.endDate ? compactRange(props.startDate, props.endDate) : "等待选择")
const latestDataLabel = computed(() => availableEndDate.value ? shortDate(availableEndDate.value) : "--")
const dropdownTitle = computed(() => {
  if (rangeMode.value === "日") return "选择统计日期"
  if (rangeMode.value === "周") return "选择任意日期，按自然周汇总"
  if (rangeMode.value === "月") return "选择统计月份"
  if (rangeMode.value === "自定义") return "自定义统计范围"
  return "选择统计范围"
})

function isSelectedDay(value: string): boolean {
  if (rangeMode.value === "日") return value === props.endDate
  return value >= props.startDate && value <= props.endDate
}
</script>

<template>
  <section class="business-context-bar">
    <div class="store-context">
      <div class="store-icon"><ShoppingBag :size="18" /></div>
      <div><p>{{ props.store?.platform_name || "平台待配置" }} · 当前店铺</p><strong>{{ props.store?.store_name || "天猫历史经营库" }}</strong></div>
      <span class="readonly-badge"><Eye :size="13" /> 店铺ID {{ props.store?.store_id || "--" }}</span>
    </div>

    <form class="date-filter calendar-date-filter" aria-label="业务日期筛选" @submit.prevent="submitCustomRange" @click="dropdownOpen = false">
      <div class="context-query-heading"><CalendarDays :size="17" /><div><strong>统计范围</strong><span>{{ selectedRangeLabel }}</span></div><small>最新有效日 {{ latestDataLabel }}</small></div>

      <div class="range-picker-shell" @click.stop>
        <div class="range-segmented" role="tablist" aria-label="快捷时间范围">
          <button v-for="option in rangeOptions" :key="option" type="button" :class="{ active: rangeMode === option, expanded: dropdownOpen && rangeMode === option }" @click="selectRange(option)">{{ option }}</button>
        </div>

        <section v-if="dropdownOpen && !isDirectRange" class="range-dropdown" @click.stop>
          <div class="range-dropdown-heading"><div><strong>{{ dropdownTitle }}</strong><span>{{ rangeMode === "周" ? "选择后自动按周一至周日查询" : `最新可选 ${latestDataLabel}` }}</span></div><button class="dropdown-close" type="button" title="关闭日期选择" @click="dropdownOpen = false">×</button></div>
          <template v-if="isCalendarMode">
            <div class="calendar-toolbar"><button class="calendar-arrow" type="button" title="上个月" @click="shiftCursor(-1)"><ChevronLeft :size="16" /></button><strong>{{ cursorLabel }}</strong><button class="calendar-arrow" type="button" title="下个月" :disabled="calendarCursor >= availableEndDate.slice(0, 7)" @click="shiftCursor(1)"><ChevronRight :size="16" /></button></div>
            <div class="calendar-weekdays"><span v-for="day in weekDays" :key="day">{{ day }}</span></div>
            <div class="calendar-days"><button v-for="cell in calendarCells" :key="cell.date" type="button" :disabled="cell.disabled" :class="{ muted: !cell.inCurrentMonth, selected: isSelectedDay(cell.date), 'week-selected': rangeMode === '周' && isSelectedDay(cell.date) }" @click="chooseCalendarDay(cell.date)">{{ cell.day }}</button></div>
          </template>
          <template v-else-if="rangeMode === '月'">
            <div class="month-picker-header"><button class="calendar-arrow" type="button" title="上一年" @click="shiftYear(-1)"><ChevronLeft :size="15" /><ChevronLeft :size="15" class="double-arrow" /></button><strong>{{ cursorYear }}年</strong><button class="calendar-arrow" type="button" title="下一年" :disabled="cursorYear >= Number(availableEndDate.slice(0, 4))" @click="shiftYear(1)"><ChevronRight :size="15" /><ChevronRight :size="15" class="double-arrow" /></button></div>
            <div class="month-picker-grid"><button v-for="(month, index) in monthNames" :key="month" type="button" :disabled="`${cursorYear}-${String(index + 1).padStart(2, '0')}` > availableEndDate.slice(0, 7)" :class="{ active: calendarCursor === `${cursorYear}-${String(index + 1).padStart(2, '0')}` }" @click="chooseMonth(`${cursorYear}-${String(index + 1).padStart(2, '0')}`)">{{ month }}</button></div>
          </template>
          <div v-else class="dropdown-custom-fields">
            <label><span>开始日期</span><input :value="props.startDate" type="date" :max="props.endDate || availableEndDate || undefined" @input="updateStartDate" /></label>
            <label><span>结束日期</span><input :value="props.endDate" type="date" :min="props.startDate || undefined" :max="availableEndDate || undefined" @input="updateEndDate" /></label>
            <button class="range-apply" type="submit" :disabled="props.loading || !props.startDate || !props.endDate || props.startDate > props.endDate">应用筛选</button>
          </div>
        </section>
      </div>
      <span v-if="props.loading" class="sync-badge"><LoaderCircle :size="13" class="spinning" /> 正在更新</span>
    </form>
  </section>
</template>
