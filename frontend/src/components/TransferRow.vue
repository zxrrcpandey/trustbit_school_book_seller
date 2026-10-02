<template>
  <router-link :to="`/t/${encodeURIComponent(t.name)}`" class="mb-2 flex items-center justify-between gap-3 rounded-xl border border-surface-line bg-surface p-3">
    <span class="min-w-0">
      <span class="block truncate font-semibold">{{ short(t.from_warehouse) }} → {{ short(t.to_warehouse) }}</span>
      <span class="block text-[13px] text-ink-faint">
        {{ t.name }} · {{ fmtDate(t.posting_date) }} {{ String(t.posting_time || "").slice(0, 5) }}<template v-if="showOwner"> · {{ t.owner }}</template>
      </span>
    </span>
    <span class="flex-none text-right">
      <span class="tnum block font-semibold">{{ t.line_count }} line{{ t.line_count === 1 ? "" : "s" }}</span>
      <span v-if="t.docstatus !== 1" class="block text-[13px] font-semibold" :class="t.docstatus === 2 ? 'text-danger-text' : 'text-warn-text'">
        {{ t.docstatus === 2 ? "Cancelled" : "Draft" }}
      </span>
    </span>
  </router-link>
</template>

<script setup>
import { fmtDate, shortWarehouse as short } from "@/data/format.js"

defineProps({ t: { type: Object, required: true }, showOwner: { type: Boolean, default: false } })
</script>
