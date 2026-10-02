<template>
  <div data-reco class="space-y-2 rounded-xl border-2 border-warn-text bg-surface p-3">
    <div>
      <div class="font-bold leading-snug">{{ info.item_name }}</div>
      <div class="text-[13px] text-ink-faint">{{ info.item_code }}</div>
    </div>
    <div class="tnum grid grid-cols-2 gap-x-3 text-[14px]">
      <span class="text-ink-muted">System has</span><b :class="info.current_qty < 0 ? 'text-danger-text' : ''">{{ fmt(info.current_qty) }} {{ info.stock_uom }}</b>
      <span class="text-ink-muted">Transfer needs</span><b>{{ fmt(needed) }} {{ info.stock_uom }}</b>
    </div>

    <label class="block text-[14px] font-semibold text-ink-muted">
      Physically in {{ from }} now ({{ info.stock_uom }})
      <input :value="model.counted" type="number" inputmode="decimal" min="0" class="tnum mt-1 h-12 w-full rounded-lg border border-surface-line text-center text-[18px] font-bold text-ink" @input="set('counted', num($event.target.value))" />
    </label>
    <p v-if="model.counted !== '' && model.counted <= info.current_qty" class="text-[14px] font-semibold text-warn-text">
      Not more than the system already has — no reconciliation; this item's transfer will be reduced to {{ fmt(Math.max(0, info.current_qty)) }} {{ info.stock_uom }}.
    </p>
    <p v-else-if="model.counted !== '' && model.counted < needed" class="text-[14px] font-semibold text-warn-text">
      Less than the transfer needs — this item's transfer will be reduced to {{ fmt(model.counted) }} {{ info.stock_uom }}.
    </p>

    <template v-if="reconciles">
      <label class="block text-[14px] font-semibold text-ink-muted">
        Rate per {{ info.stock_uom }} for the extra {{ fmt(extra) }} (₹)
        <input :value="model.rate" type="number" inputmode="decimal" min="0" step="0.01" class="tnum mt-1 h-12 w-full rounded-lg border border-surface-line text-center text-[18px] font-bold text-ink" @input="set('rate', num($event.target.value))" />
      </label>
      <p class="text-[13px] text-ink-faint">
        <template v-if="info.rate_source">Prefilled from the {{ info.rate_source }}.</template>
        <template v-else>No purchase rate or valuation on record — type the cost price.</template>
        <template v-if="info.last_purchase_rate"> Last purchase rate ₹{{ money(info.last_purchase_rate) }}.</template>
      </p>
      <p v-if="farFromLpr" class="rounded-lg bg-warn-bg px-3 py-2 text-[14px] font-semibold text-warn-text">
        This rate is more than 50% away from the last purchase rate (₹{{ money(info.last_purchase_rate) }}). Check it.
      </p>
      <label class="block text-[14px] font-semibold text-ink-muted">
        Reason
        <select :value="model.reason" class="mt-1 h-12 w-full rounded-lg border border-surface-line bg-surface px-2 font-semibold text-ink" @change="set('reason', $event.target.value)">
          <option value="" disabled>Choose a reason</option>
          <option v-for="r in reasons" :key="r" :value="r">{{ r }}</option>
        </select>
      </label>
      <p v-if="model.reason === 'Purchase receipt not entered'" class="rounded-lg bg-warn-bg px-3 py-2 text-[14px] font-semibold text-warn-text">
        When that Purchase Receipt is entered later, this stock will be counted twice — tell the office to adjust it then.
      </p>
      <input v-if="model.reason" :value="model.note" maxlength="200" :placeholder="model.reason === 'Other' ? 'What happened? (required)' : 'Note (optional)'" class="w-full rounded-lg border border-surface-line bg-surface p-3" @input="set('note', $event.target.value)" />
      <div class="tnum rounded-lg bg-surface-page px-3 py-2 text-[14px]">
        Stock value change: <b :class="effect >= 0 ? 'text-ink' : 'text-danger-text'">₹{{ money(effect) }}</b>
        <span class="text-ink-faint"> (to Stock Adjustment)</span>
      </div>
    </template>
    <p v-if="error" class="text-[14px] font-semibold text-danger-text">{{ error }}</p>
  </div>
</template>

<script setup>
import { computed } from "vue"

import { fmt } from "@/data/format.js"

// model: {counted, rate, reason, note} — owned by the page, edited here.
const props = defineProps({
  info: { type: Object, required: true },
  needed: { type: Number, required: true },
  model: { type: Object, required: true },
  reasons: { type: Array, default: () => [] },
  from: { type: String, default: "" },
  whole: { type: Boolean, default: false },
})
const emit = defineEmits(["update"])

const num = (v) => (v === "" ? "" : Number(v))
const set = (k, v) => emit("update", { ...props.model, [k]: v })
const money = (n) => Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })

const reconciles = computed(() => props.model.counted !== "" && props.model.counted > props.info.current_qty)
const extra = computed(() => (reconciles.value ? props.model.counted - props.info.current_qty : 0))
// mirrors the server: existing units keep their value, the extra gets the rate
const effect = computed(() => {
  const r = Number(props.model.rate || 0)
  const q0 = props.info.current_qty
  const v0 = props.info.current_value
  return q0 > 0 && v0 > 0 ? extra.value * r : props.model.counted * r - v0
})
const farFromLpr = computed(() => {
  const l = props.info.last_purchase_rate
  const r = Number(props.model.rate || 0)
  return l > 0 && r > 0 && Math.abs(r - l) / l > 0.5
})
const error = computed(() => {
  const m = props.model
  if (m.counted === "" || m.counted < 0) return "Enter the count."
  if (props.whole && !Number.isInteger(m.counted)) return `${props.info.stock_uom} must be a whole number.`
  if (!reconciles.value) return ""
  if (!(Number(m.rate) > 0)) return "Enter a rate above zero."
  if (!m.reason) return "Choose a reason."
  if (m.reason === "Other" && !String(m.note || "").trim()) return "Write what happened."
  return ""
})
defineExpose({ error, reconciles, effect })
</script>
