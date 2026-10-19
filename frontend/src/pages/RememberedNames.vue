<template>
  <div>
    <AppHeader title="Remembered names" :back="party ? false : '/home'">
      <template v-if="party" #right>
        <button type="button" class="px-3 py-2 font-semibold text-brand-deep" @click="party = null">All {{ partyType === "Supplier" ? "suppliers" : "customers" }}</button>
      </template>
    </AppHeader>
    <main class="space-y-3 p-4">
      <p class="text-[14px] text-ink-muted">
        Saved when someone confirms a line. If one is wrong, change or delete it here and the next paper uses the fix.
        Only Purchase Managers (suppliers) and Sales Managers (customers) can change them.
      </p>
      <div v-if="types.length > 1" class="grid grid-cols-2 gap-1 rounded-xl bg-surface-line p-1">
        <button v-for="t in types" :key="t" type="button" class="min-h-secondary rounded-lg font-semibold" :class="partyType === t ? 'bg-surface' : 'text-ink-muted'" @click="partyType = t">
          {{ t === "Supplier" ? "Suppliers" : "Customers" }}
        </button>
      </div>
      <p v-if="error" class="rounded-lg bg-danger-bg p-3 text-danger-text">{{ error }}</p>

      <!-- choose a party -->
      <template v-if="!party">
        <input v-model="partyTxt" type="search" :placeholder="`Search ${partyType === 'Supplier' ? 'suppliers' : 'customers'}`" class="w-full rounded-lg border border-surface-line bg-surface p-3" aria-label="Search" />
        <div v-if="!parties" class="space-y-2"><div v-for="i in 4" :key="i" class="skeleton h-14" /></div>
        <p v-else-if="!parties.length" class="p-6 text-center text-ink-muted">No remembered names yet. They appear after the first order from a paper.</p>
        <button v-for="p in parties || []" :key="p.party" type="button" class="flex w-full items-center justify-between gap-3 rounded-xl border border-surface-line bg-surface p-3 text-left" @click="openParty(p)">
          <span class="min-w-0"><span class="block font-semibold">{{ p.title || p.party }}</span><span class="block text-[13px] text-ink-faint">last {{ fmtDate(p.last) }}</span></span>
          <span class="tnum flex-none text-[14px] font-semibold text-ink-muted">{{ p.names }} name{{ p.names === 1 ? "" : "s" }}</span>
        </button>
      </template>

      <!-- names of one party -->
      <template v-else>
        <div class="rounded-xl border border-surface-line bg-surface p-3">
          <div class="text-[13px] font-semibold uppercase tracking-wide text-ink-faint">{{ partyType }}</div>
          <div class="text-[18px] font-bold">{{ party.title || party.party }}</div>
        </div>
        <input v-model="txt" type="search" placeholder="Search the names" class="w-full rounded-lg border border-surface-line bg-surface p-3" aria-label="Search the names" />
        <div v-if="!rows" class="space-y-2"><div v-for="i in 4" :key="i" class="skeleton h-20" /></div>
        <p v-else-if="!rows.length" class="p-6 text-center text-ink-muted">Nothing found.</p>
        <article v-for="r in rows || []" :key="r.name" class="rounded-xl border border-surface-line bg-surface p-3">
          <div class="flex items-start justify-between gap-2">
            <span class="rounded-full bg-surface-line px-2 text-[13px] font-semibold text-ink-muted">{{ r.key_type === "Code" ? "Their code" : "Their wording" }}</span>
            <span class="text-[13px] text-ink-faint">used {{ r.times_used }}×</span>
          </div>
          <div class="mt-1 font-semibold">{{ r.paper_text }}</div>
          <div class="text-[14px]">→ <b :class="r.disabled ? 'text-danger-text' : ''">{{ r.item_name || r.item_code }}</b><span v-if="r.disabled" class="text-danger-text"> (disabled)</span></div>
          <div class="text-[13px] text-ink-faint">{{ r.item_code }}<template v-if="r.uom"> · {{ r.uom }}</template><template v-if="r.mrp"> · paper MRP ₹{{ money(r.mrp) }}</template> · {{ r.last_used_by_name }} {{ fmtDate(r.last_used_on) }}</div>
          <div v-if="canEdit" class="mt-2 flex gap-2">
            <button type="button" class="min-h-secondary flex-1 rounded-xl border-2 border-brand-deep font-bold text-brand-deep" :disabled="busy" @click="changing = r">Change item</button>
            <button type="button" class="min-h-secondary rounded-xl border border-danger-text px-4 font-bold text-danger-text" :disabled="busy" @click="remove(r)">Delete</button>
          </div>
        </article>
        <button v-if="rows && rows.length && rows.length % 50 === 0" type="button" class="min-h-secondary w-full rounded-xl border border-surface-line bg-surface font-semibold text-brand-deep" @click="more">Show more</button>
      </template>
    </main>
    <ChooseItemSheet v-if="changing" :line="null" :allow-leave="false" :current="changing.item_code" @pick="pickItem" @close="changing = null" />
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from "vue"

import AppHeader from "@/components/AppHeader.vue"
import ChooseItemSheet from "@/components/ChooseItemSheet.vue"
import { boot } from "@/data/api.js"
import { fmtDate } from "@/data/format.js"
import { aliasParties, changeAlias, deleteAlias, listAliases, money } from "@/data/paper.js"

const types = ref(["Supplier"])
const partyType = ref("Supplier")
const partyTxt = ref("")
const parties = ref(null)
const party = ref(null)
const txt = ref("")
const rows = ref(null)
const canEdit = ref(false)
const error = ref("")
const busy = ref(false)
const changing = ref(null)
const msg = (e, f) => (e && e.display ? e.display() : f)

async function loadParties() {
  parties.value = null
  error.value = ""
  try {
    const r = await aliasParties(partyType.value, partyTxt.value.trim())
    parties.value = r.parties || []
    canEdit.value = !!r.can_edit
  } catch (e) {
    error.value = msg(e, "Could not load.")
    parties.value = []
  }
}
async function loadRows(append = false) {
  if (!append) rows.value = null
  error.value = ""
  try {
    const r = await listAliases(partyType.value, party.value.party, txt.value.trim(), append ? rows.value.length : 0)
    rows.value = append ? [...rows.value, ...(r.rows || [])] : r.rows || []
    canEdit.value = !!r.can_edit
  } catch (e) {
    error.value = msg(e, "Could not load.")
    if (!append) rows.value = []
  }
}
const more = () => loadRows(true)
function openParty(p) {
  party.value = p
  txt.value = ""
  loadRows()
}

let t1 = null
watch(partyTxt, () => {
  clearTimeout(t1)
  t1 = setTimeout(loadParties, 350)
})
let t2 = null
watch(txt, () => {
  clearTimeout(t2)
  t2 = setTimeout(() => party.value && loadRows(), 350)
})
watch(partyType, () => {
  party.value = null
  loadParties()
})

async function pickItem(itemCode) {
  const r = changing.value
  changing.value = null
  busy.value = true
  try {
    const res = await changeAlias(r.name, itemCode)
    r.item_code = res.item_code
    r.item_name = res.item_name
    r.disabled = 0
    r.times_used = 1
  } catch (e) {
    error.value = msg(e, "Could not change it.")
  } finally {
    busy.value = false
  }
}
async function remove(r) {
  if (!window.confirm(`Forget "${r.paper_text}" → ${r.item_name || r.item_code}?`)) return
  busy.value = true
  try {
    await deleteAlias(r.name)
    rows.value = rows.value.filter((x) => x.name !== r.name)
  } catch (e) {
    error.value = msg(e, "Could not delete it.")
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  try {
    const p = (await boot()).paper || {}
    const t = []
    if (p.po) t.push("Supplier")
    if (p.so) t.push("Customer")
    types.value = t.length ? t : ["Supplier"]
    partyType.value = types.value[0]
  } catch {
    /* defaults */
  }
  loadParties()
})
</script>
