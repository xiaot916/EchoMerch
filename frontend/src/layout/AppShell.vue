<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import { RouterLink, RouterView, useRoute } from "vue-router"
import { Bot, Database, LoaderCircle, MoreHorizontal, X } from "lucide-vue-next"

import { useDashboard } from "@/composables/useDashboard"
import { fetchStores } from "@/api"
import type { StoreRecord } from "@/types"
import BusinessContextBar from "@/layout/BusinessContextBar.vue"
import NavigationSidebar from "@/layout/NavigationSidebar.vue"
import PageHeader from "@/layout/PageHeader.vue"
import RouteTabs from "@/layout/RouteTabs.vue"
import { filterNavigation } from "@/layout/navigation"
import { useAuth } from "@/composables/useAuth"
import { usePageAI } from "@/composables/usePageAI"
import { useWorkspacePreferences } from "@/composables/useWorkspacePreferences"
import AIAssistantDrawer from "@/components/AIAssistantDrawer.vue"

const route = useRoute()
const { can, canMenu } = useAuth()
const { dashboard, loading, error, startDate, endDate, currentStoreId, ensureDashboard, loadDashboard } = useDashboard()
const stores = ref<StoreRecord[]>([])
const storesReady = ref(false)
const activeStore = computed(() => stores.value.find((item) => item.store_id === currentStoreId.value) || stores.value[0] || null)
const latestAvailableDate = computed(() => (dashboard.value?.freshness ?? []).reduce(
  (latest, item) => item.latest_date > latest ? item.latest_date : latest,
  dashboard.value?.range_end || "",
))

const pageTitle = computed(() => route.meta.title || "经营概览")
const pageEyebrow = computed(() => route.meta.eyebrow || "天猫经营数据")
const requiresDashboard = computed(() => route.meta.requiresDashboard !== false)
const visibleDomains = computed(() => filterNavigation(can, canMenu))
const mobileItems = computed(() => visibleDomains.value.flatMap((domain) => domain.items))
const mobileNavigation = computed(() => mobileItems.value.slice(0, 4))
const mobileMoreNavigation = computed(() => mobileItems.value.slice(4))

const showBusinessContext = computed(() => route.meta.surface === "business")
const mobileMenuOpen = ref(false)
const aiOpen = ref(false)
const aiRunQuestion = ref("")
const aiRunToken = ref(0)
const { sidebarCollapsed, toggleSidebar } = useWorkspacePreferences()
const { ensureProfiles, profileFor } = usePageAI()

const aiPageKey = computed(() => String(route.meta.aiPageKey || ""))
const aiProfile = computed(() => profileFor(aiPageKey.value))
const aiPageContext = computed(() => {
  return {
    page: pageTitle.value,
    route: route.fullPath,
    filters: { query: route.query, start_date: startDate.value, end_date: endDate.value },
  }
})

function loadCurrentDashboard(useFilter = false): Promise<void> {
  return loadDashboard(useFilter, activeStore.value?.store_id)
}

function ensureCurrentDashboard(): Promise<void> {
  return ensureDashboard(activeStore.value?.store_id)
}

function isMobileActive(path: string): boolean {
  return route.path === path || route.path.startsWith(`${path}/`)
}

function runPageDiagnosis(question: string): void {
  aiRunQuestion.value = question
  aiRunToken.value += 1
  aiOpen.value = true
}

function diagnoseCurrentPage(): void {
  runPageDiagnosis(
    aiProfile.value?.diagnostic_question ||
    "诊断当前页面，给出结果、原因、风险和可验证动作",
  )
}

onMounted(async () => {
  void ensureProfiles()
  try {
    stores.value = await fetchStores()
  } catch {
    stores.value = []
  } finally {
    storesReady.value = true
    currentStoreId.value = activeStore.value?.store_id ?? null
    if (showBusinessContext.value) void ensureCurrentDashboard()
  }
})

watch(showBusinessContext, (visible) => {
  if (visible && storesReady.value) void ensureCurrentDashboard()
}, { immediate: true })

watch(() => route.path, () => {
  mobileMenuOpen.value = false
  aiOpen.value = false
  aiRunQuestion.value = ""
})
</script>

<template>
  <main class="app-shell" :class="{ 'sidebar-is-collapsed': sidebarCollapsed }">
    <NavigationSidebar :collapsed="sidebarCollapsed" @toggle="toggleSidebar" />

    <section class="workspace">
      <PageHeader :title="pageTitle" :eyebrow="pageEyebrow" :show-business-context="showBusinessContext" :loading="loading" :sidebar-collapsed="sidebarCollapsed" @refresh="loadCurrentDashboard(true)" @toggle-sidebar="toggleSidebar" />
      <RouteTabs />

      <div class="content" :class="{ 'content-ai': route.name === 'ai' }">
        <BusinessContextBar
          v-if="showBusinessContext && route.name !== 'ai'"
          :store="activeStore"
          :start-date="startDate"
          :end-date="endDate"
          :latest-date="latestAvailableDate"
          :loading="loading"
          @update:start-date="startDate = $event"
          @update:end-date="endDate = $event"
          @submit="loadCurrentDashboard(true)"
        />

        <section class="page-outlet">
          <RouterView v-slot="{ Component, route: pageRoute }">
            <component :is="Component" :key="pageRoute.fullPath" />
          </RouterView>

          <div v-if="requiresDashboard && !dashboard && !error" class="page-state-overlay">
            <section class="loading-panel">
              <LoaderCircle :size="28" class="spinning" /><span>正在读取历史经营数据</span>
            </section>
          </div>

          <div v-else-if="requiresDashboard && error" class="page-state-overlay">
            <section class="error-panel">
              <Database :size="25" />
              <div><strong>数据源暂不可用</strong><p>{{ error }}</p></div>
              <button @click="loadCurrentDashboard(true)">重试</button>
            </section>
          </div>
        </section>
      </div>
    </section>

    <button v-if="aiProfile && ['analytics.read', 'brand_assets.read'].includes(String(route.meta.permission || ''))" class="ai-floating-button" title="诊断当前页面" aria-label="诊断当前页面" @click="diagnoseCurrentPage"><Bot :size="19" /><span>AI</span></button>
    <AIAssistantDrawer
      v-if="aiProfile"
      :open="aiOpen"
      :page-key="aiPageKey"
      :profile="aiProfile"
      :title="pageTitle"
      :store-id="activeStore?.store_id"
      :start-date="startDate"
      :end-date="endDate"
      :page-context="aiPageContext"
      :run-question="aiRunQuestion"
      :run-token="aiRunToken"
      @close="aiOpen = false"
    />

    <div v-if="mobileMenuOpen" class="mobile-more-menu">
      <div class="mobile-more-heading"><strong>更多页面</strong><button class="icon-button" title="关闭更多页面" @click="mobileMenuOpen = false"><X :size="17" /></button></div>
      <RouterLink v-for="item in mobileMoreNavigation" :key="item.to" :to="item.to" class="mobile-more-link">
        <component :is="item.icon" :size="17" /><span>{{ item.label }}</span><small v-if="item.note">{{ item.note }}</small>
      </RouterLink>
    </div>

    <nav class="mobile-nav" aria-label="移动端主导航">
      <RouterLink v-for="item in mobileNavigation" :key="item.to" :to="item.to" :class="{ active: isMobileActive(item.to) }">
        <component :is="item.icon" :size="18" /><span>{{ item.label }}</span>
      </RouterLink>
      <button v-if="mobileMoreNavigation.length" class="mobile-nav-more" :class="{ active: mobileMenuOpen || mobileMoreNavigation.some((item) => isMobileActive(item.to)) }" title="打开更多页面" @click="mobileMenuOpen = !mobileMenuOpen">
        <MoreHorizontal :size="18" /><span>更多</span>
      </button>
    </nav>
  </main>
</template>
