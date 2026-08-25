<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import {
  Check,
  CircleAlert,
  KeyRound,
  LoaderCircle,
  Plus,
  Search,
  ShieldCheck,
  UsersRound,
  X,
} from "lucide-vue-next"

import {
  createAccessUser,
  fetchAccessDirectory,
  fetchBrandAssetsBrands,
  fetchStores,
  resetAccessUserPassword,
  updateAccessUser,
  updateAccessUserStatus,
} from "@/api"
import EmptyState from "@/components/EmptyState.vue"
import SystemAdminHeader from "@/components/SystemAdminHeader.vue"
import type { AccessDirectory, AccessUser, BrandRecord, StoreRecord } from "@/types"

type FormMode = "create" | "edit"

const directory = ref<AccessDirectory | null>(null)
const stores = ref<StoreRecord[]>([])
const brands = ref<BrandRecord[]>([])
const loading = ref(true)
const saving = ref(false)
const actionUserId = ref<number | null>(null)
const errorMessage = ref("")
const successMessage = ref("")
const searchText = ref("")
const selectedRoleFilter = ref("all")
const selectedStatusFilter = ref("all")
const appliedSearchText = ref("")
const appliedRoleFilter = ref("all")
const appliedStatusFilter = ref("all")

const drawerOpen = ref(false)
const formMode = ref<FormMode>("create")
const editingUser = ref<AccessUser | null>(null)
const username = ref("")
const displayName = ref("")
const selectedRoleCodes = ref<string[]>(["operator"])
const selectedStoreIds = ref<number[]>([])
const selectedBrandIds = ref<string[]>([])
const password = ref("")
const passwordConfirmation = ref("")
const resetPasswordOpen = ref(false)

const roleOptions = computed(() => directory.value?.roles || [])
const isSuperAdmin = computed(() => selectedRoleCodes.value.includes("super_admin"))
const availableRoleFilters = computed(() => roleOptions.value.filter((role) => directory.value?.users.some((user) => user.roles.includes(role.code))))
const activeUsers = computed(() => (directory.value?.users || []).filter((user) => user.is_active).length)
const adminUsers = computed(() => (directory.value?.users || []).filter((user) => user.roles.includes("super_admin") || user.roles.includes("admin")).length)
const scopedUsers = computed(() => (directory.value?.users || []).filter((user) => user.store_ids !== null || user.brand_ids !== null).length)
const neverLoggedInUsers = computed(() => (directory.value?.users || []).filter((user) => !user.last_login_at).length)

const filteredUsers = computed(() => {
  const query = appliedSearchText.value.trim().toLocaleLowerCase()
  return (directory.value?.users || []).filter((user) => {
    const matchesText = !query || [user.display_name, user.username].some((value) => value.toLocaleLowerCase().includes(query))
    const matchesRole = appliedRoleFilter.value === "all" || user.roles.includes(appliedRoleFilter.value)
    const matchesStatus = appliedStatusFilter.value === "all"
      || (appliedStatusFilter.value === "active" ? user.is_active : !user.is_active)
    return matchesText && matchesRole && matchesStatus
  })
})

watch(isSuperAdmin, (enabled) => {
  if (enabled) {
    selectedStoreIds.value = []
    selectedBrandIds.value = []
  }
})

function clearMessages(): void {
  errorMessage.value = ""
  successMessage.value = ""
}

function queryUsers(): void {
  appliedSearchText.value = searchText.value
  appliedRoleFilter.value = selectedRoleFilter.value
  appliedStatusFilter.value = selectedStatusFilter.value
}

function resetUserFilters(): void {
  searchText.value = ""
  selectedRoleFilter.value = "all"
  selectedStatusFilter.value = "all"
  queryUsers()
}

function resetForm(): void {
  username.value = ""
  displayName.value = ""
  selectedRoleCodes.value = ["operator"]
  selectedStoreIds.value = stores.value[0] ? [stores.value[0].store_id] : []
  selectedBrandIds.value = []
  password.value = ""
  passwordConfirmation.value = ""
  resetPasswordOpen.value = false
  editingUser.value = null
}

function roleName(code: string): string {
  return roleOptions.value.find((role) => role.code === code)?.name || code
}

function storeScope(user: AccessUser): string {
  if (user.store_ids === null) return "全部店铺"
  if (!user.store_ids.length) return "未授权"
  return user.store_ids.map((id) => stores.value.find((store) => store.store_id === id)?.store_name || `店铺 ${id}`).join("、")
}

function brandScope(user: AccessUser): string {
  if (user.brand_ids === null) return "全部品牌"
  if (!user.brand_ids.length) return "未授权品牌"
  return user.brand_ids.map((id) => brands.value.find((brand) => brand.brand_id === id)?.brand_name || `品牌 ${id}`).join("、")
}

function formatTime(value: string | null): string {
  if (!value) return "从未登录"
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value.slice(0, 10)
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(parsed)
}

function toggleRole(roleCode: string): void {
  if (selectedRoleCodes.value.includes(roleCode)) {
    if (selectedRoleCodes.value.length > 1) selectedRoleCodes.value = selectedRoleCodes.value.filter((code) => code !== roleCode)
    return
  }
  selectedRoleCodes.value = [...selectedRoleCodes.value, roleCode]
}

function toggleStore(storeId: number): void {
  selectedStoreIds.value = selectedStoreIds.value.includes(storeId)
    ? selectedStoreIds.value.filter((id) => id !== storeId)
    : [...selectedStoreIds.value, storeId]
}

function toggleBrand(brandId: string): void {
  selectedBrandIds.value = selectedBrandIds.value.includes(brandId)
    ? selectedBrandIds.value.filter((id) => id !== brandId)
    : [...selectedBrandIds.value, brandId]
}

async function load(): Promise<void> {
  loading.value = true
  clearMessages()
  try {
    ;[directory.value, stores.value, brands.value] = await Promise.all([fetchAccessDirectory(), fetchStores(), fetchBrandAssetsBrands()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "权限目录读取失败。"
  } finally {
    loading.value = false
  }
}

function openCreate(): void {
  clearMessages()
  formMode.value = "create"
  resetForm()
  drawerOpen.value = true
}

function openEdit(user: AccessUser): void {
  clearMessages()
  formMode.value = "edit"
  editingUser.value = user
  username.value = user.username
  displayName.value = user.display_name
  selectedRoleCodes.value = [...user.roles]
  selectedStoreIds.value = user.store_ids ? [...user.store_ids] : []
  selectedBrandIds.value = user.brand_ids ? [...user.brand_ids] : []
  password.value = ""
  passwordConfirmation.value = ""
  resetPasswordOpen.value = false
  drawerOpen.value = true
}

function closeDrawer(): void {
  if (saving.value) return
  drawerOpen.value = false
  resetForm()
}

function validateAssignment(): boolean {
  if (!displayName.value.trim() || !selectedRoleCodes.value.length) {
    errorMessage.value = "显示名称和至少一个角色为必填项。"
    return false
  }
  if (!isSuperAdmin.value && !selectedStoreIds.value.length && !selectedBrandIds.value.length) {
    errorMessage.value = "非超级管理员至少需要授权一个店铺或品牌。"
    return false
  }
  return true
}

async function submitUser(): Promise<void> {
  clearMessages()
  if (!validateAssignment()) return
  if (formMode.value === "create" && (username.value.trim().length < 2 || password.value.length < 6 || password.value !== passwordConfirmation.value)) {
    errorMessage.value = "请填写至少 2 个字符的用户名、至少 6 位初始密码，并确保两次密码一致。"
    return
  }
  const editingUserId = editingUser.value?.user_id
  if (formMode.value === "edit" && (editingUserId === null || editingUserId === undefined || !editingUser.value)) return

  saving.value = true
  try {
    const request = {
      display_name: displayName.value.trim(),
      role_codes: selectedRoleCodes.value,
      store_ids: isSuperAdmin.value ? [] : selectedStoreIds.value,
      brand_ids: isSuperAdmin.value ? [] : selectedBrandIds.value,
    }
    if (formMode.value === "create") {
      await createAccessUser({ username: username.value.trim(), password: password.value, ...request })
      successMessage.value = `账号 ${username.value.trim()} 已创建。`
    } else if (editingUser.value && editingUserId !== null && editingUserId !== undefined) {
      await updateAccessUser(editingUserId, request)
      successMessage.value = `账号 ${editingUser.value.display_name} 已更新。`
    }
    await load()
    drawerOpen.value = false
    resetForm()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "账号保存失败。"
  } finally {
    saving.value = false
  }
}

async function submitPasswordReset(): Promise<void> {
  clearMessages()
  if (!editingUser.value?.user_id || password.value.length < 12 || password.value !== passwordConfirmation.value) {
    errorMessage.value = "请输入至少 12 位的新密码，并确保两次密码一致。"
    return
  }
  saving.value = true
  try {
    await resetAccessUserPassword(editingUser.value.user_id, password.value)
    successMessage.value = `已重置 ${editingUser.value.display_name} 的密码，原会话已失效。`
    password.value = ""
    passwordConfirmation.value = ""
    resetPasswordOpen.value = false
    await load()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "密码重置失败。"
  } finally {
    saving.value = false
  }
}

async function toggleUserStatus(user: AccessUser): Promise<void> {
  if (!user.user_id) return
  clearMessages()
  actionUserId.value = user.user_id
  try {
    await updateAccessUserStatus(user.user_id, !user.is_active)
    successMessage.value = user.is_active ? `账号 ${user.display_name} 已停用，现有会话已失效。` : `账号 ${user.display_name} 已启用。`
    await load()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "账号状态更新失败。"
  } finally {
    actionUserId.value = null
  }
}

onMounted(() => { void load() })
</script>

<template>
  <section class="crud-page">
    <SystemAdminHeader title="用户管理" description="管理登录账号、角色授权以及店铺和品牌数据范围。" active="users">
      <template #action><button class="crud-primary-button" type="button" @click="openCreate"><Plus :size="16" />新增用户</button></template>
    </SystemAdminHeader>

    <p v-if="errorMessage" class="admin-inline-message error" role="alert"><CircleAlert :size="16" />{{ errorMessage }}</p>
    <p v-if="successMessage" class="admin-inline-message success" role="status"><Check :size="16" />{{ successMessage }}</p>

    <section v-if="loading" class="admin-loading-state"><LoaderCircle :size="22" class="spinning" /><span>正在读取用户目录</span></section>

    <template v-else-if="directory">
      <section class="system-admin-stats" aria-label="用户目录摘要">
        <div><span>账号总数</span><strong>{{ directory.users.length }}</strong><small>当前目录</small></div>
        <div><span>已启用</span><strong>{{ activeUsers }}</strong><small>可正常登录</small></div>
        <div><span>管理账号</span><strong>{{ adminUsers }}</strong><small>管理员 / 超级管理员</small></div>
        <div><span>数据范围账号</span><strong>{{ scopedUsers }}</strong><small>{{ neverLoggedInUsers }} 个从未登录</small></div>
      </section>
      <section class="crud-panel crud-filter-panel" aria-label="用户查询">
        <div class="crud-filter-row crud-filter-row-user">
          <label class="crud-filter-field">
            <span>用户名 / 显示名称</span>
            <span class="crud-input-shell"><Search :size="15" /><input v-model="searchText" type="search" placeholder="请输入用户名或显示名称" @keyup.enter="queryUsers" /></span>
          </label>
          <label class="crud-filter-field crud-filter-field-compact"><span>角色</span><select v-model="selectedRoleFilter" aria-label="按角色筛选"><option value="all">全部角色</option><option v-for="role in availableRoleFilters" :key="role.code" :value="role.code">{{ role.name }}</option></select></label>
          <label class="crud-filter-field crud-filter-field-compact"><span>状态</span><select v-model="selectedStatusFilter" aria-label="按状态筛选"><option value="all">全部状态</option><option value="active">启用</option><option value="inactive">停用</option></select></label>
          <div class="crud-filter-actions"><button class="crud-reset-button" type="button" @click="resetUserFilters">重置</button><button class="crud-query-button" type="button" @click="queryUsers">查询</button></div>
        </div>
      </section>

      <section class="crud-panel crud-table-panel">
        <header class="system-panel-heading"><div><h3>用户列表</h3><span>展示账号状态、角色和数据授权范围</span></div><span>{{ filteredUsers.length }} / {{ directory.users.length }} 条</span></header>
        <div v-if="filteredUsers.length" class="crud-table-scroll">
          <div class="crud-table crud-user-table" role="table" aria-label="用户目录">
            <div class="crud-table-row crud-table-head" role="row"><span>用户</span><span>角色</span><span>店铺 / 品牌范围</span><span>最近登录</span><span>状态</span><span>操作</span></div>
            <div v-for="user in filteredUsers" :key="user.user_id || user.username" class="crud-table-row" :class="{ inactive: !user.is_active }" role="row">
              <div class="crud-user-identity"><strong>{{ user.display_name }}</strong><small>{{ user.username }}</small></div>
              <div class="access-role-tags"><span v-for="role in user.roles" :key="role">{{ roleName(role) }}</span></div>
              <div class="crud-scope-cell"><span>{{ storeScope(user) }}</span><small>{{ brandScope(user) }}</small></div>
              <span class="access-login-time">{{ formatTime(user.last_login_at) }}</span>
              <span class="access-state" :class="user.is_active ? 'enabled' : 'disabled'"><i></i>{{ user.is_active ? "启用" : "停用" }}</span>
              <div class="crud-actions">
                <button class="crud-edit-button" type="button" :disabled="!user.user_id" @click="openEdit(user)">编辑</button>
                <button class="crud-permission-button" type="button" :disabled="!user.user_id" @click="openEdit(user); resetPasswordOpen = true">重置密码</button>
                <button class="crud-danger-button" type="button" :disabled="!user.user_id || actionUserId === user.user_id" @click="toggleUserStatus(user)">{{ user.is_active ? "停用" : "启用" }}</button>
              </div>
            </div>
          </div>
        </div>
        <EmptyState v-else title="没有匹配的用户" detail="调整筛选条件或新建一个用户。" :icon="UsersRound" />
        <footer class="crud-table-footer">共 {{ filteredUsers.length }} 条</footer>
      </section>
    </template>

    <div v-if="drawerOpen" class="access-drawer-backdrop" @click.self="closeDrawer"><aside class="access-drawer" role="dialog" aria-modal="true" :aria-label="formMode === 'create' ? '新增用户' : '编辑用户'"><header><div><p>{{ formMode === "create" ? "新增用户" : "编辑用户" }}</p><h3>{{ formMode === "create" ? "创建访问主体" : editingUser?.display_name }}</h3></div><button type="button" title="关闭" @click="closeDrawer"><X :size="18" /></button></header><form class="access-user-form" @submit.prevent="submitUser"><label><span>显示名称</span><input v-model="displayName" autocomplete="off" placeholder="例如：运营小王" /></label><label><span>用户名</span><input v-model="username" :disabled="formMode === 'edit'" autocomplete="off" placeholder="至少 2 个字符，用于登录" /></label><fieldset><legend>角色</legend><div class="access-choice-list"><label v-for="role in roleOptions" :key="role.code"><input type="checkbox" :checked="selectedRoleCodes.includes(role.code)" @change="toggleRole(role.code)" /><span><strong>{{ role.name }}</strong><small>{{ role.description }}</small></span></label></div></fieldset><fieldset v-if="!isSuperAdmin"><legend>授权店铺</legend><div class="access-choice-list stores"><label v-for="store in stores" :key="store.store_id"><input type="checkbox" :checked="selectedStoreIds.includes(store.store_id)" @change="toggleStore(store.store_id)" /><span><strong>{{ store.store_name }}</strong><small>{{ store.platform_name }} · ID {{ store.store_id }}</small></span></label></div></fieldset><fieldset v-if="!isSuperAdmin"><legend>授权品牌资产</legend><div v-if="brands.length" class="access-choice-list stores"><label v-for="brand in brands" :key="brand.brand_id"><input type="checkbox" :checked="selectedBrandIds.includes(brand.brand_id)" @change="toggleBrand(brand.brand_id)" /><span><strong>{{ brand.brand_name }}</strong><small>品牌主体 {{ brand.brand_subject_id }}</small></span></label></div><p v-else class="access-drawer-note">暂无品牌主体，导入数据银行品牌目录后可授权。</p></fieldset><p v-else class="access-drawer-note"><ShieldCheck :size="15" />超级管理员默认可访问全部店铺和品牌资产。</p><template v-if="formMode === 'create'"><label><span>初始密码</span><input v-model="password" type="password" autocomplete="new-password" placeholder="至少 6 位" /></label><label><span>确认密码</span><input v-model="passwordConfirmation" type="password" autocomplete="new-password" placeholder="再次输入初始密码" /></label></template><div v-else class="access-password-reset"><button type="button" class="access-reset-trigger" @click="resetPasswordOpen = !resetPasswordOpen"><KeyRound :size="15" />重置登录密码</button><template v-if="resetPasswordOpen"><label><span>新密码</span><input v-model="password" type="password" autocomplete="new-password" placeholder="至少 12 位" /></label><label><span>确认新密码</span><input v-model="passwordConfirmation" type="password" autocomplete="new-password" placeholder="再次输入新密码" /></label><button type="button" class="admin-secondary-button" :disabled="saving" @click="submitPasswordReset">{{ saving ? "重置中" : "确认重置密码" }}</button></template></div><footer><button type="button" class="admin-secondary-button" :disabled="saving" @click="closeDrawer">取消</button><button class="admin-primary-button" type="submit" :disabled="saving"><LoaderCircle v-if="saving" :size="15" class="spinning" /><Check v-else :size="15" />{{ saving ? "保存中" : formMode === "create" ? "创建用户" : "保存修改" }}</button></footer></form></aside></div>
  </section>
</template>
