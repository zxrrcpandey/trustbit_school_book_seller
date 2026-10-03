<template>
  <div>
    <AppHeader title="KGS Staff">
      <template #right>
        <button type="button" class="px-3 py-2 text-[14px] font-semibold text-ink-faint" @click="logout">Sign out</button>
      </template>
    </AppHeader>
    <main class="space-y-4 p-4">
      <div class="text-[15px] text-ink-muted">Hello, <b class="text-ink">{{ info ? info.full_name : "…" }}</b></div>

      <div v-if="added.length" class="rounded-xl bg-ok-bg p-4 text-ok-text">
        <div class="text-[17px] font-bold">{{ $route.query.already ? "Already saved" : "Extra stock added" }} in {{ $route.query.to }}</div>
        <div class="text-[14px]">Nothing was in the system to transfer, so only the extra you counted was added.</div>
        <div v-for="r in added" :key="r.name" class="tnum text-[14px]">{{ r.name }} — stock value change ₹{{ Number(r.value).toLocaleString("en-IN", { minimumFractionDigits: 2 }) }}</div>
      </div>

      <InstallPrompt />

      <router-link to="/transfer" class="flex min-h-[88px] items-center justify-between rounded-2xl bg-brand-deep px-5 text-white">
        <span>
          <span class="block text-[20px] font-bold">{{ draft.lines.length ? "Continue transfer" : "New transfer" }}</span>
          <span class="block text-[14px] opacity-90">
            {{ draft.lines.length ? `${draft.lines.length} item${draft.lines.length === 1 ? "" : "s"} scanned · ${short(draft.from)} → ${short(draft.to)}` : "Move stock between warehouses" }}
          </span>
        </span>
        <span class="text-3xl">›</span>
      </router-link>

      <section>
        <div class="mb-2 flex items-center justify-between">
          <h2 class="text-[16px] font-bold">Recent transfers</h2>
          <router-link to="/transfers" class="py-2 text-[14px] font-semibold text-brand-deep">See all</router-link>
        </div>
        <div v-if="error" class="rounded-lg bg-danger-bg p-3 text-danger-text">{{ error }}</div>
        <div v-else-if="!recent" class="space-y-2"><div v-for="i in 3" :key="i" class="skeleton h-[72px]" /></div>
        <div v-else-if="!recent.length" class="rounded-xl border border-dashed border-surface-line p-6 text-center text-ink-muted">No transfers in the last 30 days.</div>
        <TransferRow v-for="t in recent" :key="t.name" :t="t" />
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"
import { useRoute } from "vue-router"

import AppHeader from "@/components/AppHeader.vue"
import InstallPrompt from "@/components/InstallPrompt.vue"
import TransferRow from "@/components/TransferRow.vue"
import { boot, myTransfers } from "@/data/api.js"
import { draft, loadDraft } from "@/data/draft.js"
import { shortWarehouse as short } from "@/data/format.js"
import { logout } from "@/data/session.js"

const route = useRoute()
const added = computed(() =>
  String(route.query.added || "").split(",").filter(Boolean).map((x) => ({ name: x.split(":")[0], value: x.split(":")[1] || 0 }))
)
const info = ref(null)
const recent = ref(null)
const error = ref("")

onMounted(async () => {
  loadDraft()
  try {
    info.value = await boot()
    recent.value = ((await myTransfers("mine", 30)) || []).slice(0, 5)
  } catch (e) {
    error.value = e.display ? e.display() : "Could not load."
  }
})
</script>
