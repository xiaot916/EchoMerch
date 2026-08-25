<script setup lang="ts">
import { onMounted, reactive, ref } from "vue"
import { Bot, CheckCircle2, CircleAlert, KeyRound, LoaderCircle, PlugZap, Save, ShieldCheck, Trash2 } from "lucide-vue-next"

import SystemAdminHeader from "@/components/SystemAdminHeader.vue"
import { fetchAIConfiguration, testAIConfiguration, updateAIConfiguration } from "@/api"
import type { AIConfiguration, AIConnectionTest } from "@/types"

const configuration = ref<AIConfiguration | null>(null)
const connection = ref<AIConnectionTest | null>(null)
const loading = ref(true)
const saving = ref(false)
const testing = ref(false)
const error = ref("")
const notice = ref("")
const apiKey = ref("")
const clearApiKey = ref(false)
const form = reactive({
  base_url: "https://apihub.agnes-ai.com",
  api_path: "/v1/chat/completions",
  model: "agnes-2.0-flash",
  timeout_seconds: 45,
})

function applyConfiguration(value: AIConfiguration): void {
  configuration.value = value
  form.base_url = value.base_url
  form.api_path = value.api_path
  form.model = value.model
  form.timeout_seconds = value.timeout_seconds
  apiKey.value = ""
  clearApiKey.value = false
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ""
  try {
    applyConfiguration(await fetchAIConfiguration())
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : "AI 配置暂不可用"
  } finally {
    loading.value = false
  }
}

async function save(): Promise<AIConfiguration | null> {
  if (!form.base_url.trim() || !form.api_path.trim() || !form.model.trim()) {
    error.value = "请填写服务地址、接口路径和模型名称。"
    return null
  }
  saving.value = true
  error.value = ""
  notice.value = ""
  connection.value = null
  try {
    const payload: Parameters<typeof updateAIConfiguration>[0] = {
      base_url: form.base_url.trim(),
      api_path: form.api_path.trim(),
      model: form.model.trim(),
      timeout_seconds: Number(form.timeout_seconds),
    }
    if (clearApiKey.value) payload.api_key = ""
    else if (apiKey.value.trim()) payload.api_key = apiKey.value.trim()
    const saved = await updateAIConfiguration(payload)
    applyConfiguration(saved)
    notice.value = "AI 配置已加密保存，并已立即应用到新的分析请求。"
    return saved
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : "AI 配置保存失败"
    return null
  } finally {
    saving.value = false
  }
}

async function testConnection(): Promise<void> {
  testing.value = true
  error.value = ""
  notice.value = ""
  connection.value = null
  try {
    connection.value = await testAIConfiguration()
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : "AI 连通性测试失败"
  } finally {
    testing.value = false
  }
}

onMounted(load)
</script>

<template>
  <SystemAdminHeader title="AI 配置" description="管理经营分析模型、加密凭据和运行时连通状态。" active="ai">
    <template #action>
      <button class="ai-config-test" type="button" :disabled="testing || loading" @click="testConnection">
        <LoaderCircle v-if="testing" :size="15" class="spinning" /><PlugZap v-else :size="15" />
        {{ testing ? "测试中" : "测试连通性" }}
      </button>
    </template>
  </SystemAdminHeader>

  <p v-if="error" class="admin-inline-message error" role="alert"><CircleAlert :size="16" />{{ error }}</p>
  <p v-if="notice" class="admin-inline-message success" role="status"><CheckCircle2 :size="16" />{{ notice }}</p>

  <section v-if="loading" class="admin-loading-state"><LoaderCircle :size="22" class="spinning" /><span>正在读取 AI 配置</span></section>
  <template v-else-if="configuration">
    <section class="system-admin-stats ai-config-stats" aria-label="AI 运行状态">
      <div><span>配置状态</span><strong>{{ configuration.api_key_configured ? "已就绪" : "未配置" }}</strong><small>{{ configuration.api_key_configured ? "Key 已加密保存" : "请求会回退规则引擎" }}</small></div>
      <div><span>当前模型</span><strong>{{ configuration.model }}</strong><small>用于经营结论自然语言生成</small></div>
      <div><span>接口协议</span><strong>Chat Completions</strong><small>{{ configuration.api_path }}</small></div>
      <div><span>请求超时</span><strong>{{ configuration.timeout_seconds }}s</strong><small>服务端最长等待时间</small></div>
    </section>

    <section class="ai-config-layout">
      <form class="panel ai-config-form" @submit.prevent="save">
        <div class="panel-heading"><div><p>运行参数</p><h2>模型服务配置</h2></div><Bot :size="18" /></div>
        <div class="ai-config-grid">
          <label class="wide"><span>服务地址</span><input v-model="form.base_url" spellcheck="false" placeholder="https://apihub.agnes-ai.com" /><small>不包含接口路径，保存时会自动移除末尾斜杠。</small></label>
          <label><span>接口路径</span><input v-model="form.api_path" spellcheck="false" placeholder="/v1/chat/completions" /></label>
          <label><span>模型名称</span><input v-model="form.model" spellcheck="false" placeholder="agnes-2.0-flash" /></label>
          <label><span>请求超时（秒）</span><input v-model.number="form.timeout_seconds" type="number" min="1" max="300" /></label>
          <label class="wide"><span>API Key</span><div class="ai-key-field"><KeyRound :size="15" /><input v-model="apiKey" type="password" autocomplete="new-password" :disabled="clearApiKey" :placeholder="configuration.api_key_configured ? '留空则保留当前 Key' : '输入 API Key'" /></div><small>当前：{{ configuration.api_key_masked || "未配置" }}。页面和接口都不会返回完整 Key。</small></label>
        </div>
        <label class="ai-clear-key"><input v-model="clearApiKey" type="checkbox" /><Trash2 :size="14" /><span>保存时清除当前 API Key</span></label>
        <div class="ai-config-actions"><span><ShieldCheck :size="14" />Key 使用当前 Windows 用户的 DPAPI 加密，仅本机后端可解密。</span><button type="submit" :disabled="saving"><LoaderCircle v-if="saving" :size="15" class="spinning" /><Save v-else :size="15" />{{ saving ? "保存中" : "保存配置" }}</button></div>
      </form>

      <article class="panel ai-config-status">
        <div class="panel-heading"><div><p>连接诊断</p><h2>真实模型请求</h2></div><PlugZap :size="18" /></div>
        <div v-if="connection" class="ai-connection-result" :class="connection.ok ? 'success' : 'failed'">
          <CheckCircle2 v-if="connection.ok" :size="24" /><CircleAlert v-else :size="24" />
          <div><strong>{{ connection.ok ? "模型连接成功" : "模型连接失败" }}</strong><span v-if="connection.ok">HTTP {{ connection.status_code }} · {{ connection.elapsed_ms }} ms · {{ connection.model }}</span><span v-else>{{ connection.error }}</span><small v-if="connection.ok && connection.reply">模型回复：{{ connection.reply }}</small></div>
        </div>
        <div v-else class="ai-connection-empty"><PlugZap :size="25" /><strong>尚未执行连接测试</strong><span>测试会向当前模型发送一个极短请求，用来确认地址、Key、模型名和返回格式均可用。</span></div>
        <dl class="ai-endpoint-summary"><div><dt>完整端点</dt><dd>{{ configuration.endpoint }}</dd></div><div><dt>凭据</dt><dd>{{ configuration.api_key_masked || "未配置" }}</dd></div><div><dt>生效方式</dt><dd>保存后立即生效，无需重启</dd></div></dl>
      </article>
    </section>
  </template>
</template>

<style scoped>
.ai-config-test { display:inline-flex; min-height:36px; align-items:center; gap:7px; border:1px solid #16845b; border-radius:5px; padding:0 13px; color:#fff; background:#16845b; font-size:11px; cursor:pointer }.ai-config-test:disabled{opacity:.55;cursor:not-allowed}.admin-inline-message{margin-top:14px}.ai-config-stats{margin-top:14px}.ai-config-stats strong{overflow:hidden;font-size:16px;text-overflow:ellipsis;white-space:nowrap}.ai-config-layout{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(320px,.65fr);gap:14px;margin-top:14px}.ai-config-form,.ai-config-status{min-width:0}.ai-config-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:13px;margin-top:15px}.ai-config-grid label{display:grid;gap:6px;color:#6f8077;font-size:10px}.ai-config-grid label.wide{grid-column:1/-1}.ai-config-grid input{width:100%;box-sizing:border-box;min-height:36px;border:1px solid #dbe5df;border-radius:5px;padding:0 10px;color:#354b3f;background:#fff;font-size:11px;outline:none}.ai-config-grid input:focus{border-color:#55a783;box-shadow:0 0 0 2px rgba(22,132,91,.08)}.ai-config-grid small{color:#98a49e;font-size:9px}.ai-key-field{display:flex;align-items:center;gap:7px;border:1px solid #dbe5df;border-radius:5px;padding:0 10px;color:#7c8c83;background:#fff}.ai-key-field input{border:0;padding:0;box-shadow:none!important}.ai-clear-key{display:inline-flex;align-items:center;gap:7px;margin-top:13px;color:#8b5a5a;font-size:10px}.ai-clear-key input{accent-color:#b44f4f}.ai-config-actions{display:flex;align-items:center;gap:12px;margin-top:16px;border-top:1px solid #edf2ef;padding-top:14px}.ai-config-actions>span{display:flex;align-items:center;gap:6px;margin-right:auto;color:#819088;font-size:9px}.ai-config-actions button{display:inline-flex;min-height:35px;align-items:center;gap:6px;border:1px solid #16845b;border-radius:5px;padding:0 14px;color:#fff;background:#16845b;font-size:11px;cursor:pointer}.ai-config-actions button:disabled{opacity:.55}.ai-connection-result{display:flex;align-items:flex-start;gap:10px;margin-top:15px;border:1px solid;border-radius:6px;padding:13px}.ai-connection-result.success{border-color:#bfe3cf;color:#14734f;background:#f2fbf6}.ai-connection-result.failed{border-color:#efcaca;color:#aa4141;background:#fff7f7}.ai-connection-result div{display:grid;gap:4px;min-width:0}.ai-connection-result strong{font-size:12px}.ai-connection-result span,.ai-connection-result small{overflow-wrap:anywhere;font-size:10px}.ai-connection-empty{display:grid;justify-items:center;gap:7px;margin-top:15px;border:1px dashed #dce6e0;border-radius:6px;padding:24px 14px;color:#85938b;text-align:center}.ai-connection-empty strong{color:#53675c;font-size:12px}.ai-connection-empty span{max-width:310px;font-size:10px;line-height:1.6}.ai-endpoint-summary{display:grid;gap:0;margin:15px 0 0}.ai-endpoint-summary div{display:grid;grid-template-columns:74px minmax(0,1fr);gap:8px;border-top:1px solid #edf2ef;padding:10px 0;font-size:10px}.ai-endpoint-summary dt{color:#8c9992}.ai-endpoint-summary dd{margin:0;overflow-wrap:anywhere;color:#50645a;text-align:right}@media(max-width:1000px){.ai-config-layout{grid-template-columns:1fr}}@media(max-width:680px){.ai-config-grid{grid-template-columns:1fr}.ai-config-grid label.wide{grid-column:auto}.ai-config-actions{align-items:flex-start;flex-direction:column}.ai-config-actions button{width:100%;justify-content:center}}
</style>
