<script setup lang="ts">
import { useNavigationLoading } from "@/composables/useNavigationLoading"

const { isNavigating, progress } = useNavigationLoading()
</script>

<template>
  <div class="navigation-progress" :class="{ visible: isNavigating }" role="status" aria-live="polite" aria-label="正在切换页面">
    <span :style="{ width: `${progress}%` }" />
  </div>
</template>
