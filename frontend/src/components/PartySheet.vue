<template>
  <div class="fixed inset-0 z-50 flex flex-col bg-surface-page">
    <AppHeader :title="`Choose the ${label.toLowerCase()}`">
      <template #right>
        <button type="button" class="px-3 py-2 font-semibold text-brand-deep" @click="$emit('close')">Close</button>
      </template>
    </AppHeader>
    <div class="flex-1 space-y-3 overflow-y-auto p-4">
      <p v-if="printed" class="rounded-xl border border-surface-line bg-surface p-3 text-[14px]">
        The paper says <b>{{ printed }}</b><template v-if="gstin"> · GSTIN {{ gstin }}</template>
      </p>
      <section v-if="candidates.length && !txt.trim()">
        <h2 class="mb-2 text-[15px] font-bold">Closest names</h2>
        <button v-for="c in candidates" :key="c.party" type="button" class="mb-2 w-full rounded-xl border border-surface-line bg-surface p-3 text-left" @click="$emit('pick', c.party)">
          <span class="block font-semibold">{{ c.title }}</span>
          <span v-if="c.title !== c.party" class="block text-[13px] text-ink-faint">{{ c.party }}</span>
        </button>
      </section>
      <input v-model="txt" type="search" enterkeyhint="search" :placeholder="`Search ${label.toLowerCase()}s`" class="w-full rounded-lg border border-surface-line bg-surface p-3" :aria-label="`Search ${label.toLowerCase()}s`" />
      <p v-if="error" class="rounded-lg bg-danger-bg p-3 text-danger-text">{{ error }}</p>
      <div v-if="loading" class="space-y-2"><div v-for="i in 3" :key="i" class="skeleton h-14" /></div>
      <button v-for="r in results" :key="r.party" type="button" class="w-full rounded-xl border border-surface-line bg-surface p-3 text-left" @click="$emit('pick', r.party)">
        <span class="block font-semibold">{{ r.title }}</span>
        <span class="block text-[13px] text-ink-faint">{{ r.party }}<template v-if="r.extra"> · {{ r.extra }}</template></span>
      </button>
      <p v-if="!loading && !error && txt.trim().length >= 2 && !results.length" class="p-4 text-center text-ink-muted">Nothing found. A new {{ label.toLowerCase() }} is created in the ERP.</p>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from "vue"

import AppHeader from "@/components/AppHeader.vue"
import { searchParties } from "@/data/paper.js"

const props = defineProps({
  purpose: { type: String, required: true }, // "Purchase Order" | "Sales Order"
  label: { type: String, default: "Supplier" },
  printed: { type: String, default: "" },
  gstin: { type: String, default: "" },
  candidates: { type: Array, default: () => [] },
})
defineEmits(["pick", "close"])

const txt = ref("")
const results = ref([])
const loading = ref(false)
const error = ref("")
let timer = null
let seq = 0

async function load(v) {
  const mine = ++seq
  loading.value = true
  error.value = ""
  try {
    const rows = await searchParties(props.purpose, v)
    if (mine === seq) results.value = rows || []
  } catch (e) {
    if (mine === seq) error.value = e.display ? e.display() : "Search failed."
  } finally {
    if (mine === seq) loading.value = false
  }
}

watch(txt, (v) => {
  clearTimeout(timer)
  timer = setTimeout(() => load(v.trim()), 350)
})
onMounted(() => {
  if (!props.candidates.length) load("")
})
</script>
