<template>
  <div class="fixed inset-0 z-50 flex flex-col bg-surface-page">
    <AppHeader title="Last bought">
      <template #right>
        <button type="button" class="px-3 py-2 font-semibold text-brand-deep" @click="$emit('close')">Close</button>
      </template>
    </AppHeader>
    <div class="flex-1 space-y-3 overflow-y-auto p-4">
      <section class="rounded-xl border border-surface-line bg-surface p-3">
        <div class="text-[13px] font-semibold uppercase tracking-wide text-ink-faint">This paper · line {{ line.idx }}</div>
        <div class="font-bold">{{ line.item_name || line.text }}</div>
        <div v-if="mineRate" class="tnum text-[14px] text-ink-muted">
          {{ fmt(line.qty) }} {{ line.uom }} · ₹{{ money(mineRate) }}<template v-if="line.discount_percent"> · {{ fmt(line.discount_percent) }}% off ₹{{ money0(line.mrp) }}</template>
        </div>
      </section>

      <section v-if="last && last.length">
        <h2 class="mb-2 text-[15px] font-bold">Last {{ last.length }} bill{{ last.length === 1 ? "" : "s" }}</h2>
        <div v-for="b in last" :key="b.doc" class="mb-2 rounded-xl border border-surface-line bg-surface p-3">
          <div class="flex items-baseline justify-between gap-2">
            <b class="tnum text-[17px]">₹{{ money(b.rate) }}</b>
            <span v-if="b.discount != null" class="tnum text-[14px] text-ink-muted">{{ b.discount }}% off ₹{{ money0(b.list) }}</span>
          </div>
          <div class="text-[13px] text-ink-faint">{{ b.supplier_name }} · {{ fmtDate(b.date) }} · {{ fmt(b.qty) }} {{ line.stock_uom }} · {{ b.doc }}<template v-if="b.bill_no"> · bill {{ b.bill_no }}</template></div>
        </div>
      </section>
      <p v-else class="rounded-xl border border-dashed border-surface-line p-4 text-center text-ink-muted">Never bought on a bill before.</p>

      <section v-if="cmp && cmp.chips.length" class="rounded-xl border border-surface-line bg-surface p-3">
        <h2 class="mb-1 text-[15px] font-bold">Against the last bill</h2>
        <div class="tnum flex justify-between text-[14px]"><span class="text-ink-muted">Rate</span><b>{{ diffText }}</b></div>
        <div class="mt-2 flex flex-wrap gap-1">
          <span v-for="(c, i) in cmp.chips" :key="i" class="rounded-full px-2 text-[13px] font-semibold" :class="c.info ? 'bg-surface-line text-ink-muted' : c.ok ? 'bg-ok-bg text-ok-text' : 'bg-warn-bg text-warn-text'">{{ c.text }}</span>
        </div>
      </section>

      <section v-if="usual" class="rounded-xl border border-surface-line bg-surface p-3">
        <h2 class="text-[15px] font-bold">{{ partyTitle }}'s usual discount</h2>
        <p class="tnum text-[14px]">{{ usual.pct }}% on {{ usual.lines }} of {{ usual.of }} bill lines in 12 months</p>
      </section>
      <p class="text-[13px] text-ink-faint">From submitted bills only, after any discount on the whole bill, per {{ line.stock_uom || "stock unit" }}. Free copies are left out. Shown only — the rate always comes from the paper.</p>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue"

import AppHeader from "@/components/AppHeader.vue"
import { fmt, fmtDate } from "@/data/format.js"
import { lastCompare, money, money0 } from "@/data/paper.js"

const props = defineProps({
  line: { type: Object, required: true },
  last: { type: Array, default: null },
  usual: { type: Object, default: null },
  partyTitle: { type: String, default: "" },
  buy: { type: Boolean, default: false },
})
defineEmits(["close"])

const mineRate = computed(() => Number(props.buy ? props.line.buy_rate : props.line.paper_rate) || 0)
const cmp = computed(() => lastCompare(props.line, props.last, props.buy))
const diffText = computed(() => {
  if (!cmp.value || !mineRate.value) return ""
  const d = mineRate.value / (Number(props.line.conversion_factor) || 1) - cmp.value.prev.rate
  if (Math.abs(d) < 0.005) return "Same"
  return `${d > 0 ? "+" : "−"}₹${money(Math.abs(d))} a copy`
})
</script>
