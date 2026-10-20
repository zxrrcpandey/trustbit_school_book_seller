<template>
  <div>
    <AppHeader title="Papers" />
    <main class="p-4">
      <div v-if="isManager" class="mb-3 grid grid-cols-2 gap-1 rounded-xl bg-surface-line p-1">
        <button v-for="s in ['mine', 'all']" :key="s" type="button" class="min-h-secondary rounded-lg font-semibold" :class="scope === s ? 'bg-surface' : 'text-ink-muted'" @click="scope = s">
          {{ s === "mine" ? "Mine" : "Everyone" }}
        </button>
      </div>
      <div v-if="only" class="mb-3 flex min-h-secondary items-center justify-between gap-2 rounded-xl border border-surface-line bg-surface py-1 pl-3 pr-1">
        <span class="text-[14px] text-ink-muted">Only <b class="text-ink">{{ only.label }}</b></span>
        <router-link to="/papers" replace class="flex min-h-[40px] items-center rounded-lg px-3 text-[14px] font-semibold text-brand-deep">Show all</router-link>
      </div>
      <div v-if="error" class="rounded-lg bg-danger-bg p-3 text-danger-text">{{ error }}</div>
      <div v-else-if="!rows" class="space-y-2"><div v-for="i in 5" :key="i" class="skeleton h-[72px]" /></div>
      <div v-else-if="!shown.length" class="p-6 text-center text-ink-muted">{{ only ? `No papers ${only.empty} in the last 60 days.` : "No papers in the last 60 days." }}</div>
      <PaperRow v-for="p in shown" :key="p.name" :p="p" :show-owner="scope === 'all'" />
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue"
import { useRoute } from "vue-router"

import AppHeader from "@/components/AppHeader.vue"
import PaperRow from "@/components/PaperRow.vue"
import { boot } from "@/data/api.js"
import { myPapers } from "@/data/paper.js"

const route = useRoute()
// Home's "Waiting for you" opens this list filtered: ?status=Ready or ?status=Failed
const FILTERS = { Ready: { label: "To check", empty: "to check" }, Failed: { label: "Not read", empty: "that could not be read" } }
const only = computed(() => FILTERS[route.query.status] || null)
const scope = ref("mine")
const isManager = ref(false)
const rows = ref(null)
const error = ref("")
const shown = computed(() => (only.value ? (rows.value || []).filter((p) => p.status === route.query.status) : rows.value || []))

async function load() {
  rows.value = null
  error.value = ""
  try {
    rows.value = (await myPapers(scope.value, 60)) || []
  } catch (e) {
    error.value = e.display ? e.display() : "Could not load."
  }
}

watch(scope, load)
onMounted(async () => {
  try {
    const p = (await boot()).paper || {}
    isManager.value = !!(p.names || p.settings)
  } catch {
    /* list still loads */
  }
  load()
})
</script>
