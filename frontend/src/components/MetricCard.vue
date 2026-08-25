<script setup lang="ts">
import { CircleHelp } from "lucide-vue-next"
import type { Component } from "vue"

defineProps<{
  label: string
  value: string
  detail: string
  icon: Component
  tone: "teal" | "blue" | "amber" | "coral"
  scope?: string
  definition?: string
}>()
</script>

<template>
  <article class="metric-card">
    <div class="metric-copy">
      <div class="metric-label-row">
        <p>{{ label }}</p>
        <span v-if="scope" class="metric-scope">{{ scope }}</span>
        <CircleHelp v-if="definition" class="metric-help" :size="14" :title="definition" />
      </div>
      <strong>{{ value }}</strong>
      <span>{{ detail }}</span>
    </div>
    <div class="metric-icon" :class="`tone-${tone}`">
      <component :is="icon" :size="21" stroke-width="1.9" />
    </div>
  </article>
</template>
