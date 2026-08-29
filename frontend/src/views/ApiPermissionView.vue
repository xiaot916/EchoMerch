<script setup lang="ts">
import { computed, ref } from "vue"
import { CircleAlert, LoaderCircle, RefreshCw, Search, ShieldCheck, X } from "lucide-vue-next"

import SystemAdminHeader from "@/components/SystemAdminHeader.vue"
import { useAsyncData } from "@/composables/useAsyncData"
import { fetchApiPermissions } from "@/api"
import type { ApiPermissionRecord } from "@/types"

const {
  data: records,
  loading,
  error,
  refresh: load,
} = useAsyncData<ApiPermissionRecord[]>(fetchApiPermissions, {
  initialData: [],
  errorMessage: "接口权限目录读取失败。",
})
const pathDraft = ref("")
const nameDraft = ref("")
const moduleDraft = ref("all")
const pathFilter = ref("")
const nameFilter = ref("")
const moduleFilter = ref("all")
const selectedRecord = ref<ApiPermissionRecord | null>(null)

const moduleOptions = computed(() => [...new Set(records.value.map((record) => record.module))].sort())
const protectedCount = computed(() => records.value.filter((record) => record.protected).length)
const rbacCount = computed(() => records.value.filter((record) => Boolean(record.permission)).length)
const writeCount = computed(() => records.value.filter((record) => !["GET", "HEAD", "OPTIONS"].includes(record.method.toLocaleUpperCase())).length)

const filteredRecords = computed(() => {
  const path = pathFilter.value.trim().toLocaleLowerCase()
  const name = nameFilter.value.trim().toLocaleLowerCase()
  return records.value.filter((record) => {
    const matchesPath = !path || record.path.toLocaleLowerCase().includes(path)
    const matchesName = !name || [record.name, record.permission || ""].some((value) => value.toLocaleLowerCase().includes(name))
    const matchesModule = moduleFilter.value === "all" || record.module === moduleFilter.value
    return matchesPath && matchesName && matchesModule
  })
})

function queryRecords(): void {
  pathFilter.value = pathDraft.value
  nameFilter.value = nameDraft.value
  moduleFilter.value = moduleDraft.value
}

function resetFilters(): void {
  pathDraft.value = ""
  nameDraft.value = ""
  moduleDraft.value = "all"
  pathFilter.value = ""
  nameFilter.value = ""
  moduleFilter.value = "all"
}

function methodClass(method: string): string {
  return method.toLocaleLowerCase()
}

</script>

<template>
  <section class="crud-page">
    <SystemAdminHeader title="接口权限" description="核对 FastAPI 运行时路由、模块归属和实际服务端权限依赖。" active="apis">
      <template #action><button class="crud-refresh-button" type="button" :disabled="loading" @click="load"><RefreshCw :size="15" :class="{ spinning: loading }" />同步接口目录</button></template>
    </SystemAdminHeader>

    <p v-if="error" class="admin-inline-message error" role="alert">
      <CircleAlert :size="16" />{{ error }}
    </p>

    <section v-if="!loading" class="system-admin-stats" aria-label="接口目录摘要">
      <div><span>接口总数</span><strong>{{ records.length }}</strong><small>FastAPI 运行时路由</small></div>
      <div><span>业务模块</span><strong>{{ moduleOptions.length }}</strong><small>按路由标签归类</small></div>
      <div><span>RBAC 权限</span><strong>{{ rbacCount }}</strong><small>{{ protectedCount }} 条绑定权限依赖</small></div>
      <div><span>写操作接口</span><strong>{{ writeCount }}</strong><small>POST / PUT / DELETE</small></div>
    </section>

    <section class="crud-panel crud-filter-panel" aria-label="接口查询">
      <div class="crud-filter-row crud-filter-row-api">
        <label class="crud-filter-field">
          <span>接口路径</span>
          <span class="crud-input-shell">
            <Search :size="15" />
            <input v-model="pathDraft" type="search" placeholder="请输入接口路径" @keyup.enter="queryRecords" />
          </span>
        </label>
        <label class="crud-filter-field">
          <span>接口说明 / 权限</span>
          <input v-model="nameDraft" type="search" placeholder="请输入接口名称或权限标识" @keyup.enter="queryRecords" />
        </label>
        <label class="crud-filter-field crud-filter-field-compact">
          <span>模块标签</span>
          <select v-model="moduleDraft">
            <option value="all">全部模块</option>
            <option v-for="module in moduleOptions" :key="module" :value="module">{{ module }}</option>
          </select>
        </label>
        <div class="crud-filter-actions">
          <button class="crud-reset-button" type="button" @click="resetFilters">重置</button>
          <button class="crud-query-button" type="button" @click="queryRecords">查询</button>
        </div>
      </div>
    </section>

    <section v-if="loading" class="admin-loading-state">
      <LoaderCircle :size="22" class="spinning" />正在读取 FastAPI 路由
    </section>

    <section v-else class="crud-panel crud-table-panel">
      <header class="system-panel-heading"><div><h3>接口目录</h3><span>路由、模块和服务端鉴权策略</span></div><span>{{ filteredRecords.length }} / {{ records.length }} 条</span></header>
      <div class="crud-table-scroll">
        <div class="crud-table crud-api-table" role="table" aria-label="接口权限列表">
          <div class="crud-table-row crud-table-head" role="row">
            <span>请求方式</span>
            <span>接口路径</span>
            <span>接口说明</span>
            <span>模块标签</span>
            <span>权限标识</span>
            <span>服务端校验</span>
            <span>操作</span>
          </div>
          <div v-for="record in filteredRecords" :key="`${record.method}:${record.path}`" class="crud-table-row" role="row">
            <span class="http-method" :class="methodClass(record.method)">{{ record.method }}</span>
            <code class="crud-api-path">{{ record.path }}</code>
            <span class="crud-table-description">{{ record.name }}</span>
            <span class="crud-module-tag">{{ record.module }}</span>
            <code>{{ record.permission || "—" }}</code>
            <span class="crud-protection-tag" :class="{ protected: record.protected }">
              {{ record.protected ? "权限依赖" : "其他鉴权" }}
            </span>
            <div class="crud-actions">
              <button class="crud-edit-button" type="button" @click="selectedRecord = record">查看</button>
            </div>
          </div>
        </div>
      </div>
      <footer class="crud-table-footer">共 {{ filteredRecords.length }} 条接口记录</footer>
    </section>

    <div v-if="selectedRecord" class="access-drawer-backdrop" @click.self="selectedRecord = null">
      <aside class="access-drawer" role="dialog" aria-modal="true" aria-label="接口详情">
        <header>
          <div><p>接口详情</p><h3>{{ selectedRecord.name }}</h3></div>
          <button type="button" title="关闭" @click="selectedRecord = null"><X :size="18" /></button>
        </header>
        <div class="role-permission-drawer-body">
          <p class="crud-readonly-note">
            <ShieldCheck :size="15" />该记录来自当前运行中的 FastAPI 路由，不在前端单独维护。
          </p>
          <dl class="crud-detail-list">
            <div><dt>请求方式</dt><dd><span class="http-method" :class="methodClass(selectedRecord.method)">{{ selectedRecord.method }}</span></dd></div>
            <div><dt>接口路径</dt><dd><code>{{ selectedRecord.path }}</code></dd></div>
            <div><dt>接口说明</dt><dd>{{ selectedRecord.name }}</dd></div>
            <div><dt>模块标签</dt><dd>{{ selectedRecord.module }}</dd></div>
            <div><dt>权限标识</dt><dd><code>{{ selectedRecord.permission || "未绑定 RBAC 权限点" }}</code></dd></div>
            <div><dt>服务端校验</dt><dd>{{ selectedRecord.protected ? "已绑定权限依赖" : "由登录、数据范围或公开策略处理" }}</dd></div>
          </dl>
        </div>
      </aside>
    </div>
  </section>
</template>
