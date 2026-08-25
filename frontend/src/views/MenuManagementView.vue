<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { ChevronDown, ChevronRight, LoaderCircle, Menu, Search, ShieldCheck, X } from "lucide-vue-next"

import SystemAdminHeader from "@/components/SystemAdminHeader.vue"
import { useAccessDirectory } from "@/composables/useAccessDirectory"

type MenuRow = {
  id: string
  parentId: string | null
  name: string
  type: "目录" | "菜单"
  path: string
  component: string
  permission: string
  order: number
  hidden: boolean
  cached: boolean
  childrenCount: number
}

const nameDraft = ref("")
const pathDraft = ref("")
const typeDraft = ref("all")
const nameFilter = ref("")
const pathFilter = ref("")
const typeFilter = ref("all")
// Match the conventional admin tree layout: show root menus first, and let
// the operator expand only the branch they need.
const expandedDomains = ref(new Set<string>())
const selectedMenu = ref<MenuRow | null>(null)
const { directory, loading, error, loadAccessDirectory } = useAccessDirectory()
const directoryCount = computed(() => (directory.value?.menus || []).filter((menu) => !menu.parent_code).length)
const menuCount = computed(() => (directory.value?.menus || []).filter((menu) => menu.menu_type === "menu").length)
const permissionCount = computed(() => new Set(menuRows.value.map((row) => row.permission).filter(Boolean)).size)
const hiddenCount = computed(() => menuRows.value.filter((row) => row.hidden).length)

const menuRows = computed<MenuRow[]>(() => (directory.value?.menus || []).map((menu) => ({
  id: menu.code,
  parentId: menu.parent_code,
  name: menu.name,
  type: menu.menu_type === "catalog" ? "目录" : "菜单",
  path: menu.path,
  component: menu.component,
  permission: menu.permission || "",
  order: menu.order,
  hidden: menu.hidden,
  cached: menu.menu_type === "menu",
  childrenCount: (directory.value?.menus || []).filter((child) => child.parent_code === menu.code).length,
})))

const visibleRows = computed(() => {
  const name = nameFilter.value.trim().toLocaleLowerCase()
  const path = pathFilter.value.trim().toLocaleLowerCase()
  const matches = (row: MenuRow) => {
    const matchesName = !name || row.name.toLocaleLowerCase().includes(name)
    const matchesPath = !path || [row.path, row.permission].some((value) => value.toLocaleLowerCase().includes(path))
    const matchesType = typeFilter.value === "all" || row.type === typeFilter.value
    return matchesName && matchesPath && matchesType
  }

  const result: MenuRow[] = []
  for (const domainRow of menuRows.value.filter((row) => !row.parentId)) {
    const children = menuRows.value.filter((row) => row.parentId === domainRow.id)
    const matchedChildren = children.filter(matches)
    const domainMatches = matches(domainRow)
    if (!domainMatches && !matchedChildren.length) continue
    result.push(domainRow)
    const shouldShowChildren = name || path || typeFilter.value !== "all" || expandedDomains.value.has(domainRow.id)
    if (shouldShowChildren) result.push(...(domainMatches && !name && !path && typeFilter.value === "all" ? children : matchedChildren))
  }
  return result
})

function queryMenus(): void {
  nameFilter.value = nameDraft.value
  pathFilter.value = pathDraft.value
  typeFilter.value = typeDraft.value
}

function resetFilters(): void {
  nameDraft.value = ""
  pathDraft.value = ""
  typeDraft.value = "all"
  nameFilter.value = ""
  pathFilter.value = ""
  typeFilter.value = "all"
}

function toggleDomain(domainId: string): void {
  const next = new Set(expandedDomains.value)
  if (next.has(domainId)) next.delete(domainId)
  else next.add(domainId)
  expandedDomains.value = next
}

onMounted(() => { void loadAccessDirectory(true) })
</script>

<template>
  <section class="crud-page">
    <SystemAdminHeader title="菜单管理" description="查看后台菜单树、路由路径、权限标识以及页面缓存策略。" active="menus">
      <template #action><span class="crud-heading-badge"><Menu :size="15" />路由配置同步</span></template>
    </SystemAdminHeader>

    <p v-if="error" class="admin-inline-message error" role="alert">{{ error }}</p>
    <section v-if="loading" class="admin-loading-state"><LoaderCircle :size="22" class="spinning" />正在读取菜单目录</section>

    <template v-else-if="directory">
    <section class="system-admin-stats" aria-label="菜单目录摘要">
      <div><span>一级目录</span><strong>{{ directoryCount }}</strong><small>侧边栏业务分组</small></div>
      <div><span>可访问菜单</span><strong>{{ menuCount }}</strong><small>当前路由配置</small></div>
      <div><span>权限标识</span><strong>{{ permissionCount }}</strong><small>去重后统计</small></div>
      <div><span>隐藏菜单</span><strong>{{ hiddenCount }}</strong><small>当前无隐藏项</small></div>
    </section>

    <section class="crud-panel crud-filter-panel" aria-label="菜单查询">
      <div class="crud-filter-row crud-filter-row-menu">
        <label class="crud-filter-field">
          <span>菜单名称</span>
          <span class="crud-input-shell">
            <Search :size="15" />
            <input v-model="nameDraft" type="search" placeholder="请输入菜单名称" @keyup.enter="queryMenus" />
          </span>
        </label>
        <label class="crud-filter-field">
          <span>路径 / 权限</span>
          <input v-model="pathDraft" type="search" placeholder="请输入路由或权限标识" @keyup.enter="queryMenus" />
        </label>
        <label class="crud-filter-field crud-filter-field-compact">
          <span>菜单类型</span>
          <select v-model="typeDraft">
            <option value="all">全部类型</option>
            <option value="目录">目录</option>
            <option value="菜单">菜单</option>
          </select>
        </label>
        <div class="crud-filter-actions">
          <button class="crud-reset-button" type="button" @click="resetFilters">重置</button>
          <button class="crud-query-button" type="button" @click="queryMenus">查询</button>
        </div>
      </div>
    </section>

    <section class="crud-panel crud-table-panel">
      <header class="system-panel-heading"><div><h3>菜单树</h3><span>目录默认收起，查询时自动显示匹配的子菜单</span></div><span>{{ visibleRows.length }} 条</span></header>
      <div class="crud-table-scroll">
        <div class="crud-table crud-menu-table" role="table" aria-label="菜单列表">
          <div class="crud-table-row crud-table-head" role="row">
            <span>菜单名称</span>
            <span>菜单类型</span>
            <span>访问路径</span>
            <span>组件路径</span>
            <span>权限标识</span>
            <span>排序</span>
            <span>隐藏</span>
            <span>缓存</span>
            <span>操作</span>
          </div>
          <div
            v-for="row in visibleRows"
            :key="row.id"
            class="crud-table-row"
            :class="{ 'crud-menu-child-row': row.parentId }"
            role="row"
          >
            <div class="crud-menu-name">
              <button
                v-if="row.type === '目录'"
                type="button"
                :title="expandedDomains.has(row.id) ? '收起' : '展开'"
                @click="toggleDomain(row.id)"
              >
                <ChevronDown v-if="expandedDomains.has(row.id)" :size="15" />
                <ChevronRight v-else :size="15" />
              </button>
              <span v-else class="crud-menu-tree-line"></span>
              <strong>{{ row.name }}</strong>
            </div>
            <span class="crud-type-tag" :class="{ directory: row.type === '目录' }">{{ row.type }}</span>
            <code>{{ row.path }}</code>
            <span>{{ row.component }}</span>
            <code>{{ row.permission || "—" }}</code>
            <span>{{ row.order }}</span>
            <span class="crud-switch" :class="{ enabled: row.hidden }"><i></i></span>
            <span class="crud-switch" :class="{ enabled: row.cached }"><i></i></span>
            <div class="crud-actions">
              <button v-if="row.type === '目录'" class="crud-permission-button" type="button" @click="toggleDomain(row.id)">
                {{ expandedDomains.has(row.id) ? "收起" : "展开" }}
              </button>
              <button class="crud-edit-button" type="button" @click="selectedMenu = row">查看配置</button>
            </div>
          </div>
        </div>
      </div>
      <footer class="crud-table-footer">共 {{ visibleRows.length }} 条菜单记录</footer>
    </section>

    <div v-if="selectedMenu" class="access-drawer-backdrop" @click.self="selectedMenu = null">
      <aside class="access-drawer" role="dialog" aria-modal="true" aria-label="菜单配置">
        <header>
          <div><p>菜单配置</p><h3>{{ selectedMenu.name }}</h3></div>
          <button type="button" title="关闭" @click="selectedMenu = null"><X :size="18" /></button>
        </header>
        <div class="role-permission-drawer-body">
          <p class="crud-readonly-note">
            <ShieldCheck :size="15" />菜单由路由配置生成，服务端权限校验是最终访问边界。
          </p>
          <dl class="crud-detail-list">
            <div><dt>菜单类型</dt><dd>{{ selectedMenu.type }}</dd></div>
            <div><dt>访问路径</dt><dd><code>{{ selectedMenu.path }}</code></dd></div>
            <div><dt>组件路径</dt><dd>{{ selectedMenu.component }}</dd></div>
            <div><dt>权限标识</dt><dd><code>{{ selectedMenu.permission || "无" }}</code></dd></div>
            <div><dt>排序</dt><dd>{{ selectedMenu.order }}</dd></div>
            <div><dt>子菜单</dt><dd>{{ selectedMenu.childrenCount }}</dd></div>
          </dl>
        </div>
      </aside>
    </div>
    </template>
  </section>
</template>
