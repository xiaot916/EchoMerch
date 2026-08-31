<script setup lang="ts">
import type { Component } from "vue"
import { Inbox } from "lucide-vue-next"

withDefaults(
  defineProps<{
    title: string
    detail: string
    icon?: Component
    actionLabel?: string
  }>(),
  {
    icon: () => Inbox,
  },
)

defineEmits<{
  action: []
}>()
</script>

<template>
  <div class="empty-state">
    <component :is="icon" :size="22" />
    <strong>{{ title }}</strong>
    <span>{{ detail }}</span>
    <button v-if="actionLabel" class="empty-state-action" type="button" @click="$emit('action')">{{ actionLabel }}</button>
  </div>
</template>
