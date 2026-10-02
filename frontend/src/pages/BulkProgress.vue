<template>
  <div>
    <AppHeader title="Bulk transfer" back="/home" />
    <main class="space-y-3 p-4">
      <div v-if="error" class="rounded-lg bg-danger-bg p-3 text-danger-text">{{ error }}</div>
      <div v-else-if="!st" class="space-y-2"><div class="skeleton h-24" /><div class="skeleton h-40" /></div>
      <template v-else>
        <div class="rounded-xl p-4" :class="box">
          <div class="text-[18px] font-bold">{{ headline }}</div>
          <div class="mt-1 text-[14px]">
            {{ st.done }} of {{ st.parts }} transfers made<template v-if="st.lines"> · {{ fmt(st.lines) }} lines</template>
          </div>
          <div class="mt-3 h-3 overflow-hidden rounded-full bg-surface">
            <div class="h-full bg-brand-deep transition-all" :style="{ width: pct + '%' }" />
          </div>
          <p v-if="st.error" class="mt-3 text-[14px] font-semibold">{{ st.error }}</p>
          <p v-if="st.state === 'stopped'" class="mt-2 text-[14px]">
            The transfers already made are final. Fix the problem, then move the remaining items as a new transfer.
          </p>
        </div>
        <div v-if="st.from_warehouse" class="text-[15px] font-semibold">{{ st.from_warehouse }} → {{ st.to_warehouse }}</div>
        <div class="rounded-xl border border-surface-line bg-surface">
          <div v-if="!st.transfers.length" class="p-4 text-ink-muted">Waiting for the first transfer…</div>
          <router-link
            v-for="t in st.transfers"
            :key="t.name"
            :to="`/t/${encodeURIComponent(t.name)}`"
            class="flex items-center justify-between gap-3 border-b border-surface-line px-4 py-3 last:border-0"
          >
            <span><span class="block font-semibold">{{ t.name }}</span><span class="block text-[13px] text-ink-faint">Part {{ t.part }} of {{ t.parts }}</span></span>
            <span class="tnum font-semibold">{{ t.line_count }} lines ›</span>
          </router-link>
        </div>
        <router-link to="/home" class="flex min-h-secondary items-center justify-center font-semibold text-brand-deep">Home</router-link>
      </template>
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue"

import AppHeader from "@/components/AppHeader.vue"
import { bulkStatus } from "@/data/api.js"
import { fmt } from "@/data/format.js"

const props = defineProps({ ref_: { type: String, required: true } })
const st = ref(null)
const error = ref("")
let timer = null

const pct = computed(() => (st.value && st.value.parts ? Math.round((100 * st.value.done) / st.value.parts) : 0))
const finished = computed(() => st.value && ["done", "stopped"].includes(st.value.state))
const headline = computed(() => {
  const s = st.value.state
  if (s === "done") return "All stock moved"
  if (s === "stopped") return "Stopped"
  if (s === "queued") return "Waiting to start…"
  if (s === "running") return "Moving stock…"
  return "Checking…"
})
const box = computed(() =>
  st.value.state === "done" ? "bg-ok-bg text-ok-text" : st.value.state === "stopped" ? "bg-danger-bg text-danger-text" : "bg-brand-soft text-ink"
)

async function poll() {
  try {
    st.value = await bulkStatus(props.ref_)
    error.value = ""
  } catch (e) {
    error.value = e.display ? e.display() : "Could not load."
  }
  if (!finished.value) timer = setTimeout(poll, 5000)
}

onMounted(poll)
onBeforeUnmount(() => clearTimeout(timer))
</script>
