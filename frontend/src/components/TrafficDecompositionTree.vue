<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { ChevronDown, ChevronRight } from "lucide-vue-next"
import type { TrafficTreeNode } from "@/types"
import { currency, number, ratio } from "@/lib/format"

const props = defineProps<{ nodes: TrafficTreeNode[]; selectedId: string }>()
const emit = defineEmits<{ select: [node: TrafficTreeNode] }>()
const expanded = ref(new Set<string>())
const maxByLevel = computed(() => {
  const values = new Map<number, number>()
  const visit = (nodes: TrafficTreeNode[]) => { for (const node of nodes) { values.set(node.level, Math.max(values.get(node.level) || 0, node.paid_amount)); visit(node.children) } }
  visit(props.nodes)
  return values
})
watch(() => props.nodes, (nodes) => {
  const ids = new Set<string>()
  const visit = (items: TrafficTreeNode[]) => { for (const node of items) { if (node.children.length) { ids.add(node.id); visit(node.children) } } }
  visit(nodes)
  expanded.value = ids
}, { immediate: true })
function toggle(node: TrafficTreeNode): void { if (!node.children.length) return; const next = new Set(expanded.value); if (next.has(node.id)) next.delete(node.id); else next.add(node.id); expanded.value = next }
function width(node: TrafficTreeNode): string { const peak = maxByLevel.value.get(node.level) || 1; return `${Math.max(node.paid_amount ? 5 : 0, Math.min(100, node.paid_amount / peak * 100))}%` }
</script>

<template>
  <div class="traffic-tree" role="tree" aria-label="流量来源一级二级三级分解树">
    <div class="traffic-tree-head"><span>一级来源</span><span>二级来源</span><span>三级来源</span></div>
    <div class="traffic-tree-roots">
      <article v-for="root in nodes" :key="root.id" class="traffic-tree-root">
        <div class="traffic-tree-level level-one"><button :class="{ active: selectedId === root.id }" type="button" @click="emit('select', root)"><span class="traffic-tree-node-title"><i class="traffic-tree-toggle" @click.stop="toggle(root)"><ChevronDown v-if="expanded.has(root.id)" :size="13" /><ChevronRight v-else :size="13" /></i><strong>{{ root.name }}</strong><em>L1</em></span><span class="traffic-tree-bar"><i :style="{ width: width(root) }"></i></span><small>{{ currency(root.paid_amount) }} · {{ number(root.visitors) }} 访客 · {{ ratio(root.conversion_rate) }}</small></button></div>
        <div v-if="expanded.has(root.id) && root.children.length" class="traffic-tree-branches">
          <article v-for="child in root.children" :key="child.id" class="traffic-tree-branch"><div class="traffic-tree-connector"></div><div class="traffic-tree-level level-two"><button :class="{ active: selectedId === child.id }" type="button" @click="emit('select', child)"><span class="traffic-tree-node-title"><i v-if="child.children.length" class="traffic-tree-toggle" @click.stop="toggle(child)"><ChevronDown v-if="expanded.has(child.id)" :size="13" /><ChevronRight v-else :size="13" /></i><i v-else class="traffic-tree-dot"></i><strong>{{ child.name }}</strong><em>L2</em></span><span class="traffic-tree-bar"><i :style="{ width: width(child) }"></i></span><small>{{ currency(child.paid_amount) }} · {{ number(child.visitors) }} 访客</small></button></div><div v-if="expanded.has(child.id) && child.children.length" class="traffic-tree-leaves"><div v-for="leaf in child.children" :key="leaf.id" class="traffic-tree-leaf"><div class="traffic-tree-leaf-connector"></div><div class="traffic-tree-level level-three"><button :class="{ active: selectedId === leaf.id }" type="button" @click="emit('select', leaf)"><span class="traffic-tree-node-title"><i class="traffic-tree-dot"></i><strong>{{ leaf.name }}</strong><em>L3</em></span><span class="traffic-tree-bar"><i :style="{ width: width(leaf) }"></i></span><small>{{ currency(leaf.paid_amount) }} · {{ number(leaf.visitors) }} 访客</small></button></div></div></div></article>
        </div>
      </article>
    </div>
  </div>
</template>

<style scoped>
.traffic-tree { min-width: 760px; }.traffic-tree-head { display: grid; grid-template-columns: 28% 34% 38%; gap: 18px; border-bottom: 1px solid #e4e9ef; padding: 0 12px 10px; color: #98a2b3; font-size: 10px; font-weight: 650; }.traffic-tree-roots { display: grid; gap: 10px; padding-top: 12px; }.traffic-tree-root { display: grid; grid-template-columns: 28% 72%; gap: 18px; align-items: start; }.traffic-tree-branches { display: grid; gap: 8px; }.traffic-tree-branch { display: grid; position: relative; grid-template-columns: 47% 53%; gap: 18px; align-items: start; }.traffic-tree-leaves { display: grid; gap: 7px; }.traffic-tree-leaf { display: grid; position: relative; }.traffic-tree-connector, .traffic-tree-leaf-connector { position: absolute; top: 24px; right: calc(100% - 2px); width: 18px; border-top: 1px solid #ccd8e6; }.traffic-tree-level button { width: 100%; border: 1px solid #dfe6ee; border-radius: 5px; padding: 10px 11px; color: #475467; background: #fff; text-align: left; cursor: pointer; transition: border-color .16s ease, box-shadow .16s ease, transform .16s ease; }.traffic-tree-level button:hover { border-color: #9fb7e7; box-shadow: 0 4px 14px rgba(47,98,212,.08); transform: translateY(-1px); }.traffic-tree-level button.active { border-color: #5f84dc; box-shadow: 0 0 0 2px rgba(53,106,230,.12); background: #f8faff; }.traffic-tree-node-title { display: flex; min-width: 0; align-items: center; gap: 6px; }.traffic-tree-node-title strong { overflow: hidden; flex: 1; color: #344054; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }.traffic-tree-node-title em { border-radius: 3px; padding: 2px 4px; color: #7b8ba8; background: #eef2f8; font-size: 8px; font-style: normal; }.traffic-tree-toggle { display: grid; width: 17px; height: 17px; flex: 0 0 auto; place-items: center; border-radius: 3px; color: #4e6fae; background: #edf2fb; }.traffic-tree-dot { width: 6px; height: 6px; flex: 0 0 auto; border-radius: 50%; background: #7b9add; }.traffic-tree-bar { display: block; height: 4px; margin: 9px 0 7px; overflow: hidden; border-radius: 4px; background: #edf1f6; }.traffic-tree-bar i { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, #4c7df0, #83a7f7); }.traffic-tree-level small { display: block; overflow: hidden; color: #98a2b3; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
</style>
