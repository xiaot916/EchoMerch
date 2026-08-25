<script setup lang="ts">
import { Bell, KeyRound, Menu, Settings2, ShieldCheck, UsersRound } from "lucide-vue-next"
import { RouterLink } from "vue-router"

defineProps<{
  title: string
  description: string
  active: "users" | "roles" | "menus" | "apis" | "notifications" | "ai"
}>()

const tabs = [
  { key: "users" as const, label: "用户管理", to: "/system/users", icon: UsersRound },
  { key: "roles" as const, label: "角色管理", to: "/system/roles", icon: ShieldCheck },
  { key: "menus" as const, label: "菜单管理", to: "/system/menus", icon: Menu },
  { key: "apis" as const, label: "接口权限", to: "/system/apis", icon: KeyRound },
  { key: "notifications" as const, label: "消息通知", to: "/system/notifications", icon: Bell },
  { key: "ai" as const, label: "AI 配置", to: "/system/ai", icon: Settings2 },
]
</script>

<template>
  <header class="system-admin-header">
    <div class="system-admin-heading-row">
      <div class="system-admin-title-block">
        <p>系统管理 <span>/</span> 访问控制台</p>
        <h2>{{ title }}</h2>
        <span>{{ description }}</span>
      </div>
      <div class="system-admin-header-action">
        <slot name="action" />
      </div>
    </div>
    <nav class="system-admin-tabs" aria-label="系统管理模块">
      <RouterLink
        v-for="tab in tabs"
        :key="tab.key"
        :to="tab.to"
        class="system-admin-tab"
        :class="{ active: active === tab.key }"
      >
        <component :is="tab.icon" :size="15" />
        <span>{{ tab.label }}</span>
      </RouterLink>
    </nav>
  </header>
</template>
