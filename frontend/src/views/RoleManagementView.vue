<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { Check, KeyRound, LoaderCircle, Save, Search, ShieldCheck, UsersRound } from "lucide-vue-next"

import SystemAdminHeader from "@/components/SystemAdminHeader.vue"
import { updateRoleAccess } from "@/api"
import { useAccessDirectory } from "@/composables/useAccessDirectory"

const { directory, loading, error, loadAccessDirectory } = useAccessDirectory()
const roleNameDraft = ref("")
const roleNameFilter = ref("")
const selectedRoleCode = ref<string | null>(null)
const activeTab = ref<"menus" | "permissions">("menus")
const selectedMenus = ref<string[]>([])
const selectedPermissions = ref<string[]>([])
const saving = ref(false)
const saveError = ref("")
const saveSuccess = ref("")

const filteredRoles = computed(() => {
  const query = roleNameFilter.value.trim().toLocaleLowerCase()
  if (!query) return directory.value?.roles || []
  return (directory.value?.roles || []).filter((role) =>
    [role.name, role.code, role.description].some((value) => value.toLocaleLowerCase().includes(query)),
  )
})
const selectedRole = computed(() => directory.value?.roles.find((role) => role.code === selectedRoleCode.value) || directory.value?.roles[0] || null)
const totalAssignments = computed(() => (directory.value?.users || []).reduce((total, user) => total + user.roles.length, 0))
const protectedRoleCount = computed(() => (directory.value?.roles || []).filter((role) => role.code === "super_admin").length)
const selectedIsSuperAdmin = computed(() => selectedRole.value?.code === "super_admin")
const menuRoots = computed(() => (directory.value?.menus || []).filter((menu) => !menu.parent_code))
const childrenOf = (code: string) => (directory.value?.menus || []).filter((menu) => menu.parent_code === code)

function roleUserCount(roleCode: string): number {
  return (directory.value?.users || []).filter((user) => user.roles.includes(roleCode)).length
}

function queryRoles(): void { roleNameFilter.value = roleNameDraft.value }
function resetFilters(): void { roleNameDraft.value = ""; roleNameFilter.value = "" }

function openRole(roleCode: string): void {
  selectedRoleCode.value = roleCode
  const role = directory.value?.roles.find((item) => item.code === roleCode)
  selectedMenus.value = [...(role?.menus || [])]
  selectedPermissions.value = [...(role?.permissions || [])]
  saveError.value = ""
  saveSuccess.value = ""
}

function isChecked(code: string): boolean { return selectedMenus.value.includes(code) }
function togglePermission(code: string): void {
  if (selectedIsSuperAdmin.value) return
  if (!selectedPermissions.value.includes(code)) {
    selectedPermissions.value = [...selectedPermissions.value, code]
    return
  }
  selectedPermissions.value = selectedPermissions.value.filter((item) => item !== code)
  const nextMenus = new Set(selectedMenus.value)
  for (const menu of directory.value?.menus || []) {
    if (menu.permission === code) nextMenus.delete(menu.code)
  }
  for (const root of menuRoots.value) {
    if (!childrenOf(root.code).some((child) => nextMenus.has(child.code))) nextMenus.delete(root.code)
  }
  selectedMenus.value = [...nextMenus]
}
function toggleMenu(code: string): void {
  if (selectedIsSuperAdmin.value) return
  const menu = directory.value?.menus.find((item) => item.code === code)
  if (!menu) return
  const next = new Set(selectedMenus.value)
  if (next.has(code)) next.delete(code)
  else next.add(code)
  if (menu.parent_code) {
    if (next.has(code)) next.add(menu.parent_code)
    else if (!childrenOf(menu.parent_code).some((item) => next.has(item.code))) next.delete(menu.parent_code)
  } else if (!next.has(code)) {
    for (const child of childrenOf(code)) next.delete(child.code)
  }
  if (next.has(code) && menu.permission && !selectedPermissions.value.includes(menu.permission)) {
    selectedPermissions.value = [...selectedPermissions.value, menu.permission]
  }
  selectedMenus.value = [...next]
}

async function saveAccess(): Promise<void> {
  if (!selectedRole.value || selectedIsSuperAdmin.value) return
  saving.value = true; saveError.value = ""; saveSuccess.value = ""
  try {
    const updated = await updateRoleAccess(selectedRole.value.code, {
      permission_codes: selectedPermissions.value,
      menu_codes: selectedMenus.value,
    })
    const role = directory.value?.roles.find((item) => item.code === updated.code)
    if (role) { role.permissions = updated.permissions; role.menus = updated.menus }
    selectedMenus.value = [...updated.menus]
    selectedPermissions.value = [...updated.permissions]
    saveSuccess.value = "权限已保存。"
  } catch (requestError) {
    saveError.value = requestError instanceof Error ? requestError.message : "角色权限保存失败。"
  } finally { saving.value = false }
}

onMounted(async () => {
  await loadAccessDirectory(true)
  if (directory.value?.roles[0]) openRole(directory.value.roles[0].code)
})
</script>

<template>
  <section class="crud-page">
    <SystemAdminHeader title="角色管理" description="分别配置菜单权限和功能权限；菜单由服务端目录统一管理。" active="roles">
      <template #action><span class="crud-heading-badge"><ShieldCheck :size="15" />角色授权</span></template>
    </SystemAdminHeader>
    <p v-if="error" class="admin-inline-message error" role="alert">{{ error }}</p>
    <p v-if="saveError" class="admin-inline-message error" role="alert">{{ saveError }}</p>
    <p v-if="saveSuccess" class="admin-inline-message success" role="status">{{ saveSuccess }}</p>
    <section v-if="loading" class="admin-loading-state"><LoaderCircle :size="22" class="spinning" />正在读取角色目录</section>
    <template v-else-if="directory">
      <section class="system-admin-stats" aria-label="角色权限摘要">
        <div><span>角色总数</span><strong>{{ directory.roles.length }}</strong><small>固定角色模型</small></div>
        <div><span>菜单目录</span><strong>{{ directory.menus.length }}</strong><small>服务端菜单授权</small></div>
        <div><span>角色分配</span><strong>{{ totalAssignments }}</strong><small>用户与角色关系</small></div>
        <div><span>超级管理员</span><strong>{{ protectedRoleCount }}</strong><small>不可修改</small></div>
      </section>
      <section class="crud-panel crud-filter-panel" aria-label="角色查询">
        <div class="crud-filter-row">
          <label class="crud-filter-field"><span>角色名称</span><span class="crud-input-shell"><Search :size="15" /><input v-model="roleNameDraft" type="search" placeholder="请输入角色名称、标识或说明" @keyup.enter="queryRoles" /></span></label>
          <div class="crud-filter-actions"><button class="crud-reset-button" type="button" @click="resetFilters">重置</button><button class="crud-query-button" type="button" @click="queryRoles">查询</button></div>
        </div>
      </section>
      <section class="role-workspace">
        <section class="crud-panel role-directory-panel">
          <header class="system-panel-heading"><div><h3>角色目录</h3><span>共 {{ filteredRoles.length }} 个角色</span></div></header>
          <div class="role-directory-list">
            <button v-for="role in filteredRoles" :key="role.code" type="button" :class="{ active: selectedRole?.code === role.code }" @click="openRole(role.code)">
              <span class="role-directory-icon"><ShieldCheck :size="16" /></span><span class="role-directory-copy"><strong>{{ role.name }}</strong><small>{{ role.code }}</small></span><span class="role-directory-meta"><b>{{ role.menus.length }}</b><small>菜单</small></span>
            </button>
          </div>
        </section>
        <section class="crud-panel role-permission-workspace">
          <header v-if="selectedRole" class="system-panel-heading role-workspace-heading"><div><h3>{{ selectedRole.name }}</h3><span>{{ selectedRole.description }}</span></div><span class="crud-built-in-tag">{{ selectedIsSuperAdmin ? "只读" : "可编辑" }}</span></header>
          <template v-if="selectedRole">
            <div class="role-workspace-summary"><span><UsersRound :size="15" /><b>{{ roleUserCount(selectedRole.code) }}</b> 个用户</span><span><KeyRound :size="15" /><b>{{ selectedPermissions.length }}</b> 个功能权限</span><code>{{ selectedRole.code }}</code></div>
            <div class="role-access-tabs"><button type="button" :class="{ active: activeTab === 'menus' }" @click="activeTab = 'menus'">菜单权限（{{ selectedMenus.length }}）</button><button type="button" :class="{ active: activeTab === 'permissions' }" @click="activeTab = 'permissions'">功能权限（{{ selectedPermissions.length }}）</button></div>
            <div v-if="activeTab === 'menus'" class="role-menu-tree">
              <article v-for="root in menuRoots" :key="root.code" class="role-menu-node">
                <label><input type="checkbox" :checked="isChecked(root.code)" :disabled="selectedIsSuperAdmin" @change="toggleMenu(root.code)" /><span><strong>{{ root.name }}</strong><small>{{ root.path }}</small></span></label>
                <label v-for="child in childrenOf(root.code)" :key="child.code" class="child"><input type="checkbox" :checked="isChecked(child.code)" :disabled="selectedIsSuperAdmin" @change="toggleMenu(child.code)" /><span><strong>{{ child.name }}</strong><small>{{ child.path }} · {{ child.permission || "无功能权限" }}</small></span></label>
              </article>
            </div>
            <div v-else class="role-permission-grid">
              <article v-for="permission in directory.permissions" :key="permission.code" :class="{ enabled: selectedPermissions.includes(permission.code) }" @click="togglePermission(permission.code)"><span class="role-permission-check"><Check v-if="selectedPermissions.includes(permission.code)" :size="14" /></span><div><strong>{{ permission.name }}</strong><small>{{ permission.description }}</small><code>{{ permission.code }}</code></div></article>
            </div>
            <footer v-if="!selectedIsSuperAdmin" class="role-access-actions"><button class="crud-primary-button" type="button" :disabled="saving" @click="saveAccess"><LoaderCircle v-if="saving" :size="15" class="spinning" /><Save v-else :size="15" />保存角色授权</button></footer>
          </template>
          <div v-else class="role-empty-selection"><ShieldCheck :size="24" /><strong>选择一个角色</strong><span>查看该角色的菜单和功能权限。</span></div>
        </section>
      </section>
    </template>
  </section>
</template>
