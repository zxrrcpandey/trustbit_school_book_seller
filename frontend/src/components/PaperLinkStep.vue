<template>
  <main class="space-y-3 p-4 pb-40">
    <section class="rounded-xl border bg-surface p-3" :class="paper.party ? 'border-surface-line' : 'border-2 border-warn-text'">
      <div class="flex items-start justify-between gap-2">
        <div class="min-w-0">
          <div class="text-[13px] font-semibold uppercase tracking-wide text-ink-faint">Supplier</div>
          <div class="text-[18px] font-bold">{{ paper.party ? paper.party_title : "Choose the supplier" }}</div>
          <div class="text-[14px] text-ink-muted">{{ partyHow }}<template v-if="paper.paper.no"> · bill {{ paper.paper.no }}</template> · {{ paper.lines.length }} lines</div>
        </div>
        <button type="button" class="min-h-secondary flex-none rounded-xl border-2 border-brand-deep px-4 font-bold text-brand-deep" :disabled="busy" @click="$emit('party')">
          {{ paper.party ? "Change" : "Choose" }}
        </button>
      </div>
    </section>

    <template v-if="paper.party">
      <section v-for="g in groups" :key="g.key">
        <h2 class="mb-2 text-[15px] font-bold">{{ g.title }} ({{ g.docs.length }})</h2>
        <button
          v-for="d in g.docs"
          :key="d.name"
          type="button"
          class="mb-2 w-full rounded-xl bg-surface p-3 text-left"
          :class="[d.linkable ? '' : 'opacity-60', picked.includes(d.name) ? 'border-2 border-brand-deep' : 'border border-surface-line']"
          :disabled="!d.linkable || busy"
          :aria-pressed="picked.includes(d.name)"
          @click="toggle(d)"
        >
          <span class="flex items-start gap-3">
            <span class="mt-1 h-5 w-5 flex-none rounded border-2" :class="picked.includes(d.name) ? 'border-brand-deep bg-brand-deep' : 'border-ink-faint'">
              <span v-if="picked.includes(d.name)" class="block text-center text-[13px] font-bold leading-4 text-white">✓</span>
            </span>
            <span class="min-w-0 flex-1">
              <span class="flex items-start justify-between gap-2">
                <span class="min-w-0">
                  <span class="block font-bold">{{ d.name }}</span>
                  <span class="block text-[13px] text-ink-faint">{{ fmtDate(d.date) }} · {{ d.owner_name }} · {{ d.lines }} line{{ d.lines === 1 ? "" : "s" }}<template v-if="d.bill_no"> · bill {{ d.bill_no }}</template></span>
                </span>
                <span v-if="d.linkable" class="tnum flex-none rounded-full px-2 text-[13px] font-bold" :class="band(d.pct || 0)">{{ d.pct || 0 }}% match</span>
                <span v-else class="flex-none rounded-full bg-surface-line px-2 text-[13px] font-bold text-ink-muted">–</span>
              </span>
              <span v-if="d.linkable" class="mt-1 block text-[14px]">{{ d.hits || 0 }} of {{ paper.lines.length }} paper lines are on this {{ g.short }}</span>
              <span v-else class="mt-1 block text-[14px] font-semibold text-warn-text">{{ d.why }}. Can't be {{ g.key === "pr" ? "billed" : "received" }} until a shop owner approves it.</span>
              <span class="mt-1 flex flex-wrap gap-1">
                <span v-if="best && best.name === d.name" class="rounded-full bg-ok-bg px-2 text-[12px] font-semibold text-ok-text">Best fit</span>
                <span v-if="d.linkable" class="rounded-full bg-surface-line px-2 text-[12px] font-semibold text-ink-muted">{{ d.due_lines }} line{{ d.due_lines === 1 ? "" : "s" }} {{ g.key === "pr" ? "to bill" : "due" }}</span>
                <span v-if="paper.purpose === 'Purchase Invoice' && g.key === 'po'" class="rounded-full bg-surface-line px-2 text-[12px] font-semibold text-ink-muted">The bill adds the stock itself</span>
                <span v-if="d.draft_bills && d.draft_bills.length" class="rounded-full bg-warn-bg px-2 text-[12px] font-semibold text-warn-text">Draft bill {{ d.draft_bills.join(", ") }} already uses it</span>
              </span>
            </span>
          </span>
        </button>
      </section>
      <p v-if="!paper.open_docs.length" class="rounded-xl border border-dashed border-surface-line p-4 text-center text-ink-muted">
        {{ paper.party_title }} has no open {{ paper.purpose === "Purchase Invoice" ? "Receipts or POs" : "POs" }}.
      </p>

      <h2 class="text-[15px] font-bold">Nothing to link</h2>
      <button
        type="button"
        class="w-full rounded-xl bg-surface p-3 text-left"
        :class="none ? 'border-2 border-brand-deep' : 'border border-surface-line'"
        :aria-pressed="none"
        :disabled="busy"
        @click="pickNone"
      >
        <span class="block font-bold">{{ paper.purpose === "Purchase Invoice" ? "Goods came with this bill" : "No PO" }}</span>
        <span class="block text-[13px] text-ink-faint">{{ paper.purpose === "Purchase Invoice" ? 'One bill that also adds the stock ("Update Stock")' : "These goods were not ordered" }}</span>
      </button>
      <p v-if="paper.purpose === 'Purchase Invoice'" class="text-[13px] text-ink-faint">A bill linked to a Receipt never adds stock again — ERPNext would count it twice otherwise.</p>
    </template>
    <p v-if="error" class="rounded-lg bg-danger-bg p-3 font-semibold text-danger-text">{{ error }}</p>

    <div class="safe-bottom fixed inset-x-0 bottom-0 z-30 border-t border-surface-line bg-surface px-4 pt-3">
      <div class="mx-auto max-w-lg">
        <button type="button" class="min-h-action w-full rounded-xl bg-brand-deep text-[17px] font-bold text-white disabled:opacity-40" :disabled="busy || !paper.party || (!picked.length && !none)" @click="go">
          {{ buttonText }}
        </button>
      </div>
    </div>
  </main>
</template>

<script setup>
import { computed, ref } from "vue"

import { fmtDate } from "@/data/format.js"
import { band } from "@/data/paper.js"

const props = defineProps({
  paper: { type: Object, required: true },
  partyHow: { type: String, default: "" },
  busy: { type: Boolean, default: false },
  error: { type: String, default: "" },
})
const emit = defineEmits(["link", "party"])

const docs = computed(() => props.paper.open_docs || [])
const best = computed(() => docs.value.find((d) => d.linkable && (d.pct || 0) >= (props.paper.doc_preselect || 60)) || null)
// the best document is ticked for you when it matches 60% or more
const picked = ref(best.value ? [best.value.name] : [])
const none = ref(false)
const groups = computed(() => {
  const out = []
  const prs = docs.value.filter((d) => d.doctype === "Purchase Receipt")
  const pos = docs.value.filter((d) => d.doctype === "Purchase Order")
  if (prs.length) out.push({ key: "pr", short: "Receipt", title: "Receipts not billed yet", docs: prs })
  if (pos.length) out.push({ key: "po", short: "PO", title: `Open orders from ${props.paper.party_title}`, docs: pos })
  return out
})
function toggle(d) {
  none.value = false
  const kind = d.doctype
  let next = picked.value.includes(d.name) ? picked.value.filter((n) => n !== d.name) : [...picked.value, d.name]
  // Receipts or POs, not both: a bill from a Receipt never adds stock again
  next = next.filter((n) => (docs.value.find((x) => x.name === n) || {}).doctype === kind)
  picked.value = next
}
function pickNone() {
  none.value = true
  picked.value = []
}
const buttonText = computed(() => {
  if (none.value) return props.paper.purpose === "Purchase Invoice" ? "Bill that adds stock — check the lines" : "No PO — check the lines"
  if (!picked.value.length) return "Tick a document, or choose the option below"
  const kind = (docs.value.find((x) => x.name === picked.value[0]) || {}).doctype === "Purchase Receipt" ? "Receipt" : "PO"
  return `Link ${picked.value.length} ${kind}${picked.value.length === 1 ? "" : "s"} and check the lines`
})
function go() {
  if (none.value) emit("link", "none", [])
  else emit("link", "docs", picked.value)
}
</script>
