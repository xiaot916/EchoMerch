import { computed, ref } from "vue"

import {
  changeCurrentPassword,
  fetchAuthConfiguration,
  fetchCurrentUser,
  login as loginRequest,
  logout as logoutRequest,
} from "@/api"
import type { AccessUser, AuthConfiguration } from "@/types"

const configuration = ref<AuthConfiguration | null>(null)
const currentUser = ref<AccessUser | null>(null)
const loading = ref(false)
let initialized = false
let initialRequest: Promise<void> | null = null
let sessionRevision = 0

async function loadSession(force = false): Promise<void> {
  if (initialized && !force) return
  // A refresh already in flight is enough for concurrent callers. Starting a
  // second request here would let the slower response overwrite newer state.
  if (initialRequest) return initialRequest

  const requestRevision = sessionRevision
  const request = (async () => {
    loading.value = true
    try {
      const nextConfiguration = await fetchAuthConfiguration()
      if (requestRevision === sessionRevision) {
        configuration.value = nextConfiguration
      }
      const nextUser = await fetchCurrentUser()
      if (requestRevision === sessionRevision) {
        currentUser.value = nextUser
      }
    } catch {
      if (requestRevision === sessionRevision) {
        currentUser.value = null
      }
    } finally {
      initialRequest = null
      if (requestRevision === sessionRevision) {
        initialized = true
        loading.value = false
      }
    }
  })()
  initialRequest = request
  return request
}

export function useAuth() {
  async function signIn(username: string, password: string): Promise<void> {
    // Invalidate any session probe that started before this login attempt.
    sessionRevision += 1
    loading.value = true
    try {
      currentUser.value = await loginRequest(username, password)
      initialized = true
      if (!configuration.value) configuration.value = await fetchAuthConfiguration()
    } finally {
      loading.value = false
    }
  }

  async function signOut(): Promise<void> {
    sessionRevision += 1
    try {
      await logoutRequest()
    } finally {
      currentUser.value = null
      initialized = true
    }
  }

  async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
    sessionRevision += 1
    loading.value = true
    try {
      await changeCurrentPassword(currentPassword, newPassword)
      currentUser.value = null
      initialized = true
    } finally {
      loading.value = false
    }
  }

  function can(permission?: string): boolean {
    if (!permission) return true
    const user = currentUser.value
    return Boolean(user && (user.roles.includes("super_admin") || user.permissions.includes(permission)))
  }

  function canMenu(menuCode?: string): boolean {
    if (!menuCode) return true
    const user = currentUser.value
    return Boolean(user && (user.roles.includes("super_admin") || user.menus.includes(menuCode)))
  }

  return {
    configuration,
    currentUser,
    loading,
    // Fail closed while configuration is loading or unavailable.
    authenticationEnabled: computed(() => configuration.value?.enabled ?? true),
    isAuthenticated: computed(() => currentUser.value !== null),
    loadSession,
    signIn,
    signOut,
    changePassword,
    can,
    canMenu,
  }
}
