<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { ArrowRight, BarChart3, Bot, ChartNoAxesCombined, Eye, EyeOff, KeyRound, LoaderCircle, PackageSearch, UserRound } from "lucide-vue-next"
import { useRoute, useRouter } from "vue-router"

import { useAuth } from "@/composables/useAuth"

const route = useRoute()
const router = useRouter()
const { isAuthenticated, loading, loadSession, signIn } = useAuth()

const username = ref("")
const password = ref("")
const passwordVisible = ref(false)
const errorMessage = ref("")
const redirectPath = computed(() => {
  const requestedPath = typeof route.query.redirect === "string" ? route.query.redirect : "/"
  return requestedPath.startsWith("/") && !requestedPath.startsWith("//") ? requestedPath : "/"
})

async function leaveLogin(): Promise<void> {
  await router.replace(redirectPath.value)
}

async function submit(): Promise<void> {
  if (!username.value.trim() || !password.value) {
    errorMessage.value = "请输入用户名和密码。"
    return
  }
  errorMessage.value = ""
  try {
    await signIn(username.value, password.value)
    await leaveLogin()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "登录失败，请稍后重试。"
  }
}

onMounted(async () => {
  await loadSession()
  if (isAuthenticated.value) await leaveLogin()
})
</script>

<template>
  <main class="auth-page">
    <section class="auth-panel login-auth-panel" aria-labelledby="login-title">
      <aside class="auth-brand-panel">
        <div class="auth-brand">
          <div class="auth-brand-mark"><ChartNoAxesCombined :size="22" /></div>
          <div><strong>EchoMerch</strong><span>经营数据工作台</span></div>
        </div>
        <div class="auth-brand-copy">
          <p>OPERATIONS CONSOLE</p>
          <h2>让每一次经营决策，都有数据依据。</h2>
          <span>集中查看店铺表现、推广效率与商品结构，把数据直接转成清晰、可执行的经营动作。</span>
        </div>
        <div class="auth-capabilities" aria-label="工作台能力">
          <div><BarChart3 :size="17" /><span><strong>经营分析</strong><small>统一查看交易、流量与推广表现</small></span></div>
          <div><Bot :size="17" /><span><strong>AI 决策</strong><small>自动定位问题并生成可落地的运营方案</small></span></div>
          <div><PackageSearch :size="17" /><span><strong>商品与库存</strong><small>识别商品机会、缺货风险与补货重点</small></span></div>
        </div>
        <div class="auth-brand-footer"><span class="auth-brand-dot"></span><span>数据驱动 · 聚焦经营决策</span></div>
      </aside>

      <div class="auth-form-panel">
        <div class="auth-heading">
          <p>欢迎回来</p>
          <h1 id="login-title">登录工作台</h1>
          <span>登录 EchoMerch，进入你的经营数据工作台。</span>
        </div>

        <form class="auth-form" @submit.prevent="submit">
          <label for="login-username">
            <span>用户名</span>
            <div class="auth-input-shell"><UserRound :size="17" /><input id="login-username" v-model="username" autocomplete="username" autofocus :disabled="loading" placeholder="请输入用户名" /></div>
          </label>
          <label for="login-password">
            <span>密码</span>
            <div class="auth-input-shell"><KeyRound :size="17" /><input id="login-password" v-model="password" :type="passwordVisible ? 'text' : 'password'" autocomplete="current-password" :disabled="loading" placeholder="请输入密码" /><button class="auth-password-toggle" type="button" :disabled="loading" :aria-label="passwordVisible ? '隐藏密码' : '显示密码'" :title="passwordVisible ? '隐藏密码' : '显示密码'" @click="passwordVisible = !passwordVisible"><EyeOff v-if="passwordVisible" :size="17" /><Eye v-else :size="17" /></button></div>
          </label>
          <p v-if="errorMessage" class="auth-error" role="alert">{{ errorMessage }}</p>
          <button class="auth-submit" type="submit" :disabled="loading">
            <LoaderCircle v-if="loading" :size="17" class="spinning" />
            <span>{{ loading ? "正在验证" : "登录" }}</span>
            <ArrowRight v-if="!loading" :size="17" />
          </button>
          <p class="auth-form-note">登录后即可查看经营分析、AI 决策和业务数据。</p>
        </form>
      </div>
    </section>
  </main>
</template>
