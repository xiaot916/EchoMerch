<script setup lang="ts">
import { ArrowRight, ClipboardCheck } from "lucide-vue-next"

import type { BusinessActionRow } from "@/lib/businessDecision"

withDefaults(defineProps<{
  rows: BusinessActionRow[]
  eyebrow?: string
  title?: string
  note?: string
  emptyText?: string
}>(), {
  eyebrow: "经营动作",
  title: "对象级行动清单",
  note: "按当前证据排序",
  emptyText: "当前筛选没有需要单列的经营动作。",
})
</script>

<template>
  <section class="panel business-action-panel">
    <div class="panel-heading">
      <div><p>{{ eyebrow }}</p><h2>{{ title }}</h2></div>
      <span class="panel-action">{{ note }}</span>
    </div>
    <div v-if="rows.length" class="business-action-table-wrap">
      <table class="business-action-table">
        <thead><tr><th>优先级 / 对象</th><th>问题与证据</th><th>已知影响量</th><th>建议动作</th><th>验证指标</th><th>观察窗口</th><th>下钻</th></tr></thead>
        <tbody>
          <tr v-for="item in rows" :key="item.id">
            <td><span class="business-priority" :class="item.priority.toLowerCase()">{{ item.priority }}</span><strong>{{ item.object }}</strong></td>
            <td><strong>{{ item.issue }}</strong><small>{{ item.evidence }}</small></td>
            <td><em :class="item.tone || 'stable'">{{ item.impact }}</em></td>
            <td>{{ item.action }}</td>
            <td>{{ item.validation }}</td>
            <td>{{ item.window }}</td>
            <td><RouterLink v-if="item.to" :to="item.to" :aria-label="`下钻查看${item.object}`"><ArrowRight :size="15" /></RouterLink><span v-else>--</span></td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else class="business-action-empty"><ClipboardCheck :size="18" /><span>{{ emptyText }}</span></div>
  </section>
</template>

<style scoped>
.business-action-panel { overflow: hidden; }
.business-action-table-wrap { overflow-x: auto; margin-top: 12px; }
.business-action-table { width: 100%; min-width: 1120px; border-collapse: collapse; table-layout: fixed; }
.business-action-table th, .business-action-table td { border-bottom: 1px solid #edf2ef; padding: 10px 9px; color: #61736a; font-size: 10px; line-height: 1.5; text-align: left; vertical-align: top; }.business-action-table th { color: #8b9991; background: #f8faf9; font-size: 9px; font-weight: 650; }.business-action-table th:nth-child(1) { width: 185px; }.business-action-table th:nth-child(2) { width: 235px; }.business-action-table th:nth-child(3) { width: 125px; }.business-action-table th:nth-child(4) { width: 210px; }.business-action-table th:nth-child(5) { width: 170px; }.business-action-table th:nth-child(6) { width: 90px; }.business-action-table th:nth-child(7) { width: 52px; text-align: center; }
.business-action-table td:first-child { display: grid; grid-template-columns: auto minmax(0, 1fr); align-items: start; gap: 7px; }.business-action-table td strong, .business-action-table td small { display: block; }.business-action-table td strong { color: #40564a; font-size: 10px; }.business-action-table td small { margin-top: 4px; color: #94a198; font-size: 8px; }.business-action-table td em { font-style: normal; font-weight: 700; }.business-action-table td em.risk { color: #b95d4c; }.business-action-table td em.warning { color: #a87328; }.business-action-table td em.opportunity { color: #147a56; }.business-action-table td em.stable { color: #57746a; }.business-action-table td:last-child { text-align: center; }.business-action-table a { display: inline-grid; width: 28px; height: 28px; place-items: center; border: 1px solid #cfe1d7; border-radius: 4px; color: #237b5a; background: #fff; }.business-action-table a:hover { border-color: #84bea1; background: #f2faf5; }
.business-priority { display: inline-flex; min-width: 28px; height: 20px; align-items: center; justify-content: center; border-radius: 3px; font-size: 8px; font-weight: 800; }.business-priority.p0 { color: #a94334; background: #fff0ed; }.business-priority.p1 { color: #96651c; background: #fff7e8; }.business-priority.p2 { color: #326b9a; background: #edf5fb; }
.business-action-empty { display: flex; min-height: 90px; align-items: center; justify-content: center; gap: 8px; color: #829188; font-size: 10px; }
</style>
