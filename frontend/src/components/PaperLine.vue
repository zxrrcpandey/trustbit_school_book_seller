<template>
  <article class="rounded-xl border bg-surface p-3" :class="look.card">
    <div class="flex items-start justify-between gap-2">
      <span class="rounded-full px-2 py-[2px] text-[13px] font-bold" :class="look.chip">{{ look.text }}</span>
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
        {{ line.item_code }}<template v-if="line.item_cls"> · Class {{ line.item_cls }}</template><template v-if="line.item_mrp"> · MRP ₹{{ money(line.item_mrp) }}</template>
      </div>
      <div class="mt-2 flex items-center gap-2">
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
          v-if="line.uoms && line.uoms.length > 1"
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
        <span v-if="isPo && line.paper_rate && line.qty" class="tnum ml-auto text-right text-[14px]">
          × ₹{{ money(line.paper_rate) }}<br /><b>₹{{ money(line.paper_rate * line.qty) }}</b>
        </span>
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
        <span class="flex-1 self-center text-[13px] text-ink-faint">{{ state === "left" ? "Listed for the office (not on the order)." : `Will be remembered for ${partyTitle || "this party"}.` }}</span>
        <button type="button" class="min-h-secondary px-3 font-semibold text-brand-deep" @click="$emit('undo')">Undo</button>
      </template>
    </div>
  </article>
</template>

<script setup>
import { computed } from "vue"

import { fmt } from "@/data/format.js"
import { money } from "@/data/paper.js"

const props = defineProps({
  line: { type: Object, required: true },
  isPo: { type: Boolean, default: true },
  partyTitle: { type: String, default: "" },
  disabled: { type: Boolean, default: false },
})
defineEmits(["ok", "change", "leave", "undo", "qty", "uom"])

const HOW = {
  alias_code: "Remembered by their code",
  alias_text: "Remembered from an earlier paper",
  barcode: "ISBN / barcode on the paper",
  item_code: "Our item code on the paper",
  party_code: "Their code, already in ERPNext",
}

const state = computed(() => {
  const l = props.line
  if (l.decision === "left") return "left"
  if (l.decision === "ok" || l.by_person) return "confirmed"
  return l.colour || "red"
})

const LOOK = {
  green: { text: "Sure", chip: "bg-ok-bg text-ok-text", card: "border-surface-line" },
  confirmed: { text: "Confirmed", chip: "bg-ok-bg text-ok-text", card: "border-surface-line" },
  amber: { text: "To check", chip: "bg-warn-bg text-warn-text", card: "border-warn-text" },
  red: { text: "Not found", chip: "bg-danger-bg text-danger-text", card: "border-danger-text" },
  left: { text: "Left out", chip: "bg-surface-line text-ink-muted", card: "border-surface-line" },
}
const look = computed(() => LOOK[state.value])

const noteText = computed(() => {
  const l = props.line
  if (state.value === "green") return HOW[l.how] || ""
  if (state.value === "amber" || state.value === "red") return l.note || ""
  return ""
})

const paperBits = computed(() => {
  const l = props.line
  const out = []
  if (l.code) out.push(`Code ${l.code}`)
  if (l.isbn) out.push(`ISBN ${l.isbn}`)
  if (l.mrp) out.push(`MRP ${money(l.mrp)}`)
  if (l.discount_percent) out.push(`${fmt(l.discount_percent)}% off`)
  if (l.rate) out.push(`rate ${money(l.rate)}`)
  if (l.paper_qty) out.push(`qty ${fmt(l.paper_qty)}${l.unit ? " " + l.unit : ""}`)
  else if (l.unit) out.push(l.unit)
  return out.join(" · ")
})
</script>
