<template>
  <article class="rounded-xl border bg-surface p-3" :class="cardClass">
    <div class="flex items-start justify-between gap-2">
      <span class="flex flex-wrap items-center gap-1">
        <span class="rounded-full px-2 py-[2px] text-[13px] font-bold" :class="look.chip">{{ chipText }}</span>
        <span v-if="showPct" class="tnum rounded-full px-2 py-[2px] text-[13px] font-bold" :class="band(line.pct)">{{ line.pct }}%</span>
      </span>
      <span class="text-right text-[13px] text-ink-faint">Line {{ line.idx }}<template v-if="line.page > 1"> · page {{ line.page }}</template></span>
    </div>
    <p v-if="noteText" class="mt-1 text-[14px] font-semibold" :class="state === 'amber' ? 'text-warn-text' : state === 'red' ? 'text-danger-text' : 'text-ink-muted'">{{ noteText }}</p>

    <div class="mt-2 text-[13px] font-semibold uppercase tracking-wide text-ink-faint">On the paper</div>
    <div class="font-semibold" :class="state === 'left' ? 'text-ink-faint line-through' : ''">{{ line.text }}</div>
    <div v-if="paperBits" class="tnum text-[14px] text-ink-muted">{{ paperBits }}</div>

    <template v-if="line.item_code && state !== 'left'">
      <div class="mt-2 text-[13px] font-semibold uppercase tracking-wide text-ink-faint">Our item</div>
      <div class="font-semibold">{{ line.item_name }}</div>
      <div class="text-[13px] text-ink-faint">
        {{ line.item_code }}<template v-if="line.item_cls"> · Class {{ line.item_cls }}</template><template v-if="line.item_mrp"> · our MRP ₹{{ money0(line.item_mrp) }}</template>
      </div>
      <div v-if="buy && line.doc_row" class="tnum mt-1 text-[14px] font-semibold text-ok-text">
        ✓ {{ rowLabel }} · {{ rowDocShort }} line {{ line.doc_row.idx }} · {{ line.doc_row.doctype === "Purchase Receipt" ? "received" : "ordered" }} {{ fmt(line.doc_row.qty) }} · {{ line.doc_row.doctype === "Purchase Receipt" ? "to bill" : "due" }} {{ fmt(line.doc_row.due) }}
      </div>

      <div v-if="buy && line.off_doc && !line.doc_row" class="mt-1 text-[14px] font-semibold text-warn-text">
        Not on the linked {{ kind === "pi" ? "document" : "PO" }} — it goes in without a {{ kind === "pi" ? "row to match" : "PO row" }}
      </div>

      <!-- over-delivery: shown, not blocked (over-receipt allowance 1000%) -->
      <div v-if="buy && line.over && !confirmedOver" class="mt-2 rounded-lg border border-warn-text bg-warn-bg p-2 text-[14px] text-warn-text">
        <div class="font-bold">{{ fmt(line.over.total) }} on the paper · {{ fmt(line.over.due) }} due on the {{ rowDocShort }}</div>
        <div>{{ fmt(line.over.total - line.over.due) }} more than {{ line.doc_row.doctype === "Purchase Receipt" ? "received" : "ordered" }}. Allowed, but check the delivery.</div>
        <div v-if="!disabled" class="mt-2 flex gap-2">
          <button type="button" class="min-h-secondary flex-1 rounded-xl bg-brand-deep px-3 font-bold text-white" @click="$emit('ok')">Keep {{ fmt(line.qty) }}</button>
          <button type="button" class="min-h-secondary flex-1 rounded-xl border-2 border-brand-deep px-3 font-bold text-brand-deep" @click="$emit('qty', String(line.over.due))">Make it {{ fmt(line.over.due) }}</button>
        </div>
      </div>

      <!-- qty × rate ≠ the paper's amount: blocks until fixed -->
      <div v-if="buy && line.check" class="mt-2 rounded-lg border-2 border-danger-text bg-danger-bg p-2 text-[14px] text-danger-text">
        <div class="font-bold">Doesn't add up</div>
        <div class="tnum">Read {{ fmt(line.paper_qty) }} × ₹{{ money0(line.check.net_rate) }} = ₹{{ money0(line.check.expected) }} · paper's amount ₹{{ money0(line.check.amount) }}</div>
        <div v-if="line.check.fix_qty">₹{{ money0(line.check.amount) }} ÷ ₹{{ money0(line.check.net_rate) }} = {{ fmt(line.check.fix_qty) }}, so the quantity was probably misread.</div>
        <div v-if="!disabled" class="mt-2 flex gap-2">
          <button v-if="line.check.fix_qty" type="button" class="min-h-secondary flex-1 rounded-xl bg-brand-deep px-3 font-bold text-white" @click="$emit('fix')">Make it {{ fmt(line.check.fix_qty) }}</button>
          <button type="button" class="min-h-secondary flex-1 rounded-xl border-2 border-brand-deep px-3 font-bold text-brand-deep" @click="editing = !editing">Edit qty / rate</button>
        </div>
      </div>
      <div v-if="buy && editing" class="mt-2 grid grid-cols-3 gap-2 rounded-lg border border-surface-line p-2 text-[13px]">
        <label>Qty on paper<input v-model="ed.qty" type="number" inputmode="decimal" class="tnum mt-1 h-10 w-full rounded-lg border border-surface-line px-2 text-[15px]" /></label>
        <label>Rate on paper<input v-model="ed.rate" type="number" inputmode="decimal" class="tnum mt-1 h-10 w-full rounded-lg border border-surface-line px-2 text-[15px]" /></label>
        <label>Amount on paper<input v-model="ed.amount" type="number" inputmode="decimal" class="tnum mt-1 h-10 w-full rounded-lg border border-surface-line px-2 text-[15px]" /></label>
        <button type="button" class="col-span-3 min-h-secondary rounded-xl bg-brand-deep font-bold text-white" @click="saveRead">Use these numbers from the paper</button>
      </div>

      <div class="mt-2 flex flex-wrap items-center gap-2">
        <label class="sr-only" :for="`q${line.idx}`">Quantity</label>
        <input
          :id="`q${line.idx}`"
          :value="line.qty ?? ''"
          type="number"
          inputmode="decimal"
          min="0"
          placeholder="Qty"
          class="tnum h-11 w-24 rounded-lg border bg-surface text-center text-[17px] font-bold"
          :class="!line.qty ? 'border-danger-text' : 'border-surface-line'"
          :disabled="disabled"
          @change="(e) => $emit('qty', e.target.value)"
        />
        <select
          v-if="line.uoms && line.uoms.length > 1 && !(buy && line.doc_row)"
          :value="line.uom"
          class="h-11 rounded-lg border bg-surface px-2 font-semibold"
          :class="line.unit_known ? 'border-surface-line' : 'border-warn-text'"
          :disabled="disabled"
          aria-label="Unit"
          @change="(e) => $emit('uom', e.target.value)"
        >
          <option v-for="u in line.uoms" :key="u.uom" :value="u.uom">{{ u.uom }}{{ u.factor !== 1 ? ` (${u.factor} ${line.stock_uom})` : "" }}</option>
        </select>
        <span v-else class="font-semibold">{{ line.uom }}</span>
        <template v-if="buy">
          <span class="text-ink-faint">×</span>
          <label class="sr-only" :for="`r${line.idx}`">Rate</label>
          <span class="relative">
            <span class="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-ink-faint">₹</span>
            <input
              :id="`r${line.idx}`"
              :value="line.buy_rate ?? ''"
              type="number"
              inputmode="decimal"
              min="0"
              placeholder="Rate"
              class="tnum h-11 w-28 rounded-lg border bg-surface pl-6 pr-2 text-right text-[16px] font-bold"
              :class="!line.buy_rate ? 'border-danger-text' : line.rate_by_person ? 'border-brand-deep' : 'border-surface-line'"
              :disabled="disabled"
              @change="(e) => $emit('rate', e.target.value)"
            />
          </span>
          <b v-if="line.buy_rate && line.qty" class="tnum ml-auto">₹{{ money(line.buy_rate * line.qty) }}</b>
        </template>
        <span v-else-if="isPo && line.paper_rate && line.qty" class="tnum ml-auto text-right text-[14px]">
          × ₹{{ money(line.paper_rate) }}<br /><b>₹{{ money(line.paper_rate * line.qty) }}</b>
        </span>
      </div>
      <div v-if="buy" class="tnum mt-1 text-[13px] text-ink-faint">
        {{ rateSource }}<template v-if="line.doc_row && line.doc_row.rate && line.rate_src !== 'po' && line.rate_src !== 'pr'"> · {{ rowDocShort }} rate ₹{{ money(line.doc_row.rate) }}</template>
      </div>

      <!-- what we paid before: compared, never copied -->
      <button v-if="cmp" type="button" class="mt-2 block w-full border-t border-dashed border-surface-line pt-2 text-left text-[13px] text-ink-muted" @click="$emit('last')">
        Last bought · {{ fmtDate(cmp.prev.date) }} · {{ cmp.prev.supplier_name }} ›
        <b class="tnum text-ink">₹{{ money(cmp.prev.rate) }}</b><template v-if="cmp.prev.discount != null"> · {{ cmp.prev.discount }}% off ₹{{ money0(cmp.prev.list) }}</template>
        <span v-if="cmp.chips.length" class="mt-1 flex flex-wrap gap-1">
          <span v-for="(c, i) in cmp.chips" :key="i" class="rounded-full px-2 text-[12px] font-semibold" :class="c.info ? 'bg-surface-line text-ink-muted' : c.ok ? 'bg-ok-bg text-ok-text' : 'bg-warn-bg text-warn-text'">{{ c.ok && !c.info ? "✓ " : "" }}{{ c.text }}</span>
        </span>
      </button>
      <div v-else-if="isPo && usualDiscount && line.item_code" class="mt-2 border-t border-dashed border-surface-line pt-2 text-[13px] text-ink-faint">
        Never bought before · {{ partyTitle }} usually gives {{ usualDiscount.pct }}% off
      </div>
    </template>

    <div v-if="!disabled" class="mt-3 flex flex-wrap gap-2">
      <template v-if="state === 'amber'">
        <button v-if="line.item_code && line.can_keep" type="button" class="min-h-secondary flex-1 rounded-xl bg-brand-deep px-3 font-bold text-white" @click="$emit('ok')">Correct</button>
        <button type="button" class="min-h-secondary flex-1 rounded-xl border-2 border-brand-deep px-3 font-bold text-brand-deep" @click="$emit('change')">Change</button>
        <button type="button" class="min-h-secondary rounded-xl border border-surface-line px-3 font-semibold text-ink-muted" @click="$emit('leave')">Leave out</button>
      </template>
      <template v-else-if="state === 'red'">
        <button type="button" class="min-h-secondary flex-1 rounded-xl border-2 border-brand-deep px-3 font-bold text-brand-deep" @click="$emit('change')">
          {{ line.candidates && line.candidates.length ? "Choose the item" : "Search items" }}
        </button>
        <span class="self-center text-[13px] text-ink-faint">Left out if not chosen</span>
      </template>
      <template v-else-if="state === 'green'">
        <button type="button" class="min-h-secondary px-2 text-[14px] font-semibold text-brand-deep" @click="$emit('change')">Change</button>
        <button type="button" class="min-h-secondary px-2 text-[14px] font-semibold text-ink-muted" @click="$emit('leave')">Leave out</button>
      </template>
      <template v-else>
        <span class="flex-1 self-center text-[13px] text-ink-faint">{{ state === "left" ? leftText : `Will be remembered for ${partyTitle || "this party"}.` }}</span>
        <button type="button" class="min-h-secondary px-3 font-semibold text-brand-deep" @click="$emit('undo')">Undo</button>
      </template>
    </div>
  </article>
</template>

<script setup>
import { computed, reactive, ref } from "vue"

import { fmt, fmtDate } from "@/data/format.js"
import { band, lastCompare, money, money0 } from "@/data/paper.js"

const props = defineProps({
  line: { type: Object, required: true },
  isPo: { type: Boolean, default: true },
  kind: { type: String, default: "po" }, // po / so / pr / pi
  partyTitle: { type: String, default: "" },
  disabled: { type: Boolean, default: false },
  last: { type: Array, default: null },
  usualDiscount: { type: Object, default: null },
})
const emit = defineEmits(["ok", "change", "leave", "undo", "qty", "uom", "rate", "fix", "read", "last"])

const buy = computed(() => props.kind === "pr" || props.kind === "pi")
const editing = ref(false)
const ed = reactive({ qty: props.line.paper_qty ?? "", rate: props.line.rate ?? "", amount: props.line.amount ?? "" })
function saveRead() {
  editing.value = false
  emit("read", { read_qty: ed.qty === "" ? null : Number(ed.qty), read_rate: ed.rate === "" ? null : Number(ed.rate), read_amount: ed.amount === "" ? null : Number(ed.amount) })
}

const HOW = {
  alias_code: "Remembered by their code",
  alias_text: "Remembered from an earlier paper",
  barcode: "ISBN / barcode on the paper",
  item_code: "Our item code on the paper",
  party_code: "Their code, already in ERPNext",
  on_doc: "",
}

const state = computed(() => {
  const l = props.line
  if (l.decision === "left") return "left"
  if (l.decision === "ok" || l.by_person) return "confirmed"
  return l.colour || "red"
})
const confirmedOver = computed(() => props.line.decision === "ok" || props.line.by_person)

const LOOK = {
  green: { text: "Sure", chip: "bg-ok-bg text-ok-text", card: "border-surface-line" },
  confirmed: { text: "Confirmed", chip: "bg-ok-bg text-ok-text", card: "border-surface-line" },
  amber: { text: "To check", chip: "bg-warn-bg text-warn-text", card: "border-warn-text" },
  red: { text: "Not found", chip: "bg-danger-bg text-danger-text", card: "border-danger-text" },
  left: { text: "Left out", chip: "bg-surface-line text-ink-muted", card: "border-surface-line" },
}
const look = computed(() => LOOK[state.value])
const cardClass = computed(() => (buy.value && props.line.check && state.value !== "left" ? "border-2 border-danger-text" : look.value.card))
const rowDocShort = computed(() => (props.line.doc_row?.doctype === "Purchase Receipt" ? "Receipt" : "PO"))
const rowLabel = computed(() => props.line.doc_row?.parent || "")
const chipText = computed(() => {
  if (buy.value && props.line.doc_row && (state.value === "green" || state.value === "confirmed")) return `On the ${rowDocShort.value}`
  if (buy.value && props.line.check && state.value !== "left") return "Doesn't add up"
  return look.value.text
})
const showPct = computed(() => props.line.pct != null && state.value !== "left" && !(state.value === "red" && !props.line.item_code))

const noteText = computed(() => {
  const l = props.line
  if (state.value === "green") return HOW[l.how] ?? ""
  if (state.value === "amber" || state.value === "red") return l.note || ""
  return ""
})
const leftText = computed(() =>
  props.kind === "pi" ? "Left out — a Bill must carry every line." : buy.value ? "Not received here; its amount counts as left out." : "Listed for the office (not on the order)."
)

const paperBits = computed(() => {
  const l = props.line
  const out = []
  if (l.code) out.push(`Code ${l.code}`)
  if (l.isbn) out.push(`ISBN ${l.isbn}`)
  if (l.mrp) out.push(`MRP ${money0(l.mrp)}`)
  if (l.discount_percent) out.push(`${fmt(l.discount_percent)}% off`)
  if (l.rate) out.push(`rate ${money(l.rate)}`)
  if (l.paper_qty) out.push(`qty ${fmt(l.paper_qty)}${l.unit ? " " + l.unit : ""}`)
  else if (l.unit) out.push(l.unit)
  if (buy.value && l.amount) out.push(`amount ${money(l.amount)}`)
  return out.join(" · ")
})
const rateSource = computed(() => {
  const l = props.line
  if (!l.buy_rate) return "No rate on the paper — enter it (₹0 is not allowed)"
  return (
    {
      paper: "Rate from the paper (after its discount)",
      po: "No rate on the paper — the PO's rate is used",
      pr: "No rate on the paper — the Receipt's rate is used",
      person: "Rate entered by you",
    }[l.rate_src] || ""
  )
})
const cmp = computed(() => (props.kind === "so" ? null : lastCompare(props.line, props.last, buy.value)))
</script>
