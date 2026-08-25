<script setup lang="ts">
import type { Component } from "vue"
import { Inbox } from "lucide-vue-next"

withDefaults(
  defineProps<{
    title: string
    detail: string
    icon?: Component
  }>(),
  {
    icon: () => Inbox,
  },
)
</script>

<template>
  <div class="empty-state">
    <component :is="icon" :size="22" />
    <strong>{{ title }}</strong>
    <span>{{ detail }}</span>
  </div>
</template>
