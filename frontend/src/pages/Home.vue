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

      <div v-if="error" class="rounded-lg bg-danger-bg p-3 text-danger-text">{{ error }}</div>
      <div v-else-if="!info" class="space-y-3"><div class="skeleton h-[88px]" /><div class="skeleton h-[88px]" /></div>

      <template v-else>
        <router-link
          v-for="(t, i) in tiles"
          :key="t.to"
          :to="t.to"
          class="flex min-h-[88px] items-center justify-between rounded-2xl px-5"
          :class="i === 0 ? 'bg-brand-deep text-white' : 'border-2 border-brand-deep bg-surface text-brand-deep'"
        >
          <span>
            <span class="block text-[20px] font-bold">{{ t.title }}</span>
            <span class="block text-[14px]" :class="i === 0 ? 'opacity-90' : 'text-ink-muted'">{{ t.sub }}</span>
          </span>
          <span class="text-3xl">›</span>
        </router-link>

        <div v-if="links.length" class="flex flex-wrap gap-2">
          <router-link v-for="l in links" :key="l.to" :to="l.to" class="min-h-secondary flex-1 whitespace-nowrap rounded-xl border border-surface-line bg-surface px-3 py-3 text-center text-[14px] font-semibold text-brand-deep">
            {{ l.label }}
          </router-link>
        </div>

        <section v-if="paperUser">
          <div class="mb-2 flex items-center justify-between">
            <h2 class="text-[16px] font-bold">Recent papers</h2>
            <router-link to="/papers" class="py-2 text-[14px] font-semibold text-brand-deep">See all</router-link>
          </div>
          <div v-if="!papers" class="space-y-2"><div v-for="i in 2" :key="i" class="skeleton h-[72px]" /></div>
          <div v-else-if="!papers.length" class="rounded-xl border border-dashed border-surface-line p-6 text-center text-ink-muted">No papers in the last 30 days.</div>
          <PaperRow v-for="p in papers || []" :key="p.name" :p="p" />
        </section>

        <section v-if="info.can_transfer">
          <div class="mb-2 flex items-center justify-between">
            <h2 class="text-[16px] font-bold">Recent transfers</h2>
            <router-link to="/transfers" class="py-2 text-[14px] font-semibold text-brand-deep">See all</router-link>
          </div>
          <div v-if="!recent" class="space-y-2"><div v-for="i in 3" :key="i" class="skeleton h-[72px]" /></div>
          <div v-else-if="!recent.length" class="rounded-xl border border-dashed border-surface-line p-6 text-center text-ink-muted">No transfers in the last 30 days.</div>
          <TransferRow v-for="t in recent || []" :key="t.name" :t="t" />
        </section>
      </template>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"
import { useRoute } from "vue-router"

import AppHeader from "@/components/AppHeader.vue"
import InstallPrompt from "@/components/InstallPrompt.vue"
import PaperRow from "@/components/PaperRow.vue"
import TransferRow from "@/components/TransferRow.vue"
import { boot, myTransfers } from "@/data/api.js"
import { draft, loadDraft } from "@/data/draft.js"
import { shortWarehouse as short } from "@/data/format.js"
import { myPapers } from "@/data/paper.js"
import { logout } from "@/data/session.js"

const route = useRoute()
const added = computed(() =>
  String(route.query.added || "").split(",").filter(Boolean).map((x) => ({ name: x.split(":")[0], value: x.split(":")[1] || 0 }))
)
const info = ref(null)
const recent = ref(null)
const papers = ref(null)
const error = ref("")

const paper = computed(() => info.value?.paper || {})
const paperUser = computed(() => !!(paper.value.po || paper.value.so || paper.value.pr || paper.value.pi))
const tiles = computed(() => {
  const out = []
  if (info.value?.can_transfer) {
    const n = draft.lines.length
    out.push({
      to: "/transfer",
      title: n ? "Continue transfer" : "New transfer",
      sub: n ? `${n} item${n === 1 ? "" : "s"} scanned · ${short(draft.from)} → ${short(draft.to)}` : "Move stock between warehouses",
    })
  }
  if (paper.value.po) out.push({ to: "/paper?for=po", title: "Purchase Order from paper", sub: "Photo or PDF of a quotation or order list" })
  if (paper.value.pr || paper.value.pi)
    out.push({ to: `/paper?for=${paper.value.pr ? "pr" : "pi"}`, title: "Receipt or Bill from paper", sub: "The supplier's bill: link the PO, check, save or submit" })
  if (paper.value.so) out.push({ to: "/paper?for=so", title: "Sales Order from paper", sub: "A school book list or a shop's order" })
  return out
})
const links = computed(() => {
  const out = []
  if (paperUser.value) out.push({ to: "/papers", label: "Papers" })
  if (paper.value.names) out.push({ to: "/names", label: "Remembered names" })
  if (paper.value.settings) out.push({ to: "/settings", label: "Settings" })
  return out
})

onMounted(async () => {
  loadDraft()
  try {
    info.value = await boot()
  } catch (e) {
    error.value = e.display ? e.display() : "Could not load."
    return
  }
  const jobs = []
  if (info.value.can_transfer) jobs.push(myTransfers("mine", 30).then((r) => (recent.value = (r || []).slice(0, 5))))
  if (paperUser.value) jobs.push(myPapers("mine", 30).then((r) => (papers.value = (r || []).slice(0, 3))))
  try {
    await Promise.all(jobs)
  } catch (e) {
    error.value = e.display ? e.display() : "Could not load."
  }
})
</script>
