<template>
  <div class="pb-32">
    <AppHeader title="New transfer" back="/home">
      <template #right>
        <button v-if="draft.lines.length && !locked" type="button" class="px-3 py-2 text-[14px] font-semibold text-danger-text" @click="discard">Clear</button>
      </template>
    </AppHeader>

    <div v-if="bootError" class="m-4 rounded-lg bg-danger-bg p-3 text-danger-text">{{ bootError }}</div>
    <div v-else-if="!info" class="space-y-3 p-4"><div class="skeleton h-28" /><div class="skeleton h-14" /></div>

    <main v-else class="space-y-3 p-4">
      <!-- Warehouses -->
      <section class="rounded-xl border border-surface-line bg-surface p-3">
        <label class="block text-[13px] font-semibold uppercase tracking-wide text-ink-faint" for="from-wh">From</label>
        <select id="from-wh" v-model="draft.from" :disabled="locked" class="mt-1 h-12 w-full rounded-lg border border-surface-line bg-surface px-2 font-semibold">
          <option value="" disabled>Choose warehouse</option>
          <optgroup v-for="g in groups" :key="g.company" :label="g.company">
            <option v-for="w in g.rows" :key="w.name" :value="w.name">{{ w.name }} ({{ fmt(w.items_in_stock) }} items)</option>
          </optgroup>
        </select>
        <div class="my-1 flex justify-center">
          <button type="button" :disabled="locked" class="rounded-full border border-surface-line px-4 py-1 text-[14px] font-semibold text-brand-deep disabled:opacity-40" aria-label="Swap From and To" @click="swap">⇅ Swap</button>
        </div>
        <label class="block text-[13px] font-semibold uppercase tracking-wide text-ink-faint" for="to-wh">To</label>
        <select id="to-wh" v-model="draft.to" :disabled="locked" class="mt-1 h-12 w-full rounded-lg border border-surface-line bg-surface px-2 font-semibold">
          <option value="" disabled>Choose warehouse</option>
          <optgroup v-for="g in toGroups" :key="g.company" :label="g.company">
            <option v-for="w in g.rows" :key="w.name" :value="w.name">{{ w.name }}</option>
          </optgroup>
        </select>
        <p v-if="warehouseProblem" class="mt-2 text-[14px] font-semibold text-danger-text">{{ warehouseProblem }}</p>
      </section>

      <!-- Add items -->
      <section v-if="!locked" class="grid grid-cols-2 gap-2">
        <button type="button" class="min-h-action rounded-xl bg-brand-deep font-bold text-white disabled:opacity-40" :disabled="!draft.from" @click="openScanner">📷 Scan</button>
        <button type="button" class="min-h-action rounded-xl border-2 border-brand-deep font-bold text-brand-deep disabled:opacity-40" :disabled="!draft.from" @click="searching = true">🔍 Search</button>
        <button type="button" class="col-span-2 min-h-secondary rounded-xl border border-surface-line bg-surface font-semibold text-brand-deep disabled:opacity-40" :disabled="!draft.from" @click="bulkOpen = true">
          ➕ Add in bulk — school set, all stock, Excel
        </button>
        <form class="col-span-2 flex gap-2" @submit.prevent="typedCode">
          <input
            v-model="codeInput"
            :disabled="!draft.from"
            enterkeyhint="go"
            autocomplete="off"
            autocapitalize="off"
            placeholder="Type barcode / ISBN / item code"
            class="min-w-0 flex-1 rounded-lg border border-surface-line bg-surface p-3"
            aria-label="Barcode, ISBN or item code"
          />
          <button type="submit" class="rounded-lg bg-surface-line px-4 font-semibold disabled:opacity-40" :disabled="!codeInput.trim() || !draft.from">Add</button>
        </form>
        <p v-if="!draft.from" class="col-span-2 text-center text-[14px] text-ink-muted">Choose the From warehouse to start adding items.</p>
      </section>

      <div v-if="flash" class="rounded-lg px-3 py-2 text-[15px] font-semibold" :class="flash.ok ? 'bg-ok-bg text-ok-text' : 'bg-danger-bg text-danger-text'">{{ flash.text }}</div>

      <!-- Locked: a submit whose result we do not know -->
      <section v-if="locked" class="rounded-xl border-2 border-warn-text bg-warn-bg p-4 text-warn-text">
        <div class="font-bold">Not sure the transfer went through</div>
        <p class="mt-1 text-[14px]">
          The connection dropped while saving. Tap <b>Check and finish</b> — if it was already saved you will see it, and the
          stock will never be moved twice. The list is locked until then.
        </p>
        <p v-if="submitError" class="mt-2 text-[14px] font-semibold text-danger-text">{{ submitError }}</p>
        <button type="button" class="mt-3 min-h-action w-full rounded-xl bg-brand-deep font-bold text-white disabled:opacity-40" :disabled="submitting" @click="(draft.sent && draft.sent.bulk ? sendBulk : send)(draft.sent)">
          {{ submitting ? "Checking…" : "Check and finish" }}
        </button>
      </section>

      <!-- Lines -->
      <section v-if="draft.lines.length" class="space-y-2">
        <div class="flex items-center justify-between gap-2 text-[14px] text-ink-muted">
          <span>{{ fmt(draft.lines.length) }} line{{ draft.lines.length === 1 ? "" : "s" }} · {{ fmt(totalStockQty) }} in stock units</span>
          <span v-if="refreshing">Updating stock…</span>
          <button v-else-if="badCount" type="button" class="font-semibold text-danger-text" @click="onlyProblems = !onlyProblems">
            {{ onlyProblems ? "Show all" : `Show ${badCount} with problems` }}
          </button>
        </div>
        <TransferLine
          v-for="{ line, i } in visibleLines"
          :key="line.item_code + '|' + line.uom"
          :line="line"
          :problem="problems[i]"
          :warning="warnings[i]"
          :class="locked ? 'pointer-events-none opacity-70' : ''"
          @update="(patch) => updateLine(i, patch)"
          @remove="removeLine(i)"
        />
        <button v-if="hiddenCount" type="button" class="min-h-secondary w-full rounded-xl border border-surface-line bg-surface font-semibold text-brand-deep" @click="shown += 100">
          Show {{ Math.min(100, hiddenCount) }} more ({{ fmt(hiddenCount) }} hidden)
        </button>
      </section>
      <div v-else-if="draft.from" class="rounded-xl border border-dashed border-surface-line p-6 text-center text-ink-muted">
        Scan or search items to add them. Each scan adds 1; change the number or unit on the line.
      </div>
    </main>

    <!-- Bottom bar -->
    <div v-if="info && draft.lines.length && !locked" class="safe-bottom fixed inset-x-0 bottom-0 z-30 border-t border-surface-line bg-surface px-4 pt-3">
      <div class="mx-auto max-w-lg">
        <p v-if="blockReason" class="mb-2 text-center text-[14px] font-semibold text-danger-text">{{ blockReason }}</p>
        <button type="button" class="min-h-action w-full rounded-xl bg-brand-deep text-[17px] font-bold text-white disabled:opacity-40" :disabled="!!blockReason" @click="openReview">
          Review {{ fmt(draft.lines.length) }} line{{ draft.lines.length === 1 ? "" : "s" }}
        </button>
      </div>
    </div>

    <!-- Review -->
    <div v-if="reviewing" class="fixed inset-0 z-40 flex flex-col bg-surface-page">
      <AppHeader title="Check and move">
        <template #right>
          <button type="button" class="px-3 py-2 font-semibold text-brand-deep" :disabled="submitting" @click="reviewing = false">Edit</button>
        </template>
      </AppHeader>
      <div class="flex-1 space-y-3 overflow-y-auto p-4">
        <div class="rounded-xl border-2 border-brand-deep bg-surface p-4 text-center">
          <div class="text-[13px] font-semibold uppercase tracking-wide text-ink-faint">From</div>
          <div class="text-[18px] font-bold">{{ draft.from }}</div>
          <div class="my-1 text-2xl">↓</div>
          <div class="text-[13px] font-semibold uppercase tracking-wide text-ink-faint">To</div>
          <div class="text-[18px] font-bold">{{ draft.to }}</div>
        </div>
        <template v-if="reconciling">
          <div class="space-y-1 rounded-xl border-2 border-danger-text bg-danger-bg p-3 text-[15px] text-danger-text">
            <div class="text-[17px] font-bold">⚠ Not enough stock in {{ draft.from }}</div>
            <div>{{ shortItems.length }} item{{ shortItems.length === 1 ? " has" : "s have" }} less stock than you are moving.</div>
            <div>If you press <b>Accept</b>: what the system has will move, and the <b>extra you counted</b> will be added in <b>{{ draft.to }}</b>.</div>
            <div>Stock value will change by <b>₹{{ money(recoTotal) }}</b>.</div>
            <div class="font-bold">Accept only if the items are really there.</div>
          </div>
          <div v-if="recoLoading" class="skeleton h-40" />
          <p v-else-if="recoLoadError" class="rounded-lg bg-danger-bg p-3 font-semibold text-danger-text">{{ recoLoadError }}</p>
          <template v-else>
            <RecoCard
              v-for="s in shortItems"
              :key="s.item_code"
              :info="recoInfo[s.item_code]"
              :needed="s.needed"
              :model="recoModels[s.item_code]"
              :reasons="info.reco_reasons || []"
              :from="draft.from"
              :to="draft.to"
              :whole="s.whole"
              @update="(m) => (recoModels[s.item_code] = m)"
            />
          </template>
        </template>
        <div class="rounded-xl border border-surface-line bg-surface">
          <div v-for="line in draft.lines.slice(0, 100)" :key="line.item_code + '|' + line.uom" class="flex items-start justify-between gap-3 border-b border-surface-line px-4 py-3 last:border-0">
            <span class="min-w-0 font-semibold">{{ line.item_name }}</span>
            <span class="tnum flex-none text-right font-bold">{{ fmt(line.qty) }} {{ line.uom }}</span>
          </div>
          <div v-if="draft.lines.length > 100" class="px-4 py-3 text-[14px] font-semibold text-ink-muted">… and {{ fmt(draft.lines.length - 100) }} more lines</div>
        </div>
        <div v-if="isBulk" class="rounded-xl border-2 border-warn-text bg-warn-bg p-3 text-[14px] text-warn-text">
          <b>{{ fmt(draft.lines.length) }} lines</b> will be moved in the background as <b>{{ bulkParts }} transfers</b> of up to {{ info.max_lines }} lines each. Everything is checked first; you can watch the progress. Only outside shop hours (before 10:30, after 19:30).
        </div>
        <label class="block">
          <span class="text-[14px] font-semibold text-ink-muted">Note (optional) — e.g. van driver, school name</span>
          <textarea v-model="draft.remarks" rows="2" maxlength="500" class="mt-1 w-full rounded-lg border border-surface-line bg-surface p-3" />
        </label>
        <p v-if="submitError" class="rounded-lg bg-danger-bg p-3 font-semibold text-danger-text">{{ submitError }}</p>
        <router-link v-if="signedOut" to="/login" class="block text-center font-bold text-brand-deep">Sign in again (your items are kept)</router-link>
      </div>
      <div class="safe-bottom border-t border-surface-line bg-surface px-4 pt-3">
        <p v-if="reconciling && recoBlock" class="mb-2 text-center text-[14px] font-semibold text-danger-text">{{ recoBlock }}</p>
        <div v-if="reconciling" class="grid grid-cols-3 gap-2">
          <button type="button" class="min-h-action rounded-xl border-2 border-danger-text font-bold text-danger-text" :disabled="submitting" @click="reviewing = false">Reject</button>
          <button type="button" class="col-span-2 min-h-action rounded-xl bg-brand-deep text-[16px] font-bold text-white disabled:opacity-40" :disabled="submitting || !!recoBlock" @click="submit">
            {{ submitting ? "Saving…" : "Accept and move" }}
          </button>
        </div>
        <button v-else type="button" class="min-h-action w-full rounded-xl bg-brand-deep text-[17px] font-bold text-white disabled:opacity-40" :disabled="submitting" @click="submit">
          {{ submitting ? (isBulk ? "Checking everything…" : "Moving stock…") : isBulk ? `Move in background (${bulkParts} transfers)` : `Move stock now (${draft.lines.length})` }}
        </button>
      </div>
    </div>

    <ScannerSheet v-if="scanning" :last="lastScan" @code="handleCode" @close="scanning = false" />
    <ItemSearchSheet v-if="searching" :from="draft.from" @pick="pick" @close="searching = false" />
    <BulkSheet v-if="bulkOpen" :from="draft.from" :to="draft.to" :from-count="byName[draft.from]?.items_in_stock || 0" @add="addBulk" @close="bulkOpen = false" />
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { useRouter } from "vue-router"

import AppHeader from "@/components/AppHeader.vue"
import BulkSheet from "@/components/BulkSheet.vue"
import ItemSearchSheet from "@/components/ItemSearchSheet.vue"
import RecoCard from "@/components/RecoCard.vue"
import ScannerSheet from "@/components/ScannerSheet.vue"
import TransferLine from "@/components/TransferLine.vue"
import { boot, createBulkTransfer, createTransfer, getItem, lookupItem, recoPreview, stockLevels } from "@/data/api.js"
import { money, recoCalc } from "@/data/reco.js"
import { clearDraft, draft, loadDraft, rememberPair } from "@/data/draft.js"
import { errorBeep, okBeep, unlockAudio } from "@/data/feedback.js"
import { fmt } from "@/data/format.js"

const router = useRouter()
const info = ref(null)
const bootError = ref("")
const scanning = ref(false)
const searching = ref(false)
const reviewing = ref(false)
const submitting = ref(false)
const submitError = ref("")
const signedOut = ref(false)
const refreshing = ref(false)
const codeInput = ref("")
const lastScan = ref(null)
const flash = ref(null)
const serverProblems = ref({}) // "item|uom" → message from the server
const locked = computed(() => !!draft.sent)
const bulkOpen = ref(false)
const shown = ref(100)
const onlyProblems = ref(false)

// ── warehouses ──────────────────────────────────────────────────────────────
const byName = computed(() => Object.fromEntries((info.value?.warehouses || []).map((w) => [w.name, w])))
function grouped(rows) {
  const out = []
  for (const w of rows) {
    let g = out.find((x) => x.company === w.company)
    if (!g) out.push((g = { company: w.company, rows: [] }))
    g.rows.push(w)
  }
  return out
}
const groups = computed(() => grouped(info.value?.warehouses || []))
// To: same company as From (a cross-company move is a sale, not a transfer)
const toGroups = computed(() => {
  const company = byName.value[draft.from]?.company
  return grouped((info.value?.warehouses || []).filter((w) => w.name !== draft.from && (!company || w.company === company)))
})
const warehouseProblem = computed(() => {
  if (draft.from && !byName.value[draft.from]) return `${draft.from} can no longer be used. Choose again.`
  if (draft.to && !byName.value[draft.to]) return `${draft.to} can no longer be used. Choose again.`
  if (draft.from && draft.to && draft.from === draft.to) return "From and To must be different."
  if (draft.from && draft.to && byName.value[draft.from]?.company !== byName.value[draft.to]?.company)
    return "These warehouses belong to different companies."
  return ""
})

function swap() {
  ;[draft.from, draft.to] = [draft.to, draft.from]
}

// ── lines ───────────────────────────────────────────────────────────────────
const lineKey = (l) => `${l.item_code}|${l.uom}`
const unitOf = (l) => l.uoms.find((u) => u.uom === l.uom) || { factor: 1, whole: 0 }

const problems = computed(() => {
  const needed = {}
  for (const l of draft.lines) needed[l.item_code] = (needed[l.item_code] || 0) + Number(l.qty || 0) * unitOf(l).factor
  return draft.lines.map((l) => {
    const q = Number(l.qty)
    const u = unitOf(l)
    if (l.qty === "" || !(q > 0)) return "Enter a quantity."
    if (u.whole && !Number.isInteger(q)) return `${l.uom} must be a whole number.`
    if (l.valuation_ok === 0) return `Has no cost price in ${draft.from} — ask accounts to fix it first.`
    if (needed[l.item_code] > Number(l.available || 0) + 1e-6 && canReconcile.value) return serverProblems.value[lineKey(l)] || ""
    if (needed[l.item_code] > Number(l.available || 0) + 1e-6)
      return `Only ${fmt(l.available)} ${l.stock_uom} in ${draft.from}${needed[l.item_code] !== q * u.factor ? " (all lines of this item together)" : ""}.`
    return serverProblems.value[lineKey(l)] || ""
  })
})

const blockReason = computed(() => {
  if (!draft.from || !draft.to) return "Choose both warehouses."
  if (warehouseProblem.value) return warehouseProblem.value
  const bad = problems.value.filter(Boolean).length
  if (bad) return `${bad} line${bad === 1 ? " needs" : "s need"} attention.`
  if (info.value && draft.lines.length > info.value.max_lines && !info.value.is_manager)
    return `${draft.lines.length} lines — at most ${info.value.max_lines} per transfer. A Stock Manager can move more in the background.`
  return ""
})

const isBulk = computed(() => !!info.value && draft.lines.length > info.value.max_lines)

// ── short stock → Stock Reconciliation (Stock Manager, normal transfers only) ──
const canReconcile = computed(() => !!info.value?.is_manager && !isBulk.value)
const neededByItem = computed(() => {
  const m = {}
  for (const l of draft.lines) m[l.item_code] = (m[l.item_code] || 0) + Number(l.qty || 0) * unitOf(l).factor
  return m
})
const shortItems = computed(() => {
  const seen = new Set()
  const out = []
  for (const l of draft.lines) {
    if (seen.has(l.item_code)) continue
    seen.add(l.item_code)
    const need = neededByItem.value[l.item_code]
    if (need > Number(l.available || 0) + 1e-6) {
      const stockUnit = l.uoms.find((u) => u.uom === l.stock_uom) || { whole: 0 }
      out.push({ item_code: l.item_code, needed: need, available: Number(l.available || 0), stock_uom: l.stock_uom, whole: !!stockUnit.whole })
    }
  }
  return out
})
const warnings = computed(() =>
  draft.lines.map((l) => {
    if (!canReconcile.value) return ""
    const s = shortItems.value.find((x) => x.item_code === l.item_code)
    return s ? `Stock is less by ${fmt(s.needed - s.available)} ${l.stock_uom}. You can count it on the next screen.` : ""
  })
)
const reconciling = computed(() => canReconcile.value && shortItems.value.length > 0)
const recoInfo = ref({})
const recoModels = ref({})
const recoLoading = ref(false)
const recoLoadError = ref("")
function recoRow(s) {
  const info = recoInfo.value[s.item_code]
  const model = recoModels.value[s.item_code]
  if (!info || !model) return null
  return { info, model, ...recoCalc(info, s.needed, model, s.whole, draft.from, draft.to) }
}
const recoTotal = computed(() => shortItems.value.reduce((t, s) => t + (recoRow(s)?.reconciles ? recoRow(s).effect : 0), 0))
const recoBlock = computed(() => {
  if (recoLoading.value) return "Loading…"
  if (recoLoadError.value) return recoLoadError.value
  const bad = shortItems.value.map(recoRow).filter((r) => !r || r.error).length
  return bad ? `${bad} item${bad === 1 ? " needs" : "s need"} a count, price or reason.` : ""
})

async function loadRecoPreview() {
  recoLoading.value = true
  recoLoadError.value = ""
  try {
    const res = await recoPreview(draft.from, shortItems.value.map((s) => s.item_code), draft.to)
    recoInfo.value = res.items || {}
    const models = {}
    for (const s of shortItems.value) {
      const i = recoInfo.value[s.item_code] || {}
      const old = recoModels.value[s.item_code]
      models[s.item_code] = old && old.counted !== "" ? old : { counted: s.needed, rate: i.suggested_rate || "", reason: "", note: "" }
    }
    recoModels.value = models
  } catch (e) {
    recoLoadError.value = e.display ? e.display() : "Could not load the stock figures."
  } finally {
    recoLoading.value = false
  }
}

// Option B: the server splits each counted item into "transfer what the system has"
// + "add the extra in To". Here only the total moved for that item can shrink: to the
// count when it is below what was asked (never blocked — owner decision).
function applyCounts() {
  for (const s of shortItems.value) {
    const r = recoRow(s)
    if (!r || r.moveTotal >= s.needed - 1e-9) continue
    const first = draft.lines.find((l) => l.item_code === s.item_code)
    draft.lines = draft.lines.filter((l) => l.item_code !== s.item_code)
    if (r.moveTotal > 0) draft.lines.push({ ...first, uom: first.stock_uom, qty: r.moveTotal })
  }
}
const bulkParts = computed(() => (info.value ? Math.ceil(draft.lines.length / info.value.max_lines) : 0))
const badCount = computed(() => problems.value.filter(Boolean).length)
const totalStockQty = computed(() => draft.lines.reduce((t, l) => t + Number(l.qty || 0) * unitOf(l).factor, 0))
const indexed = computed(() => draft.lines.map((line, i) => ({ line, i })))
const visibleLines = computed(() =>
  onlyProblems.value && badCount.value ? indexed.value.filter(({ i }) => problems.value[i]) : indexed.value.slice(0, shown.value)
)
const hiddenCount = computed(() => (onlyProblems.value && badCount.value ? 0 : Math.max(0, draft.lines.length - shown.value)))

// Lines from a bulk load (school set / all stock / sheet): same item + unit adds
// onto the existing line, new ones go to the end. done({added, merged}).
function addBulk(lines, done) {
  const index = new Map(draft.lines.map((l) => [lineKey(l), l]))
  let added = 0
  let merged = 0
  for (const p of lines) {
    const existing = index.get(`${p.item_code}|${p.uom}`)
    if (existing) {
      existing.qty = Number(existing.qty || 0) + Number(p.qty)
      existing.available = p.available
      existing.at_target = p.at_target
      merged++
    } else {
      const line = {
        item_code: p.item_code, item_name: p.item_name, stock_uom: p.stock_uom, uoms: p.uoms, uom: p.uom,
        qty: Number(p.qty), available: p.available, at_target: p.at_target, valuation_ok: 1,
      }
      draft.lines.push(line)
      index.set(lineKey(line), line)
      added++
    }
  }
  serverProblems.value = {}
  if (done) done({ added, merged })
}

function updateLine(i, patch) {
  const line = draft.lines[i]
  if (patch.uom && patch.uom !== line.uom && draft.lines.some((l, j) => j !== i && l.item_code === line.item_code && l.uom === patch.uom)) {
    showFlash(false, `This item already has a ${patch.uom} line.`)
    return
  }
  delete serverProblems.value[lineKey(line)]
  Object.assign(line, patch)
}

function removeLine(i) {
  draft.lines.splice(i, 1)
}

function addPayload(p) {
  if (!p || !p.found) {
    errorBeep()
    return report(false, `${p?.code || "Code"} — not found. Try Search.`)
  }
  if (p.problems && p.problems.length) {
    errorBeep()
    return report(false, `${p.item_name}: ${p.problems[0]}`)
  }
  const existing = draft.lines.find((l) => l.item_code === p.item_code && l.uom === p.uom)
  let qty = 1
  if (existing) {
    existing.qty = Number(existing.qty || 0) + 1
    existing.available = p.available
    existing.at_target = p.at_target
    existing.valuation_ok = 1
    qty = existing.qty
    // move it to the top so the line just scanned is visible
    draft.lines.splice(draft.lines.indexOf(existing), 1)
    draft.lines.unshift(existing)
  } else {
    draft.lines.unshift({
      item_code: p.item_code,
      item_name: p.item_name,
      stock_uom: p.stock_uom,
      uoms: p.uoms,
      uom: p.uom,
      qty: 1,
      available: p.available,
      at_target: p.at_target,
      valuation_ok: 1,
    })
  }
  okBeep()
  report(true, `+1 ${p.item_name} — now ${fmt(qty)} ${p.uom}`)
}

function report(ok, text) {
  lastScan.value = { ok, text }
  showFlash(ok, text)
}

let flashTimer = null
function showFlash(ok, text) {
  flash.value = { ok, text }
  clearTimeout(flashTimer)
  flashTimer = setTimeout(() => (flash.value = null), ok ? 2500 : 6000)
}

async function handleCode(code) {
  if (locked.value) return
  if (!draft.from) return report(false, "Choose the From warehouse first.")
  try {
    addPayload(await lookupItem(code, draft.from, draft.to || null))
  } catch (e) {
    errorBeep()
    report(false, e.display ? e.display() : "Lookup failed.")
  }
}

function typedCode() {
  const code = codeInput.value.trim()
  codeInput.value = ""
  if (code) handleCode(code)
}

async function pick(itemCode) {
  searching.value = false
  unlockAudio()
  try {
    addPayload(await getItem(itemCode, draft.from, draft.to || null))
  } catch (e) {
    report(false, e.display ? e.display() : "Could not add the item.")
  }
}

function openScanner() {
  unlockAudio()
  lastScan.value = null
  scanning.value = true
}

// Bluetooth/USB scanners type the code fast and press Enter. Catch that when
// no text box has focus, so no on-screen keyboard is needed.
let wedge = ""
let wedgeAt = 0
function onKey(e) {
  if (scanning.value || searching.value || reviewing.value || locked.value) return
  const el = document.activeElement
  if (el && ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName)) return
  const now = Date.now()
  if (now - wedgeAt > 80) wedge = ""
  wedgeAt = now
  if (e.key === "Enter") {
    if (wedge.length >= 3) handleCode(wedge)
    wedge = ""
  } else if (e.key.length === 1) wedge += e.key
}

// Stock levels for every line, whenever a warehouse changes.
async function refreshLevels() {
  if (!draft.lines.length || !draft.from) return
  refreshing.value = true
  try {
    const levels = await stockLevels([...new Set(draft.lines.map((l) => l.item_code))], draft.from, draft.to || null)
    for (const l of draft.lines) {
      const s = levels[l.item_code]
      if (!s) continue
      l.available = s.available
      l.at_target = s.at_target
      l.valuation_ok = s.valuation_ok
    }
  } catch {
    /* lines keep their old numbers; the server re-checks on submit */
  } finally {
    refreshing.value = false
  }
}

watch(
  () => [draft.from, draft.to],
  () => {
    if (draft.to && draft.to === draft.from) draft.to = ""
    serverProblems.value = {}
    if (info.value) refreshLevels()
  }
)

// ── review + submit ─────────────────────────────────────────────────────────
function openReview() {
  submitError.value = ""
  signedOut.value = false
  reviewing.value = true
  if (reconciling.value) loadRecoPreview()
}

function submit() {
  let recos
  if (reconciling.value) {
    const rows = shortItems.value.map((s) => ({ s, r: recoRow(s) }))
    recos = rows
      .filter(({ r }) => r && r.reconciles)
      .map(({ s, r }) => ({ item_code: s.item_code, counted: r.model.counted, rate: Number(r.model.rate), reason: r.model.reason, note: r.model.note || "" }))
    applyCounts()
    if (!draft.lines.length) {
      reviewing.value = false
      showFlash(false, "Nothing left to move after the counts.")
      return
    }
  }
  ;(isBulk.value ? sendBulk : send)({
    ...(recos && recos.length ? { recos } : {}),
    from_warehouse: draft.from,
    to_warehouse: draft.to,
    items: draft.lines.map((l) => ({ item_code: l.item_code, qty: Number(l.qty), uom: l.uom })),
    remarks: draft.remarks || "",
    client_ref: draft.clientRef,
  })
}

async function send(request) {
  if (!request || submitting.value) return
  submitting.value = true
  submitError.value = ""
  signedOut.value = false
  draft.sent = request // locked until we know what happened
  try {
    const res = await createTransfer(request)
    if (res && res.ok && !res.name) {
      // nothing in the system to transfer: only the extra was added in To
      rememberPair(request.from_warehouse, request.to_warehouse)
      clearDraft({ keepWarehouses: true })
      reviewing.value = false
      router.replace({ path: "/home", query: { added: (res.recos || []).map((r) => `${r.name}:${r.value}`).join(","), to: request.to_warehouse, ...(res.already ? { already: "1" } : {}) } })
      return
    }
    if (res && res.ok) {
      rememberPair(request.from_warehouse, request.to_warehouse)
      clearDraft({ keepWarehouses: true })
      reviewing.value = false
      const recoQ = (res.recos || []).map((r) => `${r.name}:${r.value}`).join(",")
      router.replace({ path: `/t/${encodeURIComponent(res.name)}`, query: { done: "1", ...(res.already ? { already: "1" } : {}), ...(recoQ ? { recos: recoQ } : {}) } })
      return
    }
    // Nothing was created: mark the lines the server rejected.
    draft.sent = null
    const sentLines = request.items
    const map = {}
    for (const p of (res && res.problems) || []) {
      const l = sentLines[p.idx - 1]
      if (l) map[`${l.item_code}|${l.uom}`] = p.message
      else if (p.item_code) for (const x of draft.lines.filter((x) => x.item_code === p.item_code)) map[lineKey(x)] = p.message
    }
    serverProblems.value = map
    await refreshLevels()
    reviewing.value = false
    errorBeep()
    showFlash(false, "Some lines could not be moved — see the red notes.")
  } catch (e) {
    const unknown = e.excType === "NetworkError" || e.excType === "Timeout" || e.status >= 502
    if (unknown) {
      // The server may have saved it. Keep `sent` (locked) for a safe retry.
      reviewing.value = false
      submitError.value = e.display()
    } else {
      draft.sent = null // the server answered with an error: nothing was moved
      if (e.sessionExpired) signedOut.value = true
      submitError.value = e.sessionExpired ? "You were signed out. Sign in again — your items are kept." : e.display()
      if (e.needsReload) submitError.value += " Reload the app and try again."
    }
  } finally {
    submitting.value = false
  }
}

async function sendBulk(request) {
  if (!request || submitting.value) return
  submitting.value = true
  submitError.value = ""
  signedOut.value = false
  draft.sent = { ...request, bulk: 1 } // locked until we know what happened
  try {
    const { bulk, ...args } = draft.sent
    const res = await createBulkTransfer(args)
    if (res && res.ok) {
      rememberPair(request.from_warehouse, request.to_warehouse)
      clearDraft({ keepWarehouses: true })
      reviewing.value = false
      router.replace(`/bulk/${encodeURIComponent(res.ref)}`)
      return
    }
    draft.sent = null
    const map = {}
    for (const p of (res && res.problems) || []) {
      const l = request.items[p.idx - 1]
      if (l) map[`${l.item_code}|${l.uom}`] = p.message
    }
    serverProblems.value = map
    onlyProblems.value = true
    await refreshLevels()
    reviewing.value = false
    errorBeep()
    showFlash(false, `${Object.keys(map).length} line(s) cannot be moved — fix or remove them.`)
  } catch (e) {
    const unknown = e.excType === "NetworkError" || e.excType === "Timeout" || e.status >= 502
    if (unknown) {
      reviewing.value = false
      submitError.value = e.display()
    } else {
      draft.sent = null
      if (e.sessionExpired) signedOut.value = true
      submitError.value = e.sessionExpired ? "You were signed out. Sign in again — your items are kept." : e.display()
    }
  } finally {
    submitting.value = false
  }
}

function discard() {
  if (window.confirm("Remove all scanned items from this transfer?")) clearDraft({ keepWarehouses: true })
}

onMounted(async () => {
  loadDraft()
  window.addEventListener("keydown", onKey)
  try {
    info.value = await boot()
    if (!draft.from && info.value.default_from) draft.from = info.value.default_from
    refreshLevels()
  } catch (e) {
    bootError.value = e.display ? e.display() : "Could not load the warehouses."
  }
})
onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKey)
  clearTimeout(flashTimer)
})
</script>
