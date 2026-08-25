<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { ChevronDown, ChevronRight, PanelLeftClose, PanelLeftOpen } from "lucide-vue-next"
import { RouterLink, useRoute } from "vue-router"

import {
  activeNavigationItemForPath,
  brandIcon,
  filterNavigation,
  filterSidebarGroups,
  navigationDomainForPath,
} from "@/layout/navigation"
import { useAuth } from "@/composables/useAuth"

const EXPANDED_GROUPS_KEY = "echomerch.sidebar.expanded-groups"
const DEFAULT_EXPANDED_GROUPS = ["workbench"]

function readExpandedGroups(): string[] {
  if (typeof window === "undefined") return [...DEFAULT_EXPANDED_GROUPS]

  try {
    const saved = JSON.parse(window.localStorage.getItem(EXPANDED_GROUPS_KEY) || "[]")
    return Array.isArray(saved) && saved.every((key) => typeof key === "string")
      ? saved
      : [...DEFAULT_EXPANDED_GROUPS]
  } catch {
    return [...DEFAULT_EXPANDED_GROUPS]
  }
}

const route = useRoute()
const { can, canMenu } = useAuth()
const visibleDomains = computed(() => filterNavigation(can, canMenu))
const visibleGroups = computed(() => filterSidebarGroups(can, canMenu))
const activeDomain = computed(() => navigationDomainForPath(route.path, visibleDomains.value))
const activeGroup = computed(() => visibleGroups.value.find((group) => (
  group.domains.some((domain) => domain.key === activeDomain.value.key)
)))
const expandedGroups = ref<string[]>(readExpandedGroups())
const compactItems = computed(() => visibleGroups.value.flatMap((group) => group.domains.flatMap((domain) => domain.items)))

defineProps<{
  collapsed?: boolean
}>()

const emit = defineEmits<{
  toggle: []
}>()

watch(activeGroup, (group) => {
  if (group && !expandedGroups.value.includes(group.key)) {
    expandedGroups.value = [...expandedGroups.value, group.key]
  }
}, { immediate: true })

watch(expandedGroups, (value) => {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(EXPANDED_GROUPS_KEY, JSON.stringify(value))
  }
}, { deep: true })

function isExpanded(groupKey: string): boolean {
  return expandedGroups.value.includes(groupKey)
}

function toggleGroup(groupKey: string): void {
  expandedGroups.value = isExpanded(groupKey)
    ? expandedGroups.value.filter((key) => key !== groupKey)
    : [...expandedGroups.value, groupKey]
}

function isGroupActive(groupKey: string): boolean {
  return activeGroup.value?.key === groupKey
}

function isItemActive(path: string): boolean {
  return currentItem.value?.to === path
}

const currentItem = computed(() => activeNavigationItemForPath(route.path, compactItems.value))
</script>

<template>
  <aside class="primary-sidebar" :class="{ collapsed }">
    <RouterLink class="primary-brand" to="/" aria-label="EchoMerch 经营概览" title="EchoMerch 经营数据台">
      <div class="primary-brand-mark" aria-hidden="true"><component :is="brandIcon" :size="19" stroke-width="2.3" /></div>
      <span class="primary-brand-copy"><strong>EchoMerch</strong><small>经营数据台</small></span>
    </RouterLink>

    <nav v-if="!collapsed" class="grouped-sidebar-nav" aria-label="业务导航">
      <section v-for="group in visibleGroups" :key="group.key" class="sidebar-nav-group" :class="{ active: isGroupActive(group.key), expanded: isExpanded(group.key) }">
        <button
          class="sidebar-group-trigger"
          type="button"
          :aria-expanded="isExpanded(group.key)"
          @click="toggleGroup(group.key)"
        >
          <component :is="group.icon" :size="17" />
          <span>{{ group.label }}</span>
          <ChevronDown v-if="isExpanded(group.key)" class="sidebar-group-chevron" :size="16" />
          <ChevronRight v-else class="sidebar-group-chevron" :size="16" />
        </button>

        <div v-show="isExpanded(group.key)" class="sidebar-group-links">
          <template v-for="domain in group.domains" :key="domain.key">
            <RouterLink
              v-for="item in domain.items"
              :key="item.to"
              :to="item.to"
              class="sidebar-route-link"
              :class="{ active: currentItem?.to === item.to }"
            >
              <component :is="item.icon" :size="16" />
              <span>{{ item.label }}</span>
            </RouterLink>
          </template>
        </div>
      </section>
    </nav>

    <nav v-else class="sidebar-compact-navigation" aria-label="业务导航">
      <RouterLink
        v-for="item in compactItems"
        :key="item.to"
        :to="item.to"
        class="sidebar-compact-link"
        :class="{ active: isItemActive(item.to) }"
        :title="item.label"
      >
        <component :is="item.icon" :size="18" />
        <span class="visually-hidden">{{ item.label }}</span>
      </RouterLink>
    </nav>

    <div class="primary-sidebar-footer">
      <button class="sidebar-collapse-toggle" type="button" :title="collapsed ? '展开侧边栏' : '收起侧边栏'" @click="emit('toggle')">
        <PanelLeftOpen v-if="collapsed" :size="17" />
        <PanelLeftClose v-else :size="17" />
        <span v-if="!collapsed">收起菜单</span>
      </button>
    </div>
  </aside>
</template>
