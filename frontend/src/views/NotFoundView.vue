<script setup lang="ts">
import { ArrowLeft, Compass } from "lucide-vue-next"
import { RouterLink } from "vue-router"
</script>

<template>
  <main class="not-found-page">
    <section class="not-found-panel">
      <div class="not-found-icon"><Compass :size="30" /></div>
      <p>页面导航</p>
      <h1>这个页面还不存在</h1>
      <span>当前地址没有对应的经营或系统模块，请返回工作台继续操作。</span>
      <RouterLink to="/" class="not-found-link"><ArrowLeft :size="16" />返回经营概览</RouterLink>
    </section>
  </main>
</template>
