<template>
  <div class="fixed inset-0 z-40 flex flex-col bg-surface-page">
    <AppHeader :title="`Save the ${isBill ? 'Bill' : 'Receipt'}`">
      <template #right>
        <button type="button" class="px-3 py-2 font-semibold text-brand-deep" :disabled="saving" @click="$emit('close')">Back</button>
      </template>
    </AppHeader>
    <div class="flex-1 space-y-3 overflow-y-auto p-4">
      <div v-if="pv && !pv.numbers.ok" class="rounded-xl border-2 border-danger-text bg-danger-bg p-3 font-bold text-danger-text">
        ✗ {{ shortText }}
      </div>

      <div class="rounded-xl border border-surface-line bg-surface p-3">
        <div class="text-[13px] font-semibold uppercase tracking-wide text-ink-faint">Supplier</div>
        <div class="text-[18px] font-bold">{{ paper.party_title }}</div>
        <div class="text-[14px] text-ink-muted">{{ linkText }}</div>
      </div>
      <label class="block">
        <span class="text-[14px] font-semibold text-ink-muted">{{ isBill && !addsStock ? "Warehouse (on the Receipt)" : "Into warehouse" }}</span>
        <select v-model="form.warehouse" class="mt-1 h-12 w-full rounded-lg border border-surface-line bg-surface px-2 font-semibold" @change="refresh">
          <option v-for="w in paper.save.warehouses" :key="w" :value="w">{{ w }}</option>
        </select>
      </label>
      <div class="grid grid-cols-2 gap-2">
        <label class="block">
          <span class="text-[14px] font-semibold text-ink-muted">{{ isBill ? "Bill date" : "Posting date" }}</span>
          <input v-if="isBill" v-model="form.posting_date" type="date" :max="paper.save.today" class="mt-1 h-12 w-full rounded-lg border border-surface-line bg-surface px-3" @change="refresh" />
          <span v-else class="mt-1 flex h-12 items-center rounded-lg border border-surface-line bg-surface-page px-3 font-semibold">{{ fmtDate(paper.save.posting_date) }}</span>
        </label>
        <label class="block">
          <span class="text-[14px] font-semibold text-ink-muted">Bill no.</span>
          <input v-model.trim="form.bill_no" type="text" maxlength="140" class="mt-1 h-12 w-full rounded-lg border border-surface-line bg-surface px-3 font-semibold" @change="refresh" />
        </label>
      </div>
      <p v-if="isBill && !paper.save.bill_date_read" class="text-[13px] font-semibold text-warn-text">The bill date could not be read — check it. The bill is posted on that date.</p>

      <div v-if="loading && !pv" class="space-y-2"><div class="skeleton h-32" /></div>
      <template v-if="pv">
        <dl class="tnum divide-y divide-surface-line rounded-xl border border-surface-line bg-surface">
          <div class="flex justify-between px-4 py-3"><dt class="text-ink-muted">Lines · qty</dt><dd class="font-bold">{{ pv.lines }} · {{ fmt(pv.qty) }}</dd></div>
          <div class="flex justify-between px-4 py-3"><dt class="text-ink-muted">Items</dt><dd class="font-semibold">₹{{ money(pv.numbers.items) }}</dd></div>
          <div class="flex justify-between px-4 py-3"><dt class="text-ink-muted">GST{{ pv.numbers.taxes_and_charges ? ` (${pv.numbers.taxes_and_charges})` : "" }}</dt><dd class="font-semibold">₹{{ money(pv.numbers.gst) }}</dd></div>
          <div v-if="pv.numbers.charges" class="flex justify-between px-4 py-3"><dt class="text-ink-muted">Freight / packing</dt><dd class="font-semibold">₹{{ money(pv.numbers.charges) }}</dd></div>
          <div v-if="pv.numbers.rounding" class="flex justify-between px-4 py-3"><dt class="text-ink-muted">Rounding</dt><dd>₹{{ money(pv.numbers.rounding) }}</dd></div>
          <div class="flex justify-between px-4 py-3"><dt class="font-bold">Our total</dt><dd class="font-bold">₹{{ money(pv.numbers.rounded_total) }}</dd></div>
          <div v-if="!isBill && pv.totals.explained" class="flex justify-between px-4 py-3"><dt class="text-ink-muted">Left out / not received</dt><dd>₹{{ money(pv.totals.explained) }}</dd></div>
          <div v-if="against" class="flex justify-between px-4 py-3"><dt class="text-ink-muted">{{ against.label }}</dt><dd class="font-bold">₹{{ money(against.amount) }}</dd></div>
          <div class="px-4 py-3 font-bold" :class="pv.numbers.ok ? 'text-ok-text' : 'text-danger-text'">
            {{ pv.numbers.ok ? (pv.totals.has_total || pv.numbers.paper_grand ? "✓ Adds up to the paper · all lines checked" : "✓ Every line checked (no total printed on the paper)") : `✗ ${shortText}` }}
          </div>
        </dl>

        <!-- charges printed on the bill: one tap each -->
        <section v-for="c in pv.totals.charges" :key="c.i" class="rounded-xl border bg-surface p-3" :class="charges.includes(c.i) ? 'border-surface-line' : isBill ? 'border-2 border-warn-text' : 'border-surface-line'">
          <div class="flex items-center justify-between gap-2">
            <div class="min-w-0">
              <div class="font-bold">{{ c.label }} ₹{{ money(c.amount) }}</div>
              <div class="text-[13px] text-ink-faint">
                <template v-if="isBill">Printed below the items — a charge, not an item line. Goes to {{ paper.freight_account || "the account set in Settings" }}.</template>
                <template v-else>Printed on the bill. A Receipt carries no freight: it goes on the Bill.</template>
              </div>
            </div>
            <button v-if="isBill" type="button" class="min-h-secondary flex-none rounded-xl px-3 font-bold" :class="charges.includes(c.i) ? 'border border-surface-line text-ink-muted' : 'bg-brand-deep text-white'" :disabled="loading || !paper.freight_account" @click="toggleCharge(c.i)">
              {{ charges.includes(c.i) ? "Remove" : `Add ₹${money0(c.amount)}` }}
            </button>
          </div>
        </section>
        <div v-for="m in pv.totals.missing_bill_lines" :key="'m' + m.idx" class="rounded-xl border-2 border-danger-text bg-danger-bg p-3 text-[14px] text-danger-text">
          <b>Line {{ m.idx }} · ₹{{ money(m.amount) }} not on this bill</b><br />"{{ m.text }}" is on the paper but left out. A Bill must carry every line: create the item, receive it, then come back.
        </div>

        <p v-if="dearer.n" class="rounded-lg bg-warn-bg p-3 text-[14px] text-warn-text">
          {{ dearer.n }} line{{ dearer.n === 1 ? " costs" : "s cost" }} more than last time: ₹{{ money0(Math.round(dearer.total)) }} in all ({{ dearer.names }}). Shown only — it doesn't stop the save.
        </p>
        <p v-if="pv.new_mrp.length" class="rounded-lg bg-brand-soft p-3 text-[14px]">
          {{ pv.new_mrp.length }} item{{ pv.new_mrp.length === 1 ? " has" : "s have" }} a new printed MRP (e.g. {{ pv.new_mrp[0].item_name }}: ₹{{ money0(pv.new_mrp[0].paper) }} on the paper, ₹{{ money0(pv.new_mrp[0].ours) }} in our list). Filled as "Printed MRP per Stock Unit"; the selling price changes when it is submitted.
        </p>
        <p v-if="addsStock !== null" class="text-[14px] text-ink-muted">{{ isBill ? (addsStock ? "Adds stock: on (no Receipt)" : "Adds stock: off — the Receipt already did") : "" }}</p>
        <div v-if="leftOut.length" class="rounded-xl border border-warn-text bg-warn-bg p-3 text-[14px] text-warn-text">
          <b>Left out ({{ leftOut.length }}):</b> {{ leftOut.map((l) => l.text).join("; ") }}. Written in the remarks for the office.
        </div>
        <div v-for="(d, i) in pv.draft_only" :key="'d' + i" class="rounded-lg border-2 border-warn-text bg-warn-bg p-3 text-[14px] font-semibold text-warn-text">{{ d }} — it can be saved as a draft only.</div>
      </template>

      <div v-if="dupInfo" class="rounded-xl border-2 border-warn-text bg-warn-bg p-3 text-warn-text">
        <div class="font-bold">This paper was already used</div>
        <p class="text-[14px]">It became {{ dupInfo.doc }} on {{ fmtDate(dupInfo.saved_on) }}. Save another anyway?</p>
        <button type="button" class="mt-2 min-h-secondary w-full rounded-xl border-2 border-warn-text font-bold" :disabled="saving" @click="save(lastSubmit, true)">Save anyway</button>
      </div>
      <div v-if="saveUnknown" class="rounded-xl border-2 border-warn-text bg-warn-bg p-3 text-warn-text">
        <div class="font-bold">Not sure it was saved</div>
        <p class="text-[14px]">The connection dropped. Tap <b>Check and finish</b> — if it was saved you will see it; it is never saved twice.</p>
      </div>
      <p v-if="error" class="rounded-lg bg-danger-bg p-3 font-semibold text-danger-text">{{ error }}</p>
    </div>
    <div class="safe-bottom space-y-2 border-t border-surface-line bg-surface px-4 pt-3">
      <template v-if="saveUnknown">
        <button type="button" class="min-h-action w-full rounded-xl bg-brand-deep text-[17px] font-bold text-white disabled:opacity-40" :disabled="saving" @click="save(lastSubmit, lastDup)">{{ saving ? "Checking…" : "Check and finish" }}</button>
      </template>
      <template v-else>
        <div class="grid grid-cols-2 gap-2">
          <button type="button" class="min-h-action rounded-xl border-2 border-brand-deep font-bold text-brand-deep disabled:opacity-40" :disabled="!canSave || saving" @click="save(false)">
            {{ saving && !lastSubmit ? "Saving…" : "Save draft" }}
          </button>
          <button type="button" class="min-h-action rounded-xl bg-brand-deep font-bold text-white disabled:opacity-40" :disabled="!canSubmit || saving" @click="save(true)">
            {{ saving && lastSubmit ? "Submitting…" : "Submit now" }}
          </button>
        </div>
        <p class="text-center text-[13px] text-ink-faint">{{ footText }}</p>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue"

import AppHeader from "@/components/AppHeader.vue"
import { newRef } from "@/data/draft.js"
import { fmt, fmtDate } from "@/data/format.js"
import { lastCompare, money, money0, previewPurchase, saveOrder } from "@/data/paper.js"

const props = defineProps({
  paper: { type: Object, required: true },
  kept: { type: Array, required: true },
  leftOut: { type: Array, required: true },
  queue: { type: Function, required: true }, // waits for the line changes still on their way
})
const emit = defineEmits(["close", "saved", "conflict"])

const isBill = computed(() => props.paper.purpose === "Purchase Invoice")
const form = reactive({ warehouse: props.paper.save.warehouse, posting_date: props.paper.save.posting_date, bill_no: props.paper.save.bill_no })
const charges = ref([])
const pv = ref(null)
const loading = ref(false)
const saving = ref(false)
const error = ref("")
const dupInfo = ref(null)
const saveUnknown = ref(false)
const lastSubmit = ref(false)
const lastDup = ref(false)
let clientRef = newRef()

const addsStock = computed(() => (isBill.value && pv.value ? !!pv.value.update_stock : null))
const linkText = computed(() => {
  const l = props.paper.links || {}
  if (l.mode === "docs") return `Linked to ${l.docs.join(", ")}`
  return isBill.value ? "Nothing linked — the bill adds the stock" : "No PO"
})
const against = computed(() => {
  const n = pv.value?.numbers
  if (!n) return null
  if (isBill.value && n.paper_grand) return { label: "Bill's grand total", amount: n.paper_grand }
  const t = pv.value.totals.against
  if (!t) return null
  return { label: t.kind === "items" ? "Paper's item total" : "Paper's total less tax and charges", amount: t.amount }
})
const shortText = computed(() => {
  const n = pv.value?.numbers
  if (!n) return ""
  if (pv.value.totals.missing_bill_lines.length) return `${pv.value.totals.missing_bill_lines.length} line(s) of the bill are missing`
  const d = Number(n.diff || 0)
  return `₹${money(Math.abs(d))} ${d < 0 ? "short of" : "more than"} the paper`
})
const canSave = computed(() => !!(pv.value && pv.value.numbers.ok) && !loading.value)
const canSubmit = computed(() => canSave.value && !(pv.value.draft_only || []).length)
const footText = computed(() => {
  if (!pv.value) return ""
  if (!pv.value.numbers.ok) return "Both stay off until the totals match."
  if ((pv.value.draft_only || []).length) return "Draft only — the office decides on it."
  if (isBill.value) return addsStock.value ? `Submit adds the stock to ${form.warehouse} and books the bill. Only the ERP can cancel it.` : "Submit books the bill. Only the ERP can cancel it."
  return `Submit adds ${fmt(pv.value.qty)} to ${form.warehouse}. Only the ERP can cancel it.`
})
const dearer = computed(() => {
  const lb = props.paper.last_bought || {}
  let n = 0
  let total = 0
  const names = []
  for (const l of props.kept) {
    const c = lastCompare(l, lb[l.item_code], true)
    if (c && c.dearer) {
      n++
      total += c.extra
      if (names.length < 2) names.push(l.item_name)
    }
  }
  return { n, total, names: names.join(", ") + (n > 2 ? "…" : "") }
})

let seq = 0
async function refresh() {
  const mine = ++seq
  loading.value = true
  error.value = ""
  try {
    await props.queue()
    const r = await previewPurchase({ name: props.paper.name, warehouse: form.warehouse, posting_date: form.posting_date, bill_no: form.bill_no, charges: charges.value })
    if (mine === seq) pv.value = r
  } catch (e) {
    if (mine === seq) {
      pv.value = null
      error.value = e && e.display ? e.display() : "Could not work out the totals."
    }
  } finally {
    if (mine === seq) loading.value = false
  }
}
function toggleCharge(i) {
  charges.value = charges.value.includes(i) ? charges.value.filter((x) => x !== i) : [...charges.value, i]
  refresh()
}
async function save(submit, allowDuplicate = false) {
  lastSubmit.value = !!submit
  lastDup.value = !!allowDuplicate
  saving.value = true
  error.value = ""
  try {
    await props.queue()
    const r = await saveOrder({
      name: props.paper.name,
      client_ref: clientRef,
      warehouse: form.warehouse,
      posting_date: form.posting_date,
      bill_no: form.bill_no,
      submit: submit ? 1 : 0,
      charges: charges.value,
      allow_duplicate: allowDuplicate ? 1 : 0,
      version: props.paper.version,
    })
    saveUnknown.value = false
    if (r.conflict) {
      emit("conflict", r.paper)
      return
    }
    if (r.ok === 0 && r.duplicate) {
      dupInfo.value = r.duplicate
      return
    }
    emit("saved", r)
  } catch (e) {
    if (e.excType === "Timeout" || e.excType === "NetworkError" || (e.status >= 500 && e.status !== 503)) saveUnknown.value = true
    else clientRef = newRef()
    error.value = e && e.display ? e.display() : "Could not save."
  } finally {
    saving.value = false
  }
}
onMounted(() => {
  // freight already printed and an account set: offered, never added by itself
  refresh()
})
</script>
