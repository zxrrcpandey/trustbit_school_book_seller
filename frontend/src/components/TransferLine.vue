<template>
  <div class="rounded-xl border bg-surface p-3" :class="problem ? 'border-danger-text' : warning ? 'border-warn-text' : 'border-surface-line'">
    <div class="flex items-start justify-between gap-2">
      <div class="min-w-0">
        <div class="font-semibold leading-snug">{{ line.item_name }}</div>
        <div class="text-[13px] text-ink-faint">{{ line.item_code }}</div>
      </div>
      <button type="button" class="-mr-1 -mt-1 flex h-10 w-10 flex-none items-center justify-center rounded-full text-xl text-ink-faint" aria-label="Remove item" @click="$emit('remove')">×</button>
    </div>

    <div class="mt-2 flex items-center gap-2">
      <button type="button" class="h-12 w-12 flex-none rounded-lg border border-surface-line text-2xl font-bold" aria-label="One less" @click="step(-1)">−</button>
      <input
        :value="line.qty"
        type="number"
        inputmode="decimal"
        min="0"
        class="tnum h-12 w-20 min-w-0 rounded-lg border border-surface-line text-center text-[18px] font-bold"
        aria-label="Quantity"
        @input="setQty($event.target.value)"
      />
      <button type="button" class="h-12 w-12 flex-none rounded-lg border border-surface-line text-2xl font-bold" aria-label="One more" @click="step(1)">+</button>
      <select
        v-if="line.uoms.length > 1"
        :value="line.uom"
        class="h-12 min-w-0 flex-1 rounded-lg border border-surface-line bg-surface px-2 font-semibold"
        aria-label="Unit"
        @change="$emit('update', { uom: $event.target.value })"
      >
        <option v-for="u in line.uoms" :key="u.uom" :value="u.uom">{{ u.uom }}{{ u.factor !== 1 ? ` ×${fmt(u.factor)}` : "" }}</option>
      </select>
      <div v-else class="flex-1 font-semibold">{{ line.uom }}</div>
    </div>

    <div class="tnum mt-2 flex flex-wrap justify-between gap-x-3 text-[14px]">
      <span v-if="factor !== 1" class="font-semibold">= {{ fmt(stockQty) }} {{ line.stock_uom }}</span>
      <span class="text-ink-muted">Available: <b :class="line.available > 0 ? 'text-ink' : 'text-danger-text'">{{ fmt(line.available) }} {{ line.stock_uom }}</b></span>
      <span v-if="line.at_target !== null && line.at_target !== undefined" class="text-ink-faint">At destination: {{ fmt(line.at_target) }}</span>
    </div>
    <div v-if="problem" class="mt-2 rounded-lg bg-danger-bg px-3 py-2 text-[14px] font-semibold text-danger-text">{{ problem }}</div>
    <div v-else-if="warning" class="mt-2 rounded-lg bg-warn-bg px-3 py-2 text-[14px] font-semibold text-warn-text">{{ warning }}</div>
  </div>
</template>

<script setup>
import { computed } from "vue"

import { fmt } from "@/data/format.js"

// problem = the line's own error text (computed by the page: over-available,
// whole numbers, or the server's message for this line).
// warning = amber note that does not block (e.g. short stock a Stock Manager can count at review)
const props = defineProps({ line: { type: Object, required: true }, problem: { type: String, default: "" }, warning: { type: String, default: "" } })
const emit = defineEmits(["update", "remove"])

const unit = computed(() => props.line.uoms.find((u) => u.uom === props.line.uom) || { factor: 1, whole: 0 })
const factor = computed(() => unit.value.factor)
const stockQty = computed(() => Number(props.line.qty || 0) * factor.value)

function setQty(v) {
  const n = v === "" ? "" : Number(v)
  emit("update", { qty: n === "" || Number.isNaN(n) ? "" : n })
}
function step(d) {
  const n = Math.max(0, Number(props.line.qty || 0) + d)
  emit("update", { qty: n })
}
</script>
