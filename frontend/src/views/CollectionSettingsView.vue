<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { AlertTriangle, CheckCircle2, Eye, EyeOff, FileLock2, KeyRound, LoaderCircle, RefreshCw, Save, ShieldCheck } from "lucide-vue-next"

import { fetchCollectionSettings, testInventoryCredentials, updateInventoryCredentials } from "@/api"
import type { CollectionSettings, InventoryCredentialStatus } from "@/types"

const settings = ref<CollectionSettings | null>(null)
const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const error = ref("")
const notice = ref("")
const refreshToken = ref("")
const accessToken = ref("")
const showRefreshToken = ref(false)
const showAccessToken = ref(false)

const credentials = computed<InventoryCredentialStatus | null>(() => settings.value?.inventory_credentials || null)
const credentialLabel = computed(() => {
  switch (credentials.value?.status) {
    case "ready": return "可用"
    case "refresh_required": return "待刷新"
    case "invalid": return "凭证异常"
    default: return "未配置"
  }
})

async function load(): Promise<void> {
  loading.value = true
  error.value = ""
  try {
    settings.value = await fetchCollectionSettings()
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : "采集设置暂不可用"
  } finally {
    loading.value = false
  }
}

async function saveCredentials(): Promise<void> {
  if (!refreshToken.value.trim()) {
    error.value = "请填写新的 Refresh Token。"
    return
  }
  saving.value = true
  error.value = ""
  notice.value = ""
  try {
    const status = await updateInventoryCredentials({
      refresh_token: refreshToken.value.trim(),
      access_token: accessToken.value.trim() || null,
    })
    if (settings.value) settings.value.inventory_credentials = status
    refreshToken.value = ""
    accessToken.value = ""
    showRefreshToken.value = false
    showAccessToken.value = false
    notice.value = "凭证已安全保存。下一次库存采集会自动使用新的 Refresh Token。"
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : "凭证保存失败"
  } finally {
    saving.value = false
  }
}

async function validateCredentials(): Promise<void> {
  testing.value = true
  error.value = ""
  notice.value = ""
  try {
    const result = await testInventoryCredentials()
    if (settings.value) settings.value.inventory_credentials = result.credential_status
    notice.value = result.detail
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : "凭证验证失败"
  } finally {
    testing.value = false
  }
}

onMounted(() => { void load() })
</script>

<template>
  <section class="module-hero contract-hero">
    <div><p>采集节点与安全边界</p><h2>采集设置</h2><span>这里展示采集运行环境与安全边界；数据采集由后台 Worker 执行，页面不会保存或回显原始凭据。</span></div>
    <button class="capture-refresh" :disabled="loading" @click="load"><RefreshCw :size="16" :class="{ spinning: loading }" />刷新</button>
  </section>

  <section v-if="loading && !settings" class="loading-panel"><LoaderCircle :size="28" class="spinning" /><span>正在读取采集设置</span></section>
  <section v-else-if="error && !settings" class="error-panel"><FileLock2 :size="24" /><div><strong>采集设置不可用</strong><p>{{ error }}</p></div><button @click="load">重试</button></section>
  <template v-else-if="settings">
    <div v-if="error" class="collection-alert collection-alert-error"><AlertTriangle :size="16" /><span>{{ error }}</span></div>
    <div v-if="notice" class="collection-alert collection-context-note"><CheckCircle2 :size="16" /><span>{{ notice }}</span></div>

    <section class="architecture-metrics">
      <article class="panel capture-stat"><span>会话来源</span><strong>{{ settings.session_source === "drissionpage" ? "已登录采集浏览器" : "环境变量" }}</strong><small>平台登录态来源</small></article>
      <article class="panel capture-stat"><span>浏览器端口</span><strong>{{ settings.browser_port }}</strong><small>本地调试连接</small></article>
      <article class="panel capture-stat"><span>运行模式</span><strong>{{ settings.mode === "worker_enabled" ? "Worker 已启用" : settings.mode }}</strong><small>平台写操作保持关闭</small></article>
      <article class="panel capture-stat"><span>凭据变量</span><strong>{{ settings.cookie_env }}</strong><small>只读取变量名</small></article>
    </section>

    <section class="panel inventory-credential-panel">
      <div class="panel-heading"><div><p>吉客云库存采集</p><h2>凭证状态与手动刷新</h2></div><KeyRound :size="18" /></div>
      <div class="credential-status-row">
        <div class="credential-status-icon" :class="`status-${credentials?.status || 'not_configured'}`"><CheckCircle2 v-if="credentials?.status === 'ready'" :size="20" /><AlertTriangle v-else :size="20" /></div>
        <div><strong>{{ credentialLabel }}</strong><span>{{ credentials?.detail || "正在读取凭证状态。" }}</span></div>
        <small v-if="credentials?.updated_at">最近更新 {{ credentials.updated_at.replace("T", " ").replace(/\+.*$/, "") }}</small>
      </div>
      <div class="credential-facts">
        <span>Refresh Token：{{ credentials?.refresh_token_configured ? "已配置" : "未配置" }}</span>
        <span>Access Token：{{ credentials?.access_token_configured ? (credentials.access_token_expired ? "已过期" : "已配置") : "未缓存" }}</span>
        <span>来源：{{ credentials?.source === "environment" ? "环境变量" : credentials?.source === "vault" ? "加密凭证库" : "未配置" }}</span>
      </div>
      <form class="credential-form" @submit.prevent="saveCredentials">
        <label><span>新的 Refresh Token</span><div class="credential-input-shell"><KeyRound :size="15" /><input v-model="refreshToken" :type="showRefreshToken ? 'text' : 'password'" autocomplete="new-password" placeholder="粘贴后保存，不会回显旧值" :disabled="saving || testing" /><button type="button" :title="showRefreshToken ? '隐藏 Token' : '显示 Token'" :aria-label="showRefreshToken ? '隐藏 Token' : '显示 Token'" @click="showRefreshToken = !showRefreshToken"><EyeOff v-if="showRefreshToken" :size="15" /><Eye v-else :size="15" /></button></div></label>
        <label><span>可选 Access Token</span><div class="credential-input-shell"><KeyRound :size="15" /><input v-model="accessToken" :type="showAccessToken ? 'text' : 'password'" autocomplete="new-password" placeholder="通常留空，系统会自动刷新" :disabled="saving || testing" /><button type="button" :title="showAccessToken ? '隐藏 Token' : '显示 Token'" :aria-label="showAccessToken ? '隐藏 Token' : '显示 Token'" @click="showAccessToken = !showAccessToken"><EyeOff v-if="showAccessToken" :size="15" /><Eye v-else :size="15" /></button></div></label>
        <div class="credential-actions"><button type="submit" class="capture-refresh" :disabled="saving || testing"><LoaderCircle v-if="saving" :size="15" class="spinning" /><Save v-else :size="15" />{{ saving ? "保存中" : "保存凭证" }}</button><button type="button" class="capture-refresh secondary-action" :disabled="saving || testing || !credentials?.refresh_token_configured" @click="validateCredentials"><LoaderCircle v-if="testing" :size="15" class="spinning" /><RefreshCw v-else :size="15" />{{ testing ? "验证中" : "验证并刷新" }}</button></div>
      </form>
      <p class="credential-note">只显示状态，不回填或回显原始 Token。保存新 Refresh Token 后，旧 Access Token 会被清除；验证成功后库存采集会继续使用刷新后的凭证。</p>
    </section>

    <section class="panel architecture-panel"><div class="panel-heading"><div><p>安全规则</p><h2>采集执行边界</h2></div><ShieldCheck :size="18" /></div><div class="safety-list"><div v-for="(rule, index) in settings.safety_rules" :key="rule"><strong>{{ String(index + 1).padStart(2, "0") }}</strong><span>{{ rule }}</span></div></div></section>
  </template>
</template>

<style scoped>
.inventory-credential-panel { display: grid; gap: 14px; }
.credential-status-row { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 11px; border: 1px solid #e4ebe7; border-radius: 5px; padding: 12px 14px; background: #fbfdfc; }
.credential-status-icon { display: grid; width: 34px; height: 34px; place-items: center; border-radius: 50%; }
.credential-status-icon.status-ready { color: #19734a; background: #eff9f2; }
.credential-status-icon.status-refresh_required { color: #956a1d; background: #fff9e9; }
.credential-status-icon.status-invalid { color: #b24f4f; background: #fff3f3; }
.credential-status-icon.status-not_configured { color: #6e7d75; background: #f1f5f3; }
.credential-status-row strong, .credential-status-row span, .credential-status-row small { display: block; }
.credential-status-row span, .credential-status-row small { margin-top: 3px; color: var(--text-muted); font-size: 11px; line-height: 1.45; }
.credential-status-row small { margin-top: 0; text-align: right; white-space: nowrap; }
.credential-facts { display: flex; flex-wrap: wrap; gap: 7px 18px; color: var(--text-muted); font-size: 11px; }
.credential-form { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto; align-items: end; gap: 10px; }
.credential-form label { display: grid; gap: 5px; min-width: 0; }
.credential-form label > span { color: var(--text-muted); font-size: 11px; }
.credential-input-shell { display: flex; min-height: 36px; align-items: center; gap: 7px; border: 1px solid var(--line); border-radius: 4px; padding-left: 9px; color: #98a2b3; background: #fff; }
.credential-input-shell:focus-within { border-color: #6c8fea; box-shadow: 0 0 0 3px rgba(83, 120, 225, .12); }
.credential-input-shell input { min-width: 0; min-height: 34px; flex: 1; border: 0; outline: 0; color: var(--text); background: transparent; font-size: 12px; }
.credential-input-shell button { display: grid; width: 34px; height: 34px; place-items: center; border: 0; color: #98a2b3; background: transparent; }
.credential-input-shell button:hover { color: var(--accent); }
.credential-actions { display: flex; align-items: center; gap: 7px; }
.credential-actions .capture-refresh { white-space: nowrap; }
.credential-note { margin: 0; color: var(--text-muted); font-size: 10px; line-height: 1.6; }
.collection-alert-error { border-color: #efccc6; color: #b64d3e; background: #fff1ef; }
@media (max-width: 900px) { .credential-form { grid-template-columns: 1fr 1fr; } .credential-actions { grid-column: 1 / -1; } }
@media (max-width: 620px) { .credential-status-row { grid-template-columns: auto minmax(0, 1fr); } .credential-status-row small { grid-column: 2; text-align: left; } .credential-form { grid-template-columns: 1fr; } .credential-actions { grid-column: auto; flex-wrap: wrap; } }
</style>
