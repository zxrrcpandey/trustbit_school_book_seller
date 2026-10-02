<template>
  <div>
    <AppHeader :title="name" back="/home" />
    <main class="space-y-3 p-4">
      <div v-if="done" class="rounded-xl bg-ok-bg p-4 text-ok-text">
        <div class="text-[18px] font-bold">{{ already ? "Already saved" : "Stock moved" }}</div>
        <div class="text-[14px]">
          {{ already ? "This transfer had already gone through — nothing was moved twice. Check the lines below." : "The transfer is saved and the stock has moved." }}
        </div>
      </div>

      <div v-if="error" class="rounded-lg bg-danger-bg p-3 text-danger-text">{{ error }}</div>
      <div v-else-if="!doc" class="space-y-2"><div class="skeleton h-24" /><div class="skeleton h-40" /></div>
      <template v-else>
        <div class="rounded-xl border border-surface-line bg-surface p-4">
          <div class="flex items-center gap-2 text-[17px] font-bold">
            <span class="min-w-0 flex-1">{{ doc.from_warehouse }}</span><span>→</span><span class="min-w-0 flex-1 text-right">{{ doc.to_warehouse }}</span>
          </div>
          <div class="mt-1 text-[14px] text-ink-muted">
            {{ fmtDate(doc.posting_date) }} {{ doc.posting_time.slice(0, 5) }} · by {{ doc.owner_name }}
            <span v-if="doc.docstatus === 2" class="font-semibold text-danger-text"> · Cancelled</span>
            <span v-if="doc.docstatus === 0" class="font-semibold text-warn-text"> · Draft</span>
          </div>
          <div v-if="doc.remarks" class="mt-2 text-[14px]">{{ doc.remarks }}</div>
        </div>

        <a :href="doc.pdf_url" target="_blank" rel="noopener" class="flex min-h-action items-center justify-center rounded-xl border-2 border-brand-deep font-bold text-brand-deep">
          Print / share slip (PDF)
        </a>

        <div class="rounded-xl border border-surface-line bg-surface">
          <div class="border-b border-surface-line px-4 py-2 text-[14px] font-semibold text-ink-muted">{{ doc.items.length }} line{{ doc.items.length === 1 ? "" : "s" }}</div>
          <div v-for="(d, i) in doc.items" :key="i" class="flex items-start justify-between gap-3 border-b border-surface-line px-4 py-3 last:border-0">
            <span class="min-w-0">
              <span class="block font-semibold">{{ d.item_name }}</span>
              <span class="block text-[13px] text-ink-faint">{{ d.item_code }}</span>
            </span>
            <span class="tnum flex-none text-right">
              <span class="block font-bold">{{ fmt(d.qty) }} {{ d.uom }}</span>
              <span v-if="d.uom !== d.stock_uom" class="block text-[13px] text-ink-faint">{{ fmt(d.transfer_qty) }} {{ d.stock_uom }}</span>
            </span>
          </div>
        </div>

        <router-link v-if="done" to="/transfer" class="flex min-h-action items-center justify-center rounded-xl bg-brand-deep font-bold text-white">
          New transfer (same warehouses)
        </router-link>
        <router-link to="/home" class="flex min-h-secondary items-center justify-center font-semibold text-brand-deep">Home</router-link>
      </template>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"
import { useRoute } from "vue-router"

import AppHeader from "@/components/AppHeader.vue"
import { getTransfer } from "@/data/api.js"
import { fmt, fmtDate } from "@/data/format.js"

const props = defineProps({ name: { type: String, required: true } })
const route = useRoute()
const done = computed(() => route.query.done === "1")
const already = computed(() => route.query.already === "1")
const doc = ref(null)
const error = ref("")

onMounted(async () => {
  try {
    doc.value = await getTransfer(props.name)
  } catch (e) {
    error.value = e.display ? e.display() : "Could not load."
  }
})
</script>
