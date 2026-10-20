<template>
  <div>
    <AppHeader title="KGS Staff" logo />
    <main class="flex flex-col gap-[18px] px-4 pt-4">
      <div>
        <div class="text-[22px] font-bold leading-tight">{{ greeting }}<template v-if="firstName">, {{ firstName }}</template></div>
        <div class="mt-1 text-[14px] text-ink-faint">{{ today }}</div>
      </div>

      <div v-if="added.length" class="rounded-xl bg-ok-bg p-4 text-ok-text">
        <div class="text-[17px] font-bold">{{ $route.query.already ? "Already saved" : "Extra stock added" }} in {{ $route.query.to }}</div>
        <div class="text-[14px]">Nothing was in the system to transfer, so only the extra you counted was added.</div>
        <div v-for="r in added" :key="r.name" class="tnum text-[14px]">{{ r.name }} — stock value change ₹{{ Number(r.value).toLocaleString("en-IN", { minimumFractionDigits: 2 }) }}</div>
      </div>

      <div v-if="error" class="rounded-lg bg-danger-bg p-3 text-danger-text">{{ error }}</div>
      <div v-else-if="!info" class="space-y-3"><div class="skeleton h-[104px]" /><div class="skeleton h-[180px]" /></div>

      <template v-if="info">
        <router-link v-if="continueSub" to="/transfer" class="flex min-h-[64px] items-center gap-3 rounded-2xl bg-brand-deep px-3.5 py-2.5 text-white">
          <span class="flex h-10 w-10 flex-none items-center justify-center rounded-xl bg-brand"><Icon name="scan" :size="22" /></span>
          <span class="min-w-0 flex-1">
            <span class="block text-[16px] font-bold">Continue transfer</span>
            <span class="block truncate text-[13px] opacity-90">{{ continueSub }}</span>
          </span>
          <Icon name="chevron" :size="20" :stroke="2.2" class="flex-none" />
        </router-link>

        <section v-if="waiting.length" aria-labelledby="wait-h" class="overflow-hidden rounded-2xl border border-surface-line bg-surface pb-1">
          <h2 id="wait-h" class="px-4 pb-1 pt-3.5 text-[15px] font-bold">Waiting for you</h2>
          <div class="rows">
            <ListRow v-for="w in waiting" :key="w.key" :to="w.to" :href="w.href" :icon="w.icon" :tone="w.tone" :title="w.title" :sub="w.sub" />
          </div>
        </section>

        <section v-if="starts.length" aria-labelledby="start-h">
          <h2 id="start-h" class="mb-2.5 text-[15px] font-bold">Start</h2>
          <div class="grid grid-cols-2 gap-3">
            <router-link
              v-for="(s, i) in starts"
              :key="s.to"
              :to="s.to"
              class="rounded-2xl border border-surface-line bg-surface px-3.5 py-3 text-ink"
              :class="wide(i) ? 'col-span-2 flex min-h-[76px] items-center gap-3.5' : 'flex min-h-[104px] flex-col gap-2'"
            >
              <span class="flex flex-none items-center justify-center bg-brand-soft text-brand-deep" :class="wide(i) ? 'h-11 w-11 rounded-xl' : 'h-9 w-9 rounded-[10px]'">
                <Icon :name="s.icon" :size="wide(i) ? 22 : 20" />
              </span>
              <span :class="wide(i) ? 'min-w-0 flex-1' : ''">
                <span class="block font-bold" :class="wide(i) ? 'text-[16px]' : 'text-[15px]'">{{ s.title }}</span>
                <span class="block text-[13px] text-ink-faint">{{ s.sub }}</span>
              </span>
              <Icon v-if="wide(i)" name="chevron" :size="18" class="flex-none text-ink-faint" />
            </router-link>
          </div>
        </section>

        <section v-if="paperUser || info.can_transfer" aria-labelledby="recent-h">
          <div class="mb-2 flex items-baseline justify-between">
            <h2 id="recent-h" class="text-[15px] font-bold">{{ recentTitle }}</h2>
            <router-link v-if="seeAll" :to="seeAll" class="text-[14px] font-semibold text-brand-deep">See all</router-link>
          </div>
          <div v-if="!recent" class="skeleton h-[180px]" />
          <div v-else-if="!recent.length" class="rounded-2xl border border-dashed border-surface-line p-6 text-center text-[14px] text-ink-muted">
            Nothing in the last 30 days. What you start above shows up here.
          </div>
          <div v-else class="rows overflow-hidden rounded-2xl border border-surface-line bg-surface" :class="mixed ? '' : 'rows-flat'">
            <ListRow v-for="r in recent" :key="r.key" :to="r.to" :icon="mixed ? r.icon : ''" :icon-size="18" tone="mute" :title="r.title" :sub="r.sub">
              <template #right>
                <span v-if="r.chip" class="flex-none rounded-full px-2.5 py-0.5 text-[13px] font-bold" :class="r.chip.look">{{ r.chip.label }}</span>
                <span v-else class="tnum flex-none text-[14px] font-semibold text-ink-muted">{{ r.right }}</span>
              </template>
            </ListRow>
          </div>
        </section>
      </template>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"
import { useRoute } from "vue-router"

import AppHeader from "@/components/AppHeader.vue"
import Icon from "@/components/Icon.vue"
import ListRow from "@/components/ListRow.vue"
import { boot, myTransfers, poWaiting } from "@/data/api.js"
import { draft, loadDraft } from "@/data/draft.js"
import { fmtWhen, hhmm, shortWarehouse as short } from "@/data/format.js"
import { loadMyPapers, myRecentPapers, papersNotRead, papersToCheck } from "@/data/home.js"
import { PURPOSE, paperStatus, purposeKey } from "@/data/paper.js"

const route = useRoute()
const added = computed(() =>
  String(route.query.added || "").split(",").filter(Boolean).map((x) => ({ name: x.split(":")[0], value: x.split(":")[1] || 0 }))
)
const info = ref(null)
const transfers = ref(null)
const po = ref({})
const error = ref("")

const paper = computed(() => info.value?.paper || {})
const paperUser = computed(() => !!(paper.value.po || paper.value.so || paper.value.pr || paper.value.pi))
const mixed = computed(() => paperUser.value && !!info.value?.can_transfer)

// ── greeting ────────────────────────────────────────────────────────────────
const now = new Date()
const greeting = now.getHours() < 12 ? "Good morning" : now.getHours() < 17 ? "Good afternoon" : "Good evening"
const today = `${now.toLocaleDateString("en-GB", { weekday: "long" })}, ${now.getDate()} ${now.toLocaleDateString("en-GB", { month: "long" })}`
const firstName = computed(() => String(info.value?.full_name || "").trim().split(/\s+/)[0] || "")

// ── continue a transfer left on this phone ─────────────────────────────────
const continueSub = computed(() => {
  const n = draft.lines.length
  if (!info.value?.can_transfer || !n) return ""
  const where = draft.from && draft.to ? ` · ${short(draft.from)} → ${short(draft.to)}` : ""
  return `${n} item${n === 1 ? "" : "s"} scanned${where}`
})

// ── waiting for you ─────────────────────────────────────────────────────────
const partyOf = (p) => p.party_title || PURPOSE[purposeKey(p.purpose)].title
function names(list) {
  const uniq = [...new Set(list.map(partyOf))]
  return uniq.slice(0, 3).join(" · ") + (uniq.length > 3 ? ` +${uniq.length - 3}` : "")
}
function oldest(d, t) {
  return d === 0 ? `oldest sent ${t}` : d === 1 ? "oldest from yesterday" : `oldest ${d} days`
}
function sent(d, t) {
  return d === 0 ? `sent ${t}` : d === 1 ? "sent yesterday" : `waiting ${d} days`
}
const waiting = computed(() => {
  const out = []
  const a = po.value.approve
  if (a && a.count) {
    const by = a.by || []
    out.push({
      key: "approve",
      href: a.url,
      icon: "approve",
      tone: "brand",
      title: `${a.count} Purchase Order${a.count === 1 ? "" : "s"} to approve`,
      sub:
        a.count === 1 && by.length
          ? `${by[0].name} · ${sent(a.since_days, a.since_time)}`
          : [...by.map((b) => `${b.name} ${b.n}`), oldest(a.since_days, a.since_time)].join(" · "),
    })
  }
  const check = papersToCheck.value
  if (check.length) {
    const one = check.length === 1 ? check[0] : null
    out.push({
      key: "check",
      to: one ? `/paper/${encodeURIComponent(one.name)}` : "/papers?status=Ready",
      icon: "eye",
      tone: "warn",
      title: `${check.length} paper${check.length === 1 ? "" : "s"} to check`,
      sub: one ? `${partyOf(one)} · ${PURPOSE[purposeKey(one.purpose)].title}` : names(check),
    })
  }
  const failed = papersNotRead.value
  if (failed.length) {
    const one = failed.length === 1 ? failed[0] : null
    out.push({
      key: "failed",
      to: one ? `/paper/${encodeURIComponent(one.name)}` : "/papers?status=Failed",
      icon: "alert",
      tone: "danger",
      title: one ? "1 paper could not be read" : `${failed.length} papers could not be read`,
      sub: one ? `${partyOf(one)} · tap to read again` : names(failed),
    })
  }
  const m = po.value.mine
  if (m && m.count) {
    const d = m.since_days
    out.push({
      key: "mine",
      href: m.url,
      icon: "clock",
      tone: "mute",
      title: m.count === 1 ? "Your PO waits for approval" : `${m.count} of your POs wait for approval`,
      sub: "With the owners " + (d === 0 ? `since ${m.since_time}` : d === 1 ? "since yesterday" : `for ${d} days`),
    })
  }
  return out
})

// ── start something ────────────────────────────────────────────────────────
const starts = computed(() => {
  const p = paper.value
  const out = []
  if (p.po) out.push({ to: "/paper?for=po", icon: "po", title: "Purchase Order", sub: "Photo of a quotation" })
  if (p.pr) out.push({ to: "/paper?for=pr", icon: "receipt", title: "Receipt", sub: "Goods have arrived" })
  if (p.pi) out.push({ to: "/paper?for=pi", icon: "bill", title: "Bill", sub: "Supplier's bill" })
  if (p.so) out.push({ to: "/paper?for=so", icon: "so", title: "Sales Order", sub: "School book list" })
  if (info.value?.can_transfer) {
    out.push(out.length ? { to: "/transfer", icon: "transfer", title: "Transfer", sub: "Move stock" } : { to: "/transfer", icon: "transfer", title: "New transfer", sub: "Scan items and move stock" })
  }
  return out
})
// a lone tile, or the last of an odd number, runs the full width
const wide = (i) => starts.value.length === 1 || (starts.value.length % 2 === 1 && i === starts.value.length - 1)

// ── recent: papers and transfers in one list ───────────────────────────────
const recentTitle = computed(() => (mixed.value ? "Recent" : paperUser.value ? "Your recent papers" : "Your recent transfers"))
// with both kinds, the Papers and Transfers tabs below are the "see all"
const seeAll = computed(() => (mixed.value ? "" : paperUser.value ? "/papers" : "/transfers"))
const recent = computed(() => {
  const papers = paperUser.value ? myRecentPapers.value : []
  const moves = info.value?.can_transfer ? transfers.value : []
  if (papers === null || moves === null) return null
  const rows = []
  for (const p of papers) {
    if (p.status === "Discarded") continue
    const kind = PURPOSE[purposeKey(p.purpose)].title
    rows.push({
      key: "p:" + p.name,
      at: String(p.creation || ""),
      to: `/paper/${encodeURIComponent(p.name)}`,
      icon: "file",
      title: p.party_title || "Supplier not chosen yet",
      // kind + time only: numbers do not fit beside the chip on a phone (they are on the paper)
      sub: `${kind} · ${fmtWhen(p.creation)}`,
      chip: paperStatus(p.status),
    })
  }
  for (const t of moves) {
    const lines = Number(t.line_count || 0)
    rows.push({
      key: "t:" + t.name,
      at: String(t.creation || `${t.posting_date} ${t.posting_time}`),
      to: `/t/${encodeURIComponent(t.name)}`,
      icon: "transfer",
      title: `${short(t.from_warehouse)} → ${short(t.to_warehouse)}`,
      sub: `${mixed.value ? "Transfer" : t.name} · ${fmtWhen(`${t.posting_date} ${hhmm(t.posting_time)}`)}`,
      chip: t.docstatus === 0 ? { label: "Draft", look: "bg-warn-bg text-warn-text" } : t.docstatus === 2 ? { label: "Cancelled", look: "bg-danger-bg text-danger-text" } : null,
      right: `${lines} line${lines === 1 ? "" : "s"}`,
    })
  }
  return rows.sort((a, b) => b.at.localeCompare(a.at)).slice(0, 5)
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
  if (info.value.can_transfer) jobs.push(myTransfers("mine", 30).then((r) => (transfers.value = r || [])))
  if (paperUser.value) jobs.push(loadMyPapers(5000))
  // the approval rows are extra: Home works without them
  poWaiting()
    .then((r) => (po.value = r || {}))
    .catch(() => {})
  try {
    await Promise.all(jobs)
  } catch (e) {
    error.value = e.display ? e.display() : "Could not load."
  }
})
</script>
