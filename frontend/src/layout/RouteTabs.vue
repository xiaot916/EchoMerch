<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue"
import { X } from "lucide-vue-next"
import { useRoute, useRouter } from "vue-router"

import { useRouteTabs } from "@/composables/useRouteTabs"

const route = useRoute()
const router = useRouter()
const { tabs, syncCurrentRoute, closeTab, reloadTab, closeOtherTabs, closeTabsToSide } = useRouteTabs()
const activePath = computed(() => route.fullPath)
const contextMenu = ref<{ path: string; x: number; y: number } | null>(null)

watch(() => route.fullPath, () => syncCurrentRoute(route), { immediate: true })

function openContextMenu(event: MouseEvent, path: string): void {
  contextMenu.value = { path, x: event.clientX, y: event.clientY }
  void nextTick(() => {
    const menu = document.querySelector<HTMLElement>(".route-tab-context-menu")
    if (!menu) return
    contextMenu.value = {
      ...contextMenu.value!,
      x: Math.min(contextMenu.value!.x, window.innerWidth - menu.offsetWidth - 8),
      y: Math.min(contextMenu.value!.y, window.innerHeight - menu.offsetHeight - 8),
    }
  })
}

function closeContextMenu(): void { contextMenu.value = null }

async function runMenu(action: "reload" | "close" | "others" | "left" | "right"): Promise<void> {
  const path = contextMenu.value?.path
  if (!path) return
  closeContextMenu()
  if (action === "reload") await reloadTab(path, router)
  if (action === "close") await closeTab(path, router, activePath.value)
  if (action === "others") await closeOtherTabs(path, router, activePath.value)
  if (action === "left") await closeTabsToSide(path, "left", router, activePath.value)
  if (action === "right") await closeTabsToSide(path, "right", router, activePath.value)
}
</script>

<template>
  <nav class="route-tabs" aria-label="已打开页面" @click="closeContextMenu" @scroll="closeContextMenu">
    <RouterLink
      v-for="(tab, index) in tabs"
      :key="tab.path"
      :to="tab.path"
      class="route-tab"
      :class="{ active: tab.path === activePath }"
      @contextmenu.prevent.stop="openContextMenu($event, tab.path)"
    >
      <span>{{ tab.title }}</span>
      <button v-if="!tab.pinned" type="button" :title="`关闭 ${tab.title}`" @click.prevent.stop="closeTab(tab.path, router, activePath)"><X :size="13" /></button>
    </RouterLink>
    <div v-if="contextMenu" class="route-tab-context-menu" :style="{ left: `${contextMenu.x}px`, top: `${contextMenu.y}px` }" @click.stop>
      <button type="button" @click="runMenu('reload')">重新加载</button>
      <button v-if="contextMenu.path !== '/'" type="button" @click="runMenu('close')">关闭</button>
      <button type="button" @click="runMenu('others')">关闭其他</button>
      <button type="button" @click="runMenu('left')">关闭左侧</button>
      <button type="button" @click="runMenu('right')">关闭右侧</button>
    </div>
  </nav>
</template>
