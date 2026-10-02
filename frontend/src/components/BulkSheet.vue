<template>
  <div class="fixed inset-0 z-50 flex flex-col bg-surface-page">
    <AppHeader title="Add in bulk">
      <template #right>
        <button type="button" class="px-3 py-2 font-semibold text-brand-deep" @click="$emit('close')">Close</button>
      </template>
    </AppHeader>

    <div class="grid grid-cols-3 gap-1 border-b border-surface-line bg-surface p-2">
      <button v-for="t in tabs" :key="t.key" type="button" class="min-h-secondary rounded-lg px-1 text-[14px] font-semibold" :class="tab === t.key ? 'bg-brand-deep text-white' : 'bg-surface-page text-ink-muted'" @click="switchTab(t.key)">
        {{ t.label }}
      </button>
    </div>

    <div class="flex-1 space-y-3 overflow-y-auto p-4">
      <!-- result of the last load -->
      <div v-if="result" class="space-y-2">
        <div class="rounded-xl bg-ok-bg p-3 font-semibold text-ok-text">{{ result.title }}</div>
        <div v-if="result.skipped.length" class="rounded-xl border border-warn-text bg-warn-bg p-3 text-warn-text">
          <div class="font-bold">{{ result.skipped.length }} not added</div>
          <div v-for="(s, i) in result.skipped.slice(0, 200)" :key="i" class="mt-1 text-[14px]">
            <span v-if="s.row">Row {{ s.row }} · </span><b>{{ s.item_name || s.item_code || "—" }}</b><span v-if="s.qty"> ({{ fmt(s.qty) }}{{ s.uom ? " " + s.uom : "" }})</span>: {{ s.reason }}
          </div>
          <div v-if="result.skipped.length > 200" class="mt-1 text-[14px]">… and {{ result.skipped.length - 200 }} more.</div>
        </div>
        <button type="button" class="min-h-action w-full rounded-xl bg-brand-deep font-bold text-white" @click="$emit('close')">Back to the transfer</button>
        <button type="button" class="min-h-secondary w-full font-semibold text-brand-deep" @click="result = null">Add more</button>
      </div>

      <template v-else>
        <p v-if="error" class="rounded-lg bg-danger-bg p-3 font-semibold text-danger-text">{{ error }}</p>

        <!-- School set -->
        <template v-if="tab === 'set'">
          <p class="text-[14px] text-ink-muted">Pick a school set (Product Bundle) and how many sets. Every book and item in it is added × that number. Items marked "Not Available" in the set are left out.</p>
          <div v-if="!bundle">
            <input v-model="bundleTxt" type="search" placeholder="School / class, e.g. RDPS 3" class="w-full rounded-lg border border-surface-line bg-surface p-3" aria-label="Search school sets" />
            <div v-if="bundleLoading" class="mt-2 space-y-2"><div v-for="i in 3" :key="i" class="skeleton h-14" /></div>
            <button v-for="b in bundles" :key="b.bundle" type="button" class="mt-2 flex w-full items-center justify-between gap-3 rounded-xl border border-surface-line bg-surface p-3 text-left" @click="bundle = b">
              <span class="min-w-0"><span class="block font-semibold">{{ b.bundle_name }}</span><span class="block text-[13px] text-ink-faint">{{ b.bundle }}</span></span>
              <span class="flex-none text-[14px] text-ink-muted">{{ b.items_count }} items</span>
            </button>
          </div>
          <div v-else class="space-y-3 rounded-xl border border-surface-line bg-surface p-3">
            <div class="flex items-start justify-between gap-2">
              <div><div class="font-bold">{{ bundle.bundle_name }}</div><div class="text-[13px] text-ink-faint">{{ bundle.bundle }} · {{ bundle.items_count }} items</div></div>
              <button type="button" class="text-[14px] font-semibold text-brand-deep" @click="bundle = null">Change</button>
            </div>
            <label class="block text-[14px] font-semibold text-ink-muted" for="sets">Number of sets</label>
            <input id="sets" v-model.number="sets" type="number" inputmode="numeric" min="1" max="5000" class="tnum h-12 w-full rounded-lg border border-surface-line text-center text-[18px] font-bold" />
            <button type="button" class="min-h-action w-full rounded-xl bg-brand-deep font-bold text-white disabled:opacity-40" :disabled="busy || !(sets >= 1)" @click="addSet">
              {{ busy ? "Adding…" : `Add ${sets || 0} set${sets === 1 ? "" : "s"}` }}
            </button>
          </div>
        </template>

        <!-- Everything in From -->
        <template v-else-if="tab === 'all'">
          <p class="text-[14px] text-ink-muted">Adds <b>every item that has stock in {{ from }}</b>, at its full quantity — e.g. a van coming back to the godown. You can remove or reduce lines afterwards.</p>
          <p v-if="fromCount > 150" class="rounded-lg bg-warn-bg p-3 text-[14px] font-semibold text-warn-text">
            {{ from }} has {{ fmt(fromCount) }} items. More than 150 lines can only be moved by a Stock Manager, outside shop hours, as several transfers in the background.
          </p>
          <button type="button" class="min-h-action w-full rounded-xl bg-brand-deep font-bold text-white disabled:opacity-40" :disabled="busy" @click="addAll">
            {{ busy ? "Loading…" : `Load all items in ${from}` }}
          </button>
        </template>

        <!-- Excel / CSV -->
        <template v-else>
          <p class="text-[14px] text-ink-muted">
            Upload an Excel (.xlsx) or CSV file. <b>Column A</b>: barcode, ISBN or item code · <b>Column B</b>: quantity · <b>Column C</b> (optional): unit, e.g. PKT. A header row is fine.
          </p>
          <button type="button" class="text-[14px] font-semibold text-brand-deep underline" @click="downloadSample">Download a sample file</button>
          <label class="flex min-h-action w-full cursor-pointer items-center justify-center rounded-xl border-2 border-dashed border-brand-deep font-bold text-brand-deep">
            <input type="file" accept=".xlsx,.csv" class="hidden" :disabled="busy" @change="upload" />
            {{ busy ? "Reading the file…" : "Choose a file" }}
          </label>
        </template>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from "vue"

import AppHeader from "@/components/AppHeader.vue"
import { expandBundle, parseSheet, searchBundles, warehouseContents } from "@/data/api.js"
import { fmt } from "@/data/format.js"

const props = defineProps({ from: { type: String, required: true }, to: { type: String, default: "" }, fromCount: { type: Number, default: 0 } })
// add(lines) is merged into the draft by the parent and returns {added, merged}
const emit = defineEmits(["add", "close"])

const tabs = [
  { key: "set", label: "School set" },
  { key: "all", label: "All stock" },
  { key: "file", label: "Excel / CSV" },
]
const tab = ref("set")
const busy = ref(false)
const error = ref("")
const result = ref(null)
const bundleTxt = ref("")
const bundles = ref([])
const bundleLoading = ref(false)
const bundle = ref(null)
const sets = ref(1)

function switchTab(k) {
  tab.value = k
  error.value = ""
  result.value = null
}

let timer = null
let seq = 0
async function loadBundles(txt) {
  const mine = ++seq
  bundleLoading.value = true
  try {
    const rows = await searchBundles(txt)
    if (mine === seq) bundles.value = rows || []
  } catch (e) {
    if (mine === seq) error.value = e.display ? e.display() : "Search failed."
  } finally {
    if (mine === seq) bundleLoading.value = false
  }
}
watch(bundleTxt, (v) => {
  clearTimeout(timer)
  timer = setTimeout(() => loadBundles(v.trim()), 350)
})
loadBundles("")

function finish(title, res) {
  const counts = res.lines.length ? emitAdd(res.lines) : { added: 0, merged: 0 }
  const parts = [`${counts.added} line${counts.added === 1 ? "" : "s"} added`]
  if (counts.merged) parts.push(`${counts.merged} added onto existing lines`)
  result.value = { title: `${title}: ${parts.join(", ")}.`, skipped: res.skipped || [] }
}

let addResult = null
function emitAdd(lines) {
  addResult = { added: 0, merged: 0 }
  emit("add", lines, (r) => (addResult = r))
  return addResult
}

async function run(fn) {
  error.value = ""
  busy.value = true
  try {
    await fn()
  } catch (e) {
    error.value = e.display ? e.display() : "Something went wrong."
  } finally {
    busy.value = false
  }
}

const addSet = () =>
  run(async () => {
    const res = await expandBundle(bundle.value.bundle, sets.value, props.from, props.to || null)
    finish(`${res.bundle_name} × ${res.sets}`, res)
  })

const addAll = () =>
  run(async () => {
    const res = await warehouseContents(props.from, props.to || null)
    finish(`Everything in ${props.from}`, res)
  })

function readAsBase64(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => resolve(String(r.result).split(",")[1] || "")
    r.onerror = () => reject(new Error("Could not read the file."))
    r.readAsDataURL(file)
  })
}

function upload(ev) {
  const file = ev.target.files && ev.target.files[0]
  ev.target.value = ""
  if (!file) return
  if (file.size > 3 * 1024 * 1024) {
    error.value = "The file is larger than 3 MB."
    return
  }
  run(async () => {
    const res = await parseSheet(file.name, await readAsBase64(file), props.from, props.to || null)
    finish(`${file.name} (${res.rows} rows)`, res)
  })
}

function downloadSample() {
  const csv = "Barcode / ISBN / Item code,Qty,Unit (optional)\n9789999999990,10,\nITM-2025-24166,2,PKT\n"
  const a = document.createElement("a")
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }))
  a.download = "kgs_transfer_sample.csv"
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 2000)
}
</script>
