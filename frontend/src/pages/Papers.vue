<template>
  <div>
    <AppHeader title="Papers" back="/home" />
    <main class="p-4">
      <div v-if="isManager" class="mb-3 grid grid-cols-2 gap-1 rounded-xl bg-surface-line p-1">
        <button v-for="s in ['mine', 'all']" :key="s" type="button" class="min-h-secondary rounded-lg font-semibold" :class="scope === s ? 'bg-surface' : 'text-ink-muted'" @click="scope = s">
          {{ s === "mine" ? "Mine" : "Everyone" }}
        </button>
      </div>
      <div v-if="error" class="rounded-lg bg-danger-bg p-3 text-danger-text">{{ error }}</div>
      <div v-else-if="!rows" class="space-y-2"><div v-for="i in 5" :key="i" class="skeleton h-[72px]" /></div>
      <div v-else-if="!rows.length" class="p-6 text-center text-ink-muted">No papers in the last 60 days.</div>
      <PaperRow v-for="p in rows" :key="p.name" :p="p" :show-owner="scope === 'all'" />
    </main>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from "vue"

import AppHeader from "@/components/AppHeader.vue"
import PaperRow from "@/components/PaperRow.vue"
import { boot } from "@/data/api.js"
import { myPapers } from "@/data/paper.js"

const scope = ref("mine")
const isManager = ref(false)
const rows = ref(null)
const error = ref("")

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
