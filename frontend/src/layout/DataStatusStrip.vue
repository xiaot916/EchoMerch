<script setup lang="ts">
import { computed } from "vue"
import { AlertTriangle, CheckCircle2, Database } from "lucide-vue-next"

import type { DashboardResponse } from "@/types"
import { shortDate } from "@/lib/format"

const props = defineProps<{
  dashboard: DashboardResponse
}>()

const primary = computed(() => props.dashboard.coverage.find((item) => item.dataset === "店铺日概览"))
const moduleRows = computed(() => props.dashboard.coverage.filter((item) => ["流量来源", "商品排行", "推广计划"].includes(item.dataset)))
const statusLabel = computed(() => primary.value?.status === "complete" ? "数据完整" : primary.value?.status === "partial" ? "部分缺失" : "暂无店铺数据")
</script>

<template>
  <section class="data-status-strip" aria-label="数据覆盖状态">
    <div class="data-status-main" :class="{ warning: primary?.status !== 'complete' }">
      <CheckCircle2 v-if="primary?.status === 'complete'" :size="17" /><AlertTriangle v-else :size="17" />
      <div><strong>{{ statusLabel }}</strong><small>统计 {{ dashboard.range_start }} 至 {{ dashboard.range_end }} · {{ primary?.covered_days || 0 }}/{{ primary?.expected_days || 0 }} 天</small></div>
    </div>
    <div v-for="item in moduleRows" :key="item.dataset" class="data-status-item" :class="{ 'is-muted': item.status !== 'complete' }">
      <span>{{ item.dataset }}</span><strong>{{ item.status === 'complete' ? '完整' : item.status === 'partial' ? `${item.covered_days}/${item.expected_days} 天` : '未入库' }}</strong><small>最新 {{ item.latest_date ? shortDate(item.latest_date) : '--' }}</small>
    </div>
    <div class="data-status-source"><Database :size="14" /><span>本地已入库 · 不补零</span></div>
  </section>
</template>
