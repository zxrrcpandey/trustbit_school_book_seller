<template>
  <div data-reco class="space-y-2 rounded-xl border-2 border-warn-text bg-surface p-3">
    <div>
      <div class="font-bold leading-snug">{{ info.item_name }}</div>
      <div class="text-[13px] text-ink-faint">{{ info.item_code }}</div>
    </div>
    <div class="tnum grid grid-cols-2 gap-x-3 text-[14px]">
      <span class="text-ink-muted">System has in {{ from }}</span><b :class="info.current_qty < 0 ? 'text-danger-text' : ''">{{ fmt(info.current_qty) }} {{ info.stock_uom }}</b>
      <span class="text-ink-muted">You are moving</span><b>{{ fmt(needed) }} {{ info.stock_uom }}</b>
    </div>
    <p v-for="w in calc.warnings" :key="w" class="rounded-lg bg-danger-bg px-3 py-2 text-[15px] font-bold text-danger-text">{{ w }}</p>

    <label class="block text-[14px] font-semibold text-ink-muted">
      How many are really in {{ from }} now? ({{ info.stock_uom }})
      <input :value="model.counted" type="number" inputmode="decimal" min="0" class="tnum mt-1 h-12 w-full rounded-lg border border-surface-line text-center text-[18px] font-bold text-ink" @input="set('counted', num($event.target.value))" />
    </label>
    <p v-for="n in calc.notes" :key="n" class="text-[14px] font-semibold text-warn-text">{{ n }}</p>

    <template v-if="calc.reconciles">
      <label class="block text-[14px] font-semibold text-ink-muted">
        Price of 1 {{ info.stock_uom }} for the extra {{ fmt(calc.extra) }} (₹)
        <input :value="model.rate" type="number" inputmode="decimal" min="0" step="0.01" class="tnum mt-1 h-12 w-full rounded-lg border border-surface-line text-center text-[18px] font-bold text-ink" @input="set('rate', num($event.target.value))" />
      </label>
      <p class="text-[13px] text-ink-faint">
        <template v-if="info.rate_source === 'last purchase rate'">Filled from the last purchase price.</template>
        <template v-else-if="info.rate_source">Filled from the current stock value.</template>
        <template v-else>No old price found — please type the buying price.</template>
        <template v-if="info.last_purchase_rate"> Last purchase price: ₹{{ money(info.last_purchase_rate) }}.</template>
      </p>
      <p v-if="farFromLpr" class="rounded-lg bg-warn-bg px-3 py-2 text-[14px] font-semibold text-warn-text">
        ⚠ This price is very different from the last purchase price (₹{{ money(info.last_purchase_rate) }}). Please check.
      </p>
      <label class="block text-[14px] font-semibold text-ink-muted">
        Reason
        <select :value="model.reason" class="mt-1 h-12 w-full rounded-lg border border-surface-line bg-surface px-2 font-semibold text-ink" @change="set('reason', $event.target.value)">
          <option value="" disabled>Choose a reason</option>
          <option v-for="r in reasons" :key="r" :value="r">{{ r }}</option>
        </select>
      </label>
      <p v-if="model.reason === 'Purchase receipt not entered'" class="rounded-lg bg-warn-bg px-3 py-2 text-[14px] font-semibold text-warn-text">
        ⚠ When this bill's Purchase Receipt is entered later, this stock will count twice. Tell the office.
      </p>
      <input v-if="model.reason" :value="model.note" maxlength="200" :placeholder="model.reason === 'Other' ? 'What happened? (required)' : 'Note (optional)'" class="w-full rounded-lg border border-surface-line bg-surface p-3" @input="set('note', $event.target.value)" />
      <div class="tnum rounded-lg bg-surface-page px-3 py-2 text-[14px]">
        Added in {{ to }}: <b>{{ fmt(calc.extra) }} {{ info.stock_uom }}</b> · Stock value change: <b :class="calc.effect >= 0 ? 'text-ink' : 'text-danger-text'">₹{{ money(calc.effect) }}</b>
      </div>
    </template>
    <p v-if="calc.error" class="text-[14px] font-semibold text-danger-text">{{ calc.error }}</p>
  </div>
</template>

<script setup>
import { computed } from "vue"

import { fmt } from "@/data/format.js"
import { money, recoCalc } from "@/data/reco.js"

// model: {counted, rate, reason, note} — owned by the page, edited here.
const props = defineProps({
  info: { type: Object, required: true },
  needed: { type: Number, required: true },
  model: { type: Object, required: true },
  reasons: { type: Array, default: () => [] },
  from: { type: String, default: "" },
  to: { type: String, default: "" },
  whole: { type: Boolean, default: false },
})
const emit = defineEmits(["update"])

const num = (v) => (v === "" ? "" : Number(v))
const set = (k, v) => emit("update", { ...props.model, [k]: v })
const calc = computed(() => recoCalc(props.info, props.needed, props.model, props.whole, props.from, props.to))
const farFromLpr = computed(() => {
  const l = props.info.last_purchase_rate
  const r = Number(props.model.rate || 0)
  return l > 0 && r > 0 && Math.abs(r - l) / l > 0.5
})
</script>
