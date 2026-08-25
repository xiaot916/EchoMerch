<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue"
import { BellRing, CheckCircle2, CircleAlert, LoaderCircle, Pencil, Plus, RefreshCw, Send, ShieldCheck, XCircle } from "lucide-vue-next"

import {
  createNotificationChannel,
  fetchNotificationChannels,
  fetchNotificationDeliveries,
  sendNotification,
  updateNotificationChannel,
} from "@/api"
import type { NotificationChannel, NotificationDelivery } from "@/types"
import SystemAdminHeader from "@/components/SystemAdminHeader.vue"

const channels = ref<NotificationChannel[]>([])
const deliveries = ref<NotificationDelivery[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const saving = ref(false)
const sending = ref(false)
const error = ref("")
const notice = ref("")
const editingId = ref<number | null>(null)
const selectedChannelId = ref<number | null>(null)

const channelForm = reactive({
  name: "运营通知群",
  webhook_env: "ECHOMERCH_DINGTALK_WEBHOOK",
  secret_env: "ECHOMERCH_DINGTALK_SECRET",
  enabled: true,
})
const messageForm = reactive({
  message_type: "markdown" as "text" | "markdown",
  title: "EchoMerch 经营通知",
  content: "",
  at_all: false,
})

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))
const selectedChannel = computed(() => channels.value.find((item) => item.channel_id === selectedChannelId.value) ?? null)
const visiblePages = computed(() => {
  const start = Math.max(1, Math.min(page.value - 2, pageCount.value - 4))
  return Array.from({ length: Math.min(5, pageCount.value) }, (_, index) => start + index)
})

function formatTime(value: string | null): string {
  if (!value) return "--"
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false })
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ""
  try {
    const [channelRows, history] = await Promise.all([
      fetchNotificationChannels(),
      fetchNotificationDeliveries(page.value, pageSize.value),
    ])
    channels.value = channelRows
    deliveries.value = history.items
    total.value = history.total
    if (!selectedChannelId.value && channelRows.length) selectedChannelId.value = channelRows[0].channel_id
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : "消息通知暂不可用"
  } finally {
    loading.value = false
  }
}

function resetChannelForm(): void {
  editingId.value = null
  channelForm.name = "运营通知群"
  channelForm.webhook_env = "ECHOMERCH_DINGTALK_WEBHOOK"
  channelForm.secret_env = "ECHOMERCH_DINGTALK_SECRET"
  channelForm.enabled = true
}

function editChannel(channel: NotificationChannel): void {
  editingId.value = channel.channel_id
  channelForm.name = channel.name
  channelForm.webhook_env = channel.webhook_env
  channelForm.secret_env = channel.secret_env || ""
  channelForm.enabled = channel.enabled
}

async function saveChannel(): Promise<void> {
  if (!channelForm.name.trim() || !channelForm.webhook_env.trim()) {
    error.value = "请填写渠道名称和 Webhook 环境变量名。"
    return
  }
  saving.value = true
  error.value = ""
  notice.value = ""
  const payload = {
    name: channelForm.name.trim(),
    provider: "dingtalk" as const,
    webhook_env: channelForm.webhook_env.trim(),
    secret_env: channelForm.secret_env.trim() || null,
    enabled: channelForm.enabled,
  }
  try {
    const saved = editingId.value
      ? await updateNotificationChannel(editingId.value, payload)
      : await createNotificationChannel(payload)
    selectedChannelId.value = saved.channel_id
    notice.value = editingId.value ? "通知渠道已更新。" : "通知渠道已创建。"
    resetChannelForm()
    await load()
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : "渠道保存失败"
  } finally {
    saving.value = false
  }
}

async function submitMessage(): Promise<void> {
  if (!selectedChannelId.value || !messageForm.content.trim()) {
    error.value = "请选择通知渠道并填写消息内容。"
    return
  }
  const target = selectedChannel.value?.name || "所选群"
  if (!window.confirm(`确认把这条消息真实发送到“${target}”吗？`)) return
  sending.value = true
  error.value = ""
  notice.value = ""
  try {
    const result = await sendNotification({
      channel_id: selectedChannelId.value,
      message_type: messageForm.message_type,
      title: messageForm.title.trim() || "EchoMerch 通知",
      content: messageForm.content.trim(),
      at_all: messageForm.at_all,
      idempotency_key: crypto.randomUUID(),
    })
    if (result.status === "sent") {
      notice.value = "消息已发送，钉钉返回成功。"
      messageForm.content = ""
    } else {
      error.value = result.provider_message || "消息发送失败，已写入发送记录。"
    }
    page.value = 1
    await load()
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : "消息发送失败"
  } finally {
    sending.value = false
  }
}

function setPage(value: number): void {
  page.value = Math.max(1, Math.min(value, pageCount.value))
  void load()
}

watch(pageSize, () => { page.value = 1; void load() })
onMounted(() => { void load() })
</script>

<template>
  <SystemAdminHeader title="消息通知" description="统一管理群机器人，让采集、评价预警和经营任务复用同一套通知能力。" active="notifications">
    <template #action><button class="crud-refresh-button" :disabled="loading" @click="load"><RefreshCw :size="15" :class="{ spinning: loading }" />刷新通知</button></template>
  </SystemAdminHeader>

  <div v-if="notice" class="notification-banner success"><CheckCircle2 :size="17" />{{ notice }}</div>
  <div v-if="error" class="notification-banner error"><CircleAlert :size="17" />{{ error }}</div>

  <section class="notification-layout">
    <article class="panel notification-channel-panel">
      <div class="panel-heading"><div><p>渠道配置</p><h2>钉钉机器人</h2></div><ShieldCheck :size="18" /></div>
      <p class="notification-safe-note">这里只保存环境变量名，不保存或回显 Webhook 与签名密钥。</p>
      <div v-if="channels.length" class="notification-channel-list">
        <button v-for="channel in channels" :key="channel.channel_id" type="button" :class="{ active: selectedChannelId === channel.channel_id }" @click="selectedChannelId = channel.channel_id">
          <span class="channel-icon"><BellRing :size="16" /></span>
          <span><strong>{{ channel.name }}</strong><small>{{ channel.webhook_configured ? "Webhook 已就绪" : "Webhook 未配置" }} · {{ channel.enabled ? "已启用" : "已停用" }}</small></span>
          <em :class="channel.webhook_configured && channel.enabled ? 'ready' : 'pending'">{{ channel.webhook_configured && channel.enabled ? "可发送" : "待配置" }}</em>
          <i title="编辑" @click.stop="editChannel(channel)"><Pencil :size="13" /></i>
        </button>
      </div>
      <div v-else class="notification-empty"><BellRing :size="22" /><span>还没有通知渠道，请先创建一个。</span></div>

      <form class="notification-channel-form" @submit.prevent="saveChannel">
        <div class="notification-form-title"><strong>{{ editingId ? "编辑渠道" : "新增渠道" }}</strong><button v-if="editingId" type="button" @click="resetChannelForm">取消编辑</button></div>
        <label><span>渠道名称</span><input v-model="channelForm.name" maxlength="80" placeholder="例如：运营通知群" /></label>
        <label><span>Webhook 环境变量名</span><input v-model="channelForm.webhook_env" spellcheck="false" placeholder="ECHOMERCH_DINGTALK_WEBHOOK" /></label>
        <label><span>签名密钥环境变量名</span><input v-model="channelForm.secret_env" spellcheck="false" placeholder="ECHOMERCH_DINGTALK_SECRET" /></label>
        <label class="notification-check"><input v-model="channelForm.enabled" type="checkbox" /><span>启用此渠道</span></label>
        <button class="notification-primary" type="submit" :disabled="saving"><LoaderCircle v-if="saving" :size="15" class="spinning" /><Plus v-else :size="15" />{{ saving ? "保存中" : editingId ? "保存修改" : "创建渠道" }}</button>
      </form>
    </article>

    <article class="panel notification-compose-panel">
      <div class="panel-heading"><div><p>手动发送</p><h2>消息编辑器</h2></div><Send :size="18" /></div>
      <div class="notification-compose-grid">
        <label><span>发送渠道</span><select v-model="selectedChannelId"><option :value="null" disabled>请选择渠道</option><option v-for="channel in channels" :key="channel.channel_id" :value="channel.channel_id" :disabled="!channel.enabled">{{ channel.name }}</option></select></label>
        <label><span>消息类型</span><select v-model="messageForm.message_type"><option value="markdown">Markdown</option><option value="text">纯文本</option></select></label>
      </div>
      <label class="notification-field"><span>标题</span><input v-model="messageForm.title" maxlength="120" placeholder="消息标题" /></label>
      <label class="notification-field"><span>消息内容</span><textarea v-model="messageForm.content" rows="9" :placeholder="messageForm.message_type === 'markdown' ? '支持 Markdown，例如：## 昨日经营提醒' : '请输入要发送到群里的文本'"></textarea></label>
      <div class="notification-send-row">
        <label class="notification-check"><input v-model="messageForm.at_all" type="checkbox" /><span>@ 所有人</span></label>
        <span>点击发送后还会再次确认，不会静默发送。</span>
        <button class="notification-primary" type="button" :disabled="sending || !selectedChannelId" @click="submitMessage"><LoaderCircle v-if="sending" :size="15" class="spinning" /><Send v-else :size="15" />{{ sending ? "发送中" : "确认并发送" }}</button>
      </div>
    </article>
  </section>

  <section class="panel notification-history-panel">
    <div class="panel-heading"><div><p>发送审计</p><h2>消息记录</h2></div><span class="panel-action">共 {{ total }} 条</span></div>
    <div class="notification-table-wrap">
      <table class="notification-table"><thead><tr><th>状态</th><th>渠道 / 类型</th><th>标题与内容</th><th>发起人</th><th>发送时间</th><th>服务商响应</th></tr></thead><tbody>
        <tr v-for="item in deliveries" :key="item.delivery_id">
          <td><span class="delivery-status" :class="item.status"><CheckCircle2 v-if="item.status === 'sent'" :size="13" /><XCircle v-else-if="item.status === 'failed'" :size="13" /><LoaderCircle v-else :size="13" />{{ item.status === "sent" ? "成功" : item.status === "failed" ? "失败" : "发送中" }}</span></td>
          <td><strong>{{ item.channel_name || `渠道 ${item.channel_id}` }}</strong><small>{{ item.message_type === "markdown" ? "Markdown" : "纯文本" }}</small></td>
          <td class="notification-content-cell"><strong>{{ item.title }}</strong><small>{{ item.content }}</small></td>
          <td>{{ item.requested_by || "系统任务" }}</td><td>{{ formatTime(item.sent_at || item.created_at) }}</td><td class="response-cell">{{ item.provider_message || "--" }}</td>
        </tr>
        <tr v-if="!deliveries.length"><td colspan="6" class="notification-empty-cell">暂无发送记录</td></tr>
      </tbody></table>
    </div>
    <div class="notification-pagination"><span>第 {{ page }} / {{ pageCount }} 页</span><label>每页 <select v-model.number="pageSize"><option :value="10">10</option><option :value="20">20</option><option :value="50">50</option></select> 条</label><div><button :disabled="page <= 1" @click="setPage(page - 1)">上一页</button><button v-for="item in visiblePages" :key="item" :class="{ active: item === page }" @click="setPage(item)">{{ item }}</button><button :disabled="page >= pageCount" @click="setPage(page + 1)">下一页</button></div></div>
  </section>
</template>

<style scoped>
.notification-heading { margin-bottom: 14px; }
.notification-banner { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; border: 1px solid; border-radius: 6px; padding: 10px 13px; font-size: 12px; }.notification-banner.success { border-color: #bce2ce; color: #167451; background: #f4fbf7; }.notification-banner.error { border-color: #efc7c7; color: #b04444; background: #fff7f7; }
.notification-layout { display: grid; grid-template-columns: minmax(320px, .8fr) minmax(460px, 1.4fr); gap: 14px; align-items: start; }.notification-safe-note { margin: 9px 0 14px; color: #7c8c83; font-size: 11px; line-height: 1.6; }
.notification-channel-list { display: grid; gap: 7px; }.notification-channel-list > button { display: grid; grid-template-columns: 34px 1fr auto 26px; align-items: center; gap: 8px; width: 100%; border: 1px solid #e0e9e3; border-radius: 6px; padding: 9px; color: #40554a; background: #fff; text-align: left; cursor: pointer; }.notification-channel-list > button.active { border-color: #4da47e; box-shadow: 0 0 0 2px rgba(22,132,91,.08); }.channel-icon { display: grid; place-items: center; width: 32px; height: 32px; border-radius: 6px; color: #16845b; background: #eef8f3; }.notification-channel-list strong,.notification-channel-list small { display:block; }.notification-channel-list small { margin-top: 3px; color:#89978f; font-size:10px; }.notification-channel-list em { border-radius: 99px; padding: 3px 7px; font-size: 9px; font-style: normal; }.notification-channel-list em.ready { color:#14734f; background:#eaf8f1; }.notification-channel-list em.pending { color:#987026; background:#fff7e7; }.notification-channel-list i { display:grid; place-items:center; width:25px; height:25px; border-radius:4px; color:#809087; font-style:normal; }.notification-channel-list i:hover { color:#16845b; background:#eef7f2; }
.notification-empty { display:flex; align-items:center; justify-content:center; gap:8px; min-height:80px; color:#93a098; font-size:11px; }.notification-channel-form { display:grid; gap:10px; margin-top:16px; border-top:1px solid #edf2ef; padding-top:15px; }.notification-form-title { display:flex; justify-content:space-between; align-items:center; color:#40554a; font-size:12px; }.notification-form-title button { border:0; color:#16845b; background:transparent; font-size:10px; cursor:pointer; }.notification-channel-form label,.notification-field,.notification-compose-grid label { display:grid; gap:5px; color:#708078; font-size:10px; }.notification-channel-form input,.notification-compose-grid select,.notification-field input,.notification-field textarea { width:100%; box-sizing:border-box; border:1px solid #dbe5df; border-radius:5px; padding:8px 9px; color:#354b3f; background:#fff; font:inherit; font-size:11px; outline:none; }.notification-field textarea { resize:vertical; min-height:170px; line-height:1.65; }.notification-channel-form input:focus,.notification-compose-grid select:focus,.notification-field input:focus,.notification-field textarea:focus { border-color:#55a783; box-shadow:0 0 0 2px rgba(22,132,91,.08); }.notification-check { display:inline-flex !important; grid-template-columns:auto 1fr; align-items:center; gap:7px !important; }.notification-check input { width:auto; accent-color:#16845b; }.notification-primary { display:inline-flex; align-items:center; justify-content:center; gap:6px; border:1px solid #16845b; border-radius:5px; min-height:34px; padding:0 13px; color:#fff; background:#16845b; font-size:11px; cursor:pointer; }.notification-primary:disabled { cursor:not-allowed; opacity:.5; }
.notification-compose-grid { display:grid; grid-template-columns:1fr 160px; gap:10px; margin:13px 0 11px; }.notification-field { margin-bottom:11px; }.notification-send-row { display:flex; align-items:center; gap:12px; border-top:1px solid #edf2ef; padding-top:13px; }.notification-send-row > span { margin-right:auto; color:#89978f; font-size:10px; }
.notification-history-panel { margin-top:14px; }.notification-table-wrap { overflow-x:auto; margin-top:10px; }.notification-table { width:100%; min-width:900px; border-collapse:collapse; table-layout:fixed; }.notification-table th,.notification-table td { border-bottom:1px solid #edf2ef; padding:10px 8px; color:#65766d; font-size:10px; text-align:left; vertical-align:top; }.notification-table th { color:#8b9890; font-size:9px; font-weight:650; }.notification-table th:nth-child(1){width:70px}.notification-table th:nth-child(2){width:130px}.notification-table th:nth-child(4){width:90px}.notification-table th:nth-child(5){width:140px}.notification-table th:nth-child(6){width:170px}.notification-table td strong,.notification-table td small { display:block; }.notification-table td strong { color:#40554a; font-size:10px; }.notification-table td small { margin-top:4px; color:#929e97; font-size:9px; }.notification-content-cell small { overflow:hidden; max-width:460px; text-overflow:ellipsis; white-space:nowrap; }.response-cell { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.delivery-status { display:inline-flex; align-items:center; gap:4px; border-radius:99px; padding:3px 6px; }.delivery-status.sent { color:#14734f;background:#eaf8f1}.delivery-status.failed {color:#b04444;background:#fff0f0}.delivery-status.sending {color:#987026;background:#fff7e7}.notification-empty-cell { padding:30px !important; color:#94a199 !important; text-align:center !important; }
.notification-pagination { display:flex; align-items:center; gap:10px; padding-top:13px; color:#87958d; font-size:10px; }.notification-pagination > span { margin-right:auto; }.notification-pagination label { display:flex; align-items:center; gap:5px; }.notification-pagination select { border:1px solid #dbe5df; border-radius:4px; padding:4px; color:#52665a; background:#fff; }.notification-pagination > div { display:flex; gap:4px; }.notification-pagination button { min-width:28px; border:1px solid #dbe5df; border-radius:4px; padding:5px 7px; color:#52665a; background:#fff; font-size:10px; cursor:pointer; }.notification-pagination button.active { border-color:#16845b; color:#fff; background:#16845b; }.notification-pagination button:disabled { opacity:.4; cursor:not-allowed; }
@media(max-width:900px){.notification-layout{grid-template-columns:1fr}.notification-compose-grid{grid-template-columns:1fr}.notification-send-row{align-items:flex-start;flex-wrap:wrap}.notification-send-row>span{width:100%;margin:0}.notification-pagination{flex-wrap:wrap}.notification-pagination>span{width:100%;margin:0}}
</style>
