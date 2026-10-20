<template>
  <router-link :to="`/paper/${encodeURIComponent(p.name)}`" class="mb-2 flex items-center justify-between gap-3 rounded-xl border border-surface-line bg-surface p-3">
    <span class="min-w-0">
      <span class="block truncate font-semibold">{{ p.party_title || "Supplier / customer not chosen" }}</span>
      <span class="block text-[13px] text-ink-faint">
        {{ SHORT[p.purpose] || "PO" }} · {{ p.name }} · {{ fmtDate(p.creation) }}<template v-if="showOwner"> · {{ p.owner_name }}</template>
      </span>
    </span>
    <span class="flex-none text-right">
      <span class="block rounded-full px-2 text-[13px] font-bold" :class="look">{{ label }}</span>
      <span v-if="p.created_doc" class="mt-1 block text-[13px] text-ink-faint">{{ p.created_doc }}</span>
    </span>
  </router-link>
</template>

<script setup>
import { computed } from "vue"

import { fmtDate } from "@/data/format.js"
import { paperStatus } from "@/data/paper.js"

const SHORT = { "Purchase Order": "PO", "Sales Order": "SO", "Purchase Receipt": "PR", "Purchase Invoice": "PI" }
const props = defineProps({ p: { type: Object, required: true }, showOwner: { type: Boolean, default: false } })
const label = computed(() => paperStatus(props.p.status).label)
const look = computed(() => paperStatus(props.p.status).look)
</script>
