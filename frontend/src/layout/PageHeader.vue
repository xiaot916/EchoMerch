<script setup lang="ts">
import { computed, ref } from "vue"
import { ChevronDown, Eye, EyeOff, KeyRound, LoaderCircle, LogOut, PanelLeftClose, PanelLeftOpen, RefreshCw, ShieldCheck, UserRound, X } from "lucide-vue-next"
import { RouterLink, useRoute, useRouter } from "vue-router"

import { useAuth } from "@/composables/useAuth"

defineProps<{
  title: string
  eyebrow: string
  showBusinessContext: boolean
  loading: boolean
  sidebarCollapsed: boolean
}>()

const emit = defineEmits<{
  refresh: []
  "toggle-sidebar": []
}>()

const route = useRoute()
const router = useRouter()
const { currentUser, changePassword, signOut } = useAuth()
const accountOpen = ref(false)
const passwordDialogOpen = ref(false)
const currentPassword = ref("")
const newPassword = ref("")
const confirmPassword = ref("")
const currentPasswordVisible = ref(false)
const newPasswordVisible = ref(false)
const confirmPasswordVisible = ref(false)
const passwordSaving = ref(false)
const passwordError = ref("")
const accountInitial = computed(() => (currentUser.value?.display_name || "M").slice(0, 1).toUpperCase())
const accountRole = computed(() => {
  const role = currentUser.value?.roles[0]
  return ({
    super_admin: "超级管理员",
    admin: "管理员",
    operations_supervisor: "运营主管",
    store_manager: "运营店长",
    operator: "运营",
  } as Record<string, string>)[role || ""] || "已授权用户"
})

async function handleSignOut(): Promise<void> {
  accountOpen.value = false
  await signOut()
  await router.replace({ name: "login", query: { redirect: route.fullPath } })
}

function openPasswordDialog(): void {
  accountOpen.value = false
  currentPassword.value = ""
  newPassword.value = ""
  confirmPassword.value = ""
  currentPasswordVisible.value = false
  newPasswordVisible.value = false
  confirmPasswordVisible.value = false
  passwordError.value = ""
  passwordDialogOpen.value = true
}

function closePasswordDialog(): void {
  if (!passwordSaving.value) passwordDialogOpen.value = false
}

async function submitPasswordChange(): Promise<void> {
  passwordError.value = ""
  if (!currentPassword.value || !newPassword.value || !confirmPassword.value) {
    passwordError.value = "请完整填写当前密码、新密码和确认密码。"
    return
  }
  if (newPassword.value.length < 12) {
    passwordError.value = "新密码至少需要 12 位。"
    return
  }
  if (newPassword.value === currentPassword.value) {
    passwordError.value = "新密码不能与当前密码相同。"
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    passwordError.value = "两次输入的新密码不一致。"
    return
  }

  const redirectPath = route.fullPath
  passwordSaving.value = true
  try {
    await changePassword(currentPassword.value, newPassword.value)
    passwordDialogOpen.value = false
    await router.replace({ name: "login", query: { redirect: redirectPath } })
  } catch (error) {
    passwordError.value = error instanceof Error ? error.message : "密码修改失败，请稍后重试。"
  } finally {
    passwordSaving.value = false
  }
}
</script>

<template>
  <header class="topbar">
    <button class="header-nav-toggle" type="button" :title="sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'" @click="emit('toggle-sidebar')"><PanelLeftOpen v-if="sidebarCollapsed" :size="18" /><PanelLeftClose v-else :size="18" /></button>
    <div class="header-page-context">
      <strong>{{ title }}</strong>
      <span>{{ eyebrow }}</span>
    </div>
    <div class="top-actions">
      <button v-if="showBusinessContext" class="icon-button" title="刷新当前数据" :disabled="loading" @click="emit('refresh')">
        <RefreshCw :size="18" :class="{ spinning: loading }" />
      </button>
      <div v-if="currentUser" class="account-menu-wrapper" @keydown.escape="accountOpen = false">
        <button class="account-trigger" type="button" :aria-expanded="accountOpen" aria-label="打开账号菜单" @click="accountOpen = !accountOpen">
          <span class="account-avatar">{{ accountInitial }}</span>
          <span class="account-trigger-copy"><strong>{{ currentUser.display_name }}</strong><small>{{ accountRole }}</small></span>
          <ChevronDown :size="14" />
        </button>
        <div v-if="accountOpen" class="account-menu">
          <div class="account-menu-heading"><UserRound :size="16" /><div><strong>{{ currentUser.username }}</strong><span>{{ accountRole }}</span></div></div>
          <RouterLink v-if="currentUser.roles.includes('super_admin')" to="/system/users" class="account-menu-link" @click="accountOpen = false"><ShieldCheck :size="15" /><span>系统设置</span></RouterLink>
          <button class="account-menu-link" type="button" @click="openPasswordDialog"><KeyRound :size="15" /><span>修改密码</span></button>
          <button class="account-menu-link" type="button" @click="handleSignOut"><LogOut :size="15" /><span>退出登录</span></button>
        </div>
      </div>
    </div>
  </header>

  <Teleport to="body">
    <div v-if="passwordDialogOpen" class="password-dialog-backdrop" @click.self="closePasswordDialog" @keydown.esc.stop="closePasswordDialog">
      <section class="password-dialog" role="dialog" aria-modal="true" aria-labelledby="password-dialog-title">
        <header>
          <div class="password-dialog-title"><span><KeyRound :size="18" /></span><div><p>账号安全</p><h2 id="password-dialog-title">修改登录密码</h2></div></div>
          <button type="button" title="关闭" aria-label="关闭修改密码窗口" :disabled="passwordSaving" @click="closePasswordDialog"><X :size="18" /></button>
        </header>
        <form class="password-dialog-form" @submit.prevent="submitPasswordChange">
          <p class="password-dialog-note">修改成功后，当前账号的所有登录会话都会失效，需要使用新密码重新登录。</p>
          <label for="current-account-password"><span>当前密码</span><div class="password-input-shell"><KeyRound :size="16" /><input id="current-account-password" v-model="currentPassword" :type="currentPasswordVisible ? 'text' : 'password'" autocomplete="current-password" autofocus :disabled="passwordSaving" placeholder="请输入当前密码" /><button type="button" :disabled="passwordSaving" :title="currentPasswordVisible ? '隐藏密码' : '显示密码'" :aria-label="currentPasswordVisible ? '隐藏密码' : '显示密码'" @click="currentPasswordVisible = !currentPasswordVisible"><EyeOff v-if="currentPasswordVisible" :size="16" /><Eye v-else :size="16" /></button></div></label>
          <label for="new-account-password"><span>新密码</span><div class="password-input-shell"><KeyRound :size="16" /><input id="new-account-password" v-model="newPassword" :type="newPasswordVisible ? 'text' : 'password'" autocomplete="new-password" :disabled="passwordSaving" placeholder="至少 12 位" /><button type="button" :disabled="passwordSaving" :title="newPasswordVisible ? '隐藏密码' : '显示密码'" :aria-label="newPasswordVisible ? '隐藏密码' : '显示密码'" @click="newPasswordVisible = !newPasswordVisible"><EyeOff v-if="newPasswordVisible" :size="16" /><Eye v-else :size="16" /></button></div></label>
          <label for="confirm-account-password"><span>确认新密码</span><div class="password-input-shell"><KeyRound :size="16" /><input id="confirm-account-password" v-model="confirmPassword" :type="confirmPasswordVisible ? 'text' : 'password'" autocomplete="new-password" :disabled="passwordSaving" placeholder="再次输入新密码" /><button type="button" :disabled="passwordSaving" :title="confirmPasswordVisible ? '隐藏密码' : '显示密码'" :aria-label="confirmPasswordVisible ? '隐藏密码' : '显示密码'" @click="confirmPasswordVisible = !confirmPasswordVisible"><EyeOff v-if="confirmPasswordVisible" :size="16" /><Eye v-else :size="16" /></button></div></label>
          <p v-if="passwordError" class="password-dialog-error" role="alert">{{ passwordError }}</p>
          <footer><button class="password-dialog-cancel" type="button" :disabled="passwordSaving" @click="closePasswordDialog">取消</button><button class="password-dialog-submit" type="submit" :disabled="passwordSaving"><LoaderCircle v-if="passwordSaving" :size="16" class="spinning" /><KeyRound v-else :size="16" /><span>{{ passwordSaving ? "修改中" : "确认修改" }}</span></button></footer>
        </form>
      </section>
    </div>
  </Teleport>
</template>
