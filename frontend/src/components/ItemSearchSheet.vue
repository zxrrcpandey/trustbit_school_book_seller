<template>
  <div class="fixed inset-0 z-50 flex flex-col bg-surface-page">
    <div class="safe-top border-b border-surface-line bg-surface px-3 py-2">
      <div class="flex items-center gap-2">
        <input
          ref="input"
          v-model="txt"
          type="search"
          enterkeyhint="search"
          placeholder="Book or item name, code, ISBN"
          class="min-w-0 flex-1 rounded-lg border border-surface-line bg-surface p-3"
          aria-label="Search items"
        />
        <button type="button" class="px-2 py-3 font-semibold text-brand-deep" @click="$emit('close')">Close</button>
      </div>
      <div class="mt-1 text-[13px] text-ink-faint">Type two or more words to narrow it down, e.g. "viva maths 3".</div>
    </div>
    <div class="flex-1 overflow-y-auto px-3 py-2">
      <div v-if="error" class="rounded-lg bg-danger-bg p-3 text-danger-text">{{ error }}</div>
      <div v-else-if="loading" class="space-y-2">
        <div v-for="i in 4" :key="i" class="skeleton h-16" />
      </div>
      <div v-else-if="txt.trim().length >= 2 && !results.length" class="p-6 text-center text-ink-muted">Nothing found.</div>
      <button
        v-for="r in results"
        :key="r.item_code"
        type="button"
        class="mb-2 flex w-full items-center justify-between gap-3 rounded-xl border border-surface-line bg-surface p-3 text-left"
        @click="$emit('pick', r.item_code)"
      >
        <span class="min-w-0">
          <span class="block font-semibold">{{ r.item_name }}</span>
          <span class="block text-[13px] text-ink-faint">{{ r.item_code }}</span>
        </span>
        <span class="tnum flex-none text-right text-[14px]" :class="r.available > 0 ? 'text-ok-text' : 'text-ink-faint'">
          {{ fmt(r.available) }} {{ r.stock_uom }}
        </span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from "vue"

import { searchItems } from "@/data/api.js"
import { fmt } from "@/data/format.js"

const props = defineProps({ from: { type: String, default: "" } })
defineEmits(["pick", "close"])

const input = ref(null)
const txt = ref("")
const results = ref([])
const loading = ref(false)
const error = ref("")
let timer = null
let seq = 0

watch(txt, (v) => {
  clearTimeout(timer)
  error.value = ""
  if (v.trim().length < 2) {
    results.value = []
    loading.value = false
    return
  }
  loading.value = true
  timer = setTimeout(async () => {
    const mine = ++seq
    try {
      const rows = await searchItems(v.trim(), props.from)
      if (mine === seq) results.value = rows || []
    } catch (e) {
      if (mine === seq) error.value = e.display ? e.display() : "Search failed."
    } finally {
      if (mine === seq) loading.value = false
    }
  }, 400)
})

onMounted(() => input.value && input.value.focus())
</script>
