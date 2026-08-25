<script setup lang="ts">
import { ArrowLeft, LockKeyhole } from "lucide-vue-next"
import { RouterLink } from "vue-router"
</script>

<template>
  <main class="auth-page">
    <section class="auth-panel access-denied-panel" aria-labelledby="forbidden-title">
      <div class="auth-brand">
        <div class="auth-brand-mark"><LockKeyhole :size="22" /></div>
        <div><strong>EchoMerch</strong><span>访问控制</span></div>
      </div>
      <div class="auth-heading">
        <p>403 · 访问被拒绝</p>
        <h1 id="forbidden-title">当前账号无权访问</h1>
        <span>请联系管理员为你的账号授权对应业务模块或店铺。</span>
      </div>
      <RouterLink class="auth-submit auth-link" to="/"><ArrowLeft :size="17" /><span>返回经营概览</span></RouterLink>
    </section>
  </main>
</template>
