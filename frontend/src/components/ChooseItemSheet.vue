<template>
  <div class="fixed inset-0 z-50 flex flex-col bg-surface-page">
    <AppHeader title="Choose the item">
      <template #right>
        <button type="button" class="px-3 py-2 font-semibold text-brand-deep" @click="$emit('close')">Close</button>
      </template>
    </AppHeader>
    <div class="flex-1 space-y-3 overflow-y-auto p-4">
      <section v-if="line" class="rounded-xl border border-surface-line bg-surface p-3">
        <div class="text-[13px] font-semibold uppercase tracking-wide text-ink-faint">On the paper</div>
        <div class="font-bold">{{ line.text }}</div>
        <div class="tnum text-[14px] text-ink-muted">{{ paperBits }}</div>
      </section>

      <section v-if="line && line.candidates && line.candidates.length">
        <h2 class="mb-2 text-[15px] font-bold">Best matches</h2>
        <button
          v-for="(c, i) in line.candidates.slice(0, 5)"
          :key="c.item_code"
          type="button"
          class="mb-2 flex w-full items-start gap-3 rounded-xl bg-surface p-3 text-left"
          :class="picked === c.item_code ? 'border-2 border-brand-deep' : 'border border-surface-line'"
          :aria-pressed="picked === c.item_code"
          @click="picked = c.item_code"
        >
          <span class="mt-1 h-[18px] w-[18px] flex-none rounded-full" :class="picked === c.item_code ? 'border-[6px] border-brand-deep' : 'border-2 border-ink-faint'" />
          <span class="min-w-0 flex-1">
            <span class="flex items-start justify-between gap-2">
              <span class="min-w-0">
                <span class="block text-[12px] font-bold uppercase tracking-wide text-ink-faint">#{{ i + 1 }}<template v-if="i === 0"> Best match</template></span>
                <span class="block font-semibold">{{ c.item_name }}</span>
              </span>
              <span v-if="c.pct != null" class="tnum flex-none rounded-full px-2 text-[13px] font-bold" :class="band(c.pct)">{{ c.pct }}%</span>
            </span>
            <span class="block text-[13px] text-ink-faint">
              {{ c.item_code }}<template v-if="c.cls"> · Class {{ c.cls }}</template><template v-if="c.mrp"> · MRP ₹{{ money0(c.mrp) }}</template>
            </span>
            <span class="mt-1 flex flex-wrap gap-1">
              <span v-for="(r, j) in reasons(c, i)" :key="j" class="rounded-full px-2 text-[12px] font-semibold" :class="r.ok === true ? 'bg-ok-bg text-ok-text' : r.ok === false ? 'bg-warn-bg text-warn-text' : 'bg-surface-line text-ink-muted'">{{ r.ok === true ? "✓ " : r.ok === false ? "✗ " : "" }}{{ r.text }}</span>
            </span>
            <span v-if="facts[c.item_code] && facts[c.item_code][0]" class="tnum mt-1 block text-[12px] text-ink-faint">
              Last bought ₹{{ money(facts[c.item_code][0].rate) }}<template v-if="facts[c.item_code][0].discount != null"> · {{ facts[c.item_code][0].discount }}% off ₹{{ money0(facts[c.item_code][0].list) }}</template> · {{ facts[c.item_code][0].supplier_name }}
            </span>
          </span>
        </button>
        <p class="text-[12px] text-ink-faint">"Xxx" catch-all items are never suggested.</p>
      </section>

      <section>
        <label for="item-search" class="mb-2 block text-[15px] font-bold">{{ line && line.candidates && line.candidates.length ? "Or search all items" : "Search our items" }}</label>
        <input
          id="item-search"
          ref="input"
          v-model="txt"
          type="search"
          enterkeyhint="search"
          placeholder="Book or item name, code, ISBN"
          class="w-full rounded-lg border border-surface-line bg-surface p-3"
        />
        <div class="mt-1 text-[13px] text-ink-faint">Two or more words narrow it down, e.g. "viva maths 3".</div>
        <p v-if="error" class="mt-2 rounded-lg bg-danger-bg p-3 text-danger-text">{{ error }}</p>
        <div v-if="loading" class="mt-2 space-y-2"><div v-for="i in 3" :key="i" class="skeleton h-14" /></div>
        <p v-else-if="txt.trim().length >= 2 && !results.length" class="p-4 text-center text-ink-muted">Nothing found.</p>
        <button
          v-for="r in results"
          :key="r.item_code"
          type="button"
          class="mt-2 flex w-full items-start gap-3 rounded-xl bg-surface p-3 text-left"
          :class="picked === r.item_code ? 'border-2 border-brand-deep' : 'border border-surface-line'"
          :aria-pressed="picked === r.item_code"
          @click="picked = r.item_code"
        >
          <span class="mt-1 h-[18px] w-[18px] flex-none rounded-full" :class="picked === r.item_code ? 'border-[6px] border-brand-deep' : 'border-2 border-ink-faint'" />
          <span class="min-w-0 flex-1">
            <span class="block font-semibold">{{ r.item_name }}</span>
            <span class="block text-[13px] text-ink-faint">{{ r.item_code }}<template v-if="r.cls"> · Class {{ r.cls }}</template><template v-if="r.mrp"> · MRP ₹{{ money0(r.mrp) }}</template></span>
            <span v-if="r.catch_all" class="mt-1 inline-block rounded-full bg-warn-bg px-2 text-[12px] font-semibold text-warn-text">"Xxx" catch-all item — use only if nothing else fits</span>
          </span>
        </button>
      </section>

      <button v-if="allowLeave" type="button" class="min-h-secondary w-full rounded-xl border border-surface-line bg-surface font-semibold text-ink-muted" @click="$emit('leave')">
        Not in our items — leave it out
      </button>
    </div>
    <div class="safe-bottom border-t border-surface-line bg-surface px-4 pt-3">
      <p v-if="partyTitle" class="mb-2 text-center text-[13px] text-ink-faint">Saving the order remembers this for {{ partyTitle }}.</p>
      <button type="button" class="min-h-action w-full rounded-xl bg-brand-deep text-[17px] font-bold text-white disabled:opacity-40" :disabled="!picked" @click="$emit('pick', picked)">
        Use this item
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue"

import AppHeader from "@/components/AppHeader.vue"
import { fmt, fmtDate } from "@/data/format.js"
import { band, getItemFacts, money, money0, searchPaperItems } from "@/data/paper.js"

const props = defineProps({
  line: { type: Object, default: null },
  partyTitle: { type: String, default: "" },
  allowLeave: { type: Boolean, default: true },
  current: { type: String, default: "" },
  paperName: { type: String, default: "" },
})
const facts = ref({})

// plain reasons for the rank: class / MRP against the paper, what the shop did with the item
function reasons(c, i) {
  const l = props.line || {}
  const f = c.facts || {}
  const out = []
  if (c.class_mismatch) out.push({ ok: false, text: `Class ${c.cls}, paper says ${l.line_class}` })
  else if (l.line_class && c.cls === l.line_class && c.mrp_match) out.push({ ok: true, text: "Same class and MRP as the paper" })
  else if (l.line_class && c.cls === l.line_class) out.push({ ok: true, text: "Same class as the paper" })
  else if (c.mrp_match) out.push({ ok: true, text: "Same MRP as the paper" })
  if (!c.mrp_match && l.mrp && c.mrp && !c.class_mismatch) out.push({ ok: false, text: `MRP ₹${money0(c.mrp)}, paper says ₹${money0(l.mrp)}` })
  if (f.from_party) out.push({ ok: true, text: `Bought from ${props.partyTitle || "this supplier"}${f.party_date ? ", " + fmtDate(f.party_date) : ""}` })
  if (f.sold_12m) out.push({ ok: true, text: `Sold ${fmt(f.sold_12m)} in the last 12 months` })
  if (f.stock) out.push({ text: `Stock ${fmt(f.stock)}` })
  if (f.dead) out.push({ ok: false, text: "Never bought or sold — probably an old copy" })
  const first = (l.candidates || [])[0]
  if (i > 0 && first && first.item_name === c.item_name) out.push({ text: "Same name as #1" })
  return out
}
onMounted(async () => {
  const codes = ((props.line && props.line.candidates) || []).slice(0, 5).map((c) => c.item_code)
  if (!codes.length || !props.paperName) return
  try {
    facts.value = (await getItemFacts(props.paperName, codes)).last_bought || {}
  } catch {
    facts.value = {}
  }
})
defineEmits(["pick", "leave", "close"])

const input = ref(null)
const txt = ref("")
const results = ref([])
const loading = ref(false)
const error = ref("")
const picked = ref(props.current || (props.line && props.line.item_code) || "")

const paperBits = computed(() => {
  const l = props.line || {}
  const out = []
  if (l.code) out.push(`Code ${l.code}`)
  if (l.mrp) out.push(`MRP ${money(l.mrp)}`)
  if (l.paper_qty) out.push(`Qty ${fmt(l.paper_qty)}${l.unit ? " " + l.unit : ""}`)
  if (l.line_class) out.push(`Class ${l.line_class}`)
  if (l.idx) out.push(`line ${l.idx}`)
  return out.join(" · ")
})

let timer = null
let seq = 0
watch(txt, (v) => {
  clearTimeout(timer)
  error.value = ""
  if (v.trim().length < 2) {
    results.value = []
    loading.value = false
    return
  }
  loading.value = true
  timer = setTimeout(async () => {
    const mine = ++seq
    try {
      const rows = await searchPaperItems(v.trim())
      if (mine === seq) results.value = rows || []
    } catch (e) {
      if (mine === seq) error.value = e.display ? e.display() : "Search failed."
    } finally {
      if (mine === seq) loading.value = false
    }
  }, 350)
})

onMounted(() => {
  if (!(props.line && props.line.candidates && props.line.candidates.length) && input.value) input.value.focus()
})
</script>
