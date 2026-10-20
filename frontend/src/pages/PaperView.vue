<template>
  <div class="pb-36">
    <AppHeader :title="title" back="/home">
      <template #right>
        <button v-if="paper && paper.files && paper.files.length && !reading" type="button" class="px-3 py-2 text-[14px] font-semibold text-brand-deep" @click="viewing = true">View paper</button>
      </template>
    </AppHeader>

    <div v-if="loadError" class="m-4 space-y-3">
      <p class="rounded-lg bg-danger-bg p-3 text-danger-text">{{ loadError }}</p>
      <button type="button" class="min-h-secondary w-full rounded-xl border border-surface-line bg-surface font-semibold" @click="load">Try again</button>
    </div>
    <div v-else-if="!paper" class="space-y-3 p-4"><div class="skeleton h-24" /><div class="skeleton h-40" /><div class="skeleton h-40" /></div>

    <!-- Reading -->
    <main v-else-if="reading" class="flex flex-col items-center gap-4 px-6 py-16 text-center">
      <div class="h-14 w-14 animate-spin rounded-full border-4 border-surface-line border-t-brand-deep" aria-hidden="true" />
      <div class="text-[20px] font-bold">Reading the paper…</div>
      <p class="text-ink-muted">{{ paper.page_count || 1 }} page{{ paper.page_count === 1 ? "" : "s" }} · usually under a minute{{ elapsed > 5 ? ` · ${elapsed} s` : "" }}</p>
      <p class="text-[14px] text-ink-faint">You can leave this screen — the paper waits under <router-link to="/papers" class="font-semibold text-brand-deep">Papers</router-link>.</p>
    </main>

    <!-- Failed -->
    <main v-else-if="paper.status === 'Failed'" class="space-y-3 p-4">
      <div class="rounded-xl border-2 border-danger-text bg-danger-bg p-4 text-danger-text">
        <div class="text-[17px] font-bold">The paper could not be read</div>
        <p class="mt-1">{{ paper.error || "Please try again." }}</p>
      </div>
      <p v-if="actionError" class="rounded-lg bg-danger-bg p-3 font-semibold text-danger-text">{{ actionError }}</p>
      <button type="button" class="min-h-action w-full rounded-xl bg-brand-deep font-bold text-white disabled:opacity-40" :disabled="busy" @click="reread(paper.model)">Try again</button>
      <button v-for="m in betterModels" :key="m.model" type="button" class="min-h-secondary w-full rounded-xl border-2 border-brand-deep font-bold text-brand-deep disabled:opacity-40" :disabled="busy" @click="reread(m.model)">
        Read with {{ m.label }}
      </button>
      <router-link :to="newLink" class="block min-h-secondary w-full rounded-xl border border-surface-line bg-surface py-3 text-center font-semibold">Take new photos</router-link>
      <button type="button" class="min-h-secondary w-full font-semibold text-danger-text" :disabled="busy" @click="discard">Discard this paper</button>
    </main>

    <!-- Discarded -->
    <main v-else-if="paper.status === 'Discarded'" class="space-y-3 p-6 text-center">
      <div class="text-[18px] font-bold">This paper was discarded</div>
      <router-link :to="newLink" class="block min-h-action rounded-xl bg-brand-deep py-4 font-bold text-white">Read another paper</router-link>
    </main>

    <!-- Saved -->
    <main v-else-if="paper.status === 'Saved'" class="space-y-3 p-4">
      <div class="rounded-xl p-4" :class="sentForApproval ? 'bg-ok-bg text-ok-text' : 'bg-brand-soft text-ink'">
        <div class="text-[19px] font-bold">{{ doneTitle }}</div>
        <p v-if="sentForApproval" class="mt-1 text-[15px]">{{ owners || "The shop owners" }} got the approval email. You get a message when it is approved.</p>
        <p v-else-if="isPo" class="mt-1 text-[15px]">It is a draft. Send it for approval in the ERP (Actions → Send for Approval) when it is ready.</p>
        <p v-else class="mt-1 text-[15px]">It is a draft; the office submits it as today.</p>
      </div>
      <p v-if="done && done.approval_error" class="rounded-lg bg-warn-bg p-3 font-semibold text-warn-text">Saved, but not sent for approval: {{ done.approval_error }}</p>
      <dl class="tnum divide-y divide-surface-line rounded-xl border border-surface-line bg-surface">
        <div class="flex justify-between gap-3 px-4 py-3"><dt class="text-ink-muted">{{ paper.purpose }}</dt><dd class="font-bold">{{ paper.created_doc }}</dd></div>
        <div class="flex justify-between gap-3 px-4 py-3"><dt class="text-ink-muted">{{ partyLabel }}</dt><dd class="text-right font-semibold">{{ paper.party_title }}</dd></div>
        <div class="flex justify-between gap-3 px-4 py-3"><dt class="text-ink-muted">Lines · quantity</dt><dd class="font-semibold">{{ kept.length }} · {{ fmt(keptQty) }}</dd></div>
        <div v-if="done && done.grand_total" class="flex justify-between gap-3 px-4 py-3"><dt class="text-ink-muted">Total</dt><dd class="font-semibold">₹{{ money(done.grand_total) }}</dd></div>
        <div class="flex justify-between gap-3 px-4 py-3"><dt class="text-ink-muted">Saved by</dt><dd class="text-right">{{ paper.saved_by_name }} · {{ fmtDate(paper.saved_on) }}</dd></div>
      </dl>
      <p class="text-[14px] text-ink-muted">The paper is attached to the {{ isPo ? "PO" : "Sales Order" }}.</p>
      <div v-if="leftOut.length" class="rounded-xl border-2 border-warn-text bg-warn-bg p-3 text-warn-text">
        <div class="font-bold">Still to do: {{ leftOut.length }} line{{ leftOut.length === 1 ? " was" : "s were" }} left out</div>
        <div v-for="l in leftOut" :key="l.idx" class="mt-1 text-[14px]">{{ l.text }}<template v-if="l.qty"> — {{ fmt(l.qty) }}</template></div>
        <p class="mt-2 text-[14px]">Create the item{{ leftOut.length === 1 ? "" : "s" }} in the ERP, then add {{ leftOut.length === 1 ? "it" : "them" }} to {{ paper.created_doc }}{{ isPo ? " before it is approved" : "" }}.</p>
      </div>
      <a :href="docUrl" class="block min-h-action rounded-xl border-2 border-brand-deep py-4 text-center font-bold text-brand-deep">Open in the ERP</a>
      <router-link :to="newLink" class="block min-h-action rounded-xl bg-brand-deep py-4 text-center font-bold text-white">Read another paper</router-link>
    </main>

    <!-- Check the lines -->
    <main v-else class="space-y-3 p-4">
      <section class="rounded-xl border bg-surface p-3" :class="paper.party ? 'border-surface-line' : 'border-2 border-warn-text'">
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <div class="text-[13px] font-semibold uppercase tracking-wide text-ink-faint">{{ partyLabel }}</div>
            <div class="text-[18px] font-bold">{{ paper.party ? paper.party_title : `Choose the ${partyLabel.toLowerCase()}` }}</div>
            <div class="text-[14px] text-ink-muted">{{ partyHow }}</div>
          </div>
          <button type="button" class="min-h-secondary flex-none rounded-xl border-2 border-brand-deep px-4 font-bold text-brand-deep" :disabled="busy" @click="partyOpen = true">
            {{ paper.party ? "Change" : "Choose" }}
          </button>
        </div>
      </section>

      <p v-if="paperLine" class="text-[14px] text-ink-muted">{{ paperLine }}</p>
      <p v-for="(n, i) in paper.notes" :key="'n' + i" class="rounded-lg bg-brand-soft p-3 text-[14px]">{{ n }}</p>
      <p v-for="(w, i) in paper.paper.warnings" :key="'w' + i" class="rounded-lg bg-warn-bg p-3 text-[14px] text-warn-text">The AI noted: {{ w }}</p>
      <p v-if="paper.paper.truncated" class="rounded-lg bg-warn-bg p-3 text-[14px] font-semibold text-warn-text">The paper is very long — only the first {{ lines.length }} lines were read. Send the rest as another paper.</p>
      <div v-if="paper.duplicate" class="rounded-xl border-2 border-warn-text bg-warn-bg p-3 text-[14px] text-warn-text">
        <b>Already used?</b> Paper no. {{ paper.paper.no }} from this {{ partyLabel.toLowerCase() }} became {{ paper.duplicate.doc }} on {{ fmtDate(paper.duplicate.saved_on) }}.
      </div>
      <p v-if="flash" class="rounded-lg px-3 py-2 text-[15px] font-semibold" :class="flash.ok ? 'bg-ok-bg text-ok-text' : 'bg-danger-bg text-danger-text'">{{ flash.text }}</p>

      <div class="grid grid-cols-3 gap-2 text-center">
        <div class="rounded-xl bg-ok-bg p-2 text-ok-text"><div class="tnum text-[22px] font-bold">{{ counts.sure }}</div><div class="text-[13px] font-semibold">sure</div></div>
        <div class="rounded-xl bg-warn-bg p-2 text-warn-text"><div class="tnum text-[22px] font-bold">{{ counts.pending }}</div><div class="text-[13px] font-semibold">to check</div></div>
        <div class="rounded-xl bg-danger-bg p-2 text-danger-text"><div class="tnum text-[22px] font-bold">{{ counts.missing }}</div><div class="text-[13px] font-semibold">not found</div></div>
      </div>

      <section v-if="!isPo" class="rounded-xl border border-surface-line bg-surface p-3">
        <div class="flex items-center justify-between gap-3">
          <label for="copies" class="text-[15px] font-semibold">Copies of each book</label>
          <div class="flex items-center gap-1">
            <button type="button" class="h-11 w-11 rounded-lg border border-surface-line text-xl font-bold" aria-label="One copy less" @click="setCopies((copies || 0) - 1)">−</button>
            <input id="copies" :value="copies || ''" type="number" inputmode="numeric" min="0" class="tnum h-11 w-20 rounded-lg border border-surface-line text-center text-[18px] font-bold" @change="(e) => setCopies(e.target.value)" />
            <button type="button" class="h-11 w-11 rounded-lg border border-surface-line text-xl font-bold" aria-label="One copy more" @click="setCopies((copies || 0) + 1)">+</button>
          </div>
        </div>
        <p class="mt-1 text-[13px] text-ink-faint">For lines without a quantity on the paper. You can still change one line. Prices come from our selling price list, never from the paper.</p>
      </section>

      <button v-if="counts.pending" type="button" class="text-[14px] font-semibold text-brand-deep" @click="onlyPending = !onlyPending">
        {{ onlyPending ? "Show all lines" : `Show only the ${counts.pending} to check` }}
      </button>

      <PaperLine
        v-for="l in shownLines"
        :key="l.idx"
        :line="l"
        :is-po="isPo"
        :party-title="paper.party_title"
        :disabled="busy && busyIdx === l.idx"
        @ok="decide(l, 'ok')"
        @leave="decide(l, 'left')"
        @undo="decide(l, null)"
        @change="choosing = l"
        @qty="(v) => change(l, { qty: v === '' ? null : Number(v) })"
        @uom="(v) => change(l, { uom: v })"
      />

      <section class="tnum space-y-1 rounded-xl border border-surface-line bg-surface p-3 text-[14px]">
        <div v-if="paper.paper.items_total" class="flex justify-between gap-3"><span class="text-ink-muted">Paper total</span><b>₹{{ money(paper.paper.items_total) }}<template v-if="paper.paper.total_qty"> · {{ fmt(paper.paper.total_qty) }}</template></b></div>
        <div v-else-if="paper.paper.grand_total" class="flex justify-between gap-3"><span class="text-ink-muted">Paper's grand total (with tax)</span><b>₹{{ money(paper.paper.grand_total) }}</b></div>
        <div class="flex justify-between gap-3"><span class="text-ink-muted">The {{ lines.length }} lines we read</span><b>{{ readTotal ? `₹${money(readTotal)} · ` : "" }}{{ fmt(readQty) }} qty</b></div>
        <div v-if="totalCheck" class="pt-1 font-semibold" :class="totalCheck.ok ? 'text-ok-text' : 'text-warn-text'">{{ totalCheck.text }}</div>
      </section>

      <div class="space-y-2 pt-2">
        <button v-if="otherModels.length" type="button" class="min-h-secondary w-full rounded-xl border border-surface-line bg-surface font-semibold text-brand-deep" :disabled="busy" @click="rereadOpen = true">
          Read again with a better model
        </button>
        <button type="button" class="min-h-secondary w-full font-semibold text-danger-text" :disabled="busy" @click="discard">Discard this paper</button>
      </div>
    </main>

    <!-- Bottom bar (check screen) -->
    <div v-if="paper && paper.status === 'Ready'" class="safe-bottom fixed inset-x-0 bottom-0 z-30 border-t border-surface-line bg-surface px-4 pt-3">
      <div class="mx-auto max-w-lg">
        <p v-if="blockReason" class="mb-2 text-center text-[14px] font-semibold text-warn-text">{{ blockReason }}</p>
        <button type="button" class="min-h-action w-full rounded-xl bg-brand-deep text-[17px] font-bold text-white disabled:opacity-40" :disabled="!!blockReason || busy || !paper.can_save" @click="openSave">
          Next: make the {{ isPo ? "Purchase Order" : "Sales Order" }}
        </button>
      </div>
    </div>

    <!-- Save -->
    <div v-if="saveOpen" class="fixed inset-0 z-40 flex flex-col bg-surface-page">
      <AppHeader :title="`Make the ${isPo ? 'Purchase Order' : 'Sales Order'}`">
        <template #right>
          <button type="button" class="px-3 py-2 font-semibold text-brand-deep" :disabled="saving" @click="saveOpen = false">Back</button>
        </template>
      </AppHeader>
      <div class="flex-1 space-y-3 overflow-y-auto p-4">
        <div class="rounded-xl border border-surface-line bg-surface p-3">
          <div class="text-[13px] font-semibold uppercase tracking-wide text-ink-faint">{{ partyLabel }}</div>
          <div class="text-[18px] font-bold">{{ paper.party_title }}</div>
        </div>
        <label class="block">
          <span class="text-[14px] font-semibold text-ink-muted">{{ isPo ? "Needed by" : "Delivery date" }}</span>
          <input v-model="form.needed_by" type="date" :min="today" class="mt-1 h-12 w-full rounded-lg border border-surface-line bg-surface px-3" />
        </label>
        <label class="block">
          <span class="text-[14px] font-semibold text-ink-muted">{{ isPo ? "Deliver to" : "Deliver from" }}</span>
          <select v-model="form.warehouse" class="mt-1 h-12 w-full rounded-lg border border-surface-line bg-surface px-2 font-semibold">
            <option v-for="w in paper.save.warehouses" :key="w" :value="w">{{ w }}</option>
          </select>
        </label>
        <div v-if="paper.save.school_field" class="block">
          <label for="school" class="text-[14px] font-semibold text-ink-muted">For school (optional)</label>
          <input id="school" v-model="schoolTxt" type="search" list="school-list" placeholder="Not for one school" class="mt-1 h-12 w-full rounded-lg border border-surface-line bg-surface px-3" @input="findSchools" />
          <datalist id="school-list"><option v-for="s in schools" :key="s" :value="s" /></datalist>
        </div>

        <section v-if="isPo" class="rounded-xl border border-surface-line bg-surface p-3">
          <div class="mb-2 text-[15px] font-bold">Rates</div>
          <label class="flex min-h-secondary items-center gap-3"><input v-model="form.rate_mode" type="radio" value="paper" class="h-5 w-5 accent-[var(--kgs-brand-deep)]" />The paper's rates{{ paper.paper.discount_note ? ` (${paper.paper.discount_note})` : "" }}</label>
          <label class="flex min-h-secondary items-center gap-3"><input v-model="form.rate_mode" type="radio" value="ours" class="h-5 w-5 accent-[var(--kgs-brand-deep)]" />Our usual buying price</label>
          <template v-if="form.rate_mode === 'paper'">
            <p v-if="rateTotalWarning" class="mt-2 rounded-lg bg-warn-bg p-2 text-[14px] font-semibold text-warn-text">{{ rateTotalWarning }}</p>
            <p v-for="(w, i) in rateWarnings" :key="i" class="mt-2 rounded-lg bg-warn-bg p-2 text-[14px] text-warn-text">{{ w }}</p>
            <p v-if="noPrice" class="mt-2 text-[14px] text-ink-muted">{{ noPrice }} line{{ noPrice === 1 ? " has" : "s have" }} no price on the paper — the ERP's buying price is used.</p>
          </template>
        </section>

        <dl class="tnum divide-y divide-surface-line rounded-xl border border-surface-line bg-surface">
          <div class="flex justify-between px-4 py-3"><dt class="text-ink-muted">Lines</dt><dd class="font-bold">{{ kept.length }}</dd></div>
          <div class="flex justify-between px-4 py-3"><dt class="text-ink-muted">Quantity</dt><dd class="font-bold">{{ fmt(keptQty) }}</dd></div>
          <div v-if="isPo && form.rate_mode === 'paper' && orderTotal" class="flex justify-between px-4 py-3"><dt class="text-ink-muted">Total at the paper's rates</dt><dd class="font-bold">₹{{ money(orderTotal) }}</dd></div>
        </dl>
        <div v-if="leftOut.length" class="rounded-xl border border-warn-text bg-warn-bg p-3 text-[14px] text-warn-text">
          <b>Left out ({{ leftOut.length }}):</b> {{ leftOut.map((l) => l.text + (l.qty ? `, ${fmt(l.qty)}` : "")).join("; ") }}. They are written in the {{ isPo ? "PO's remark" : "order's comment" }} for the office.
        </div>
        <p class="text-[14px] text-ink-muted">{{ learnCount }} line{{ learnCount === 1 ? "" : "s" }} will be remembered for {{ paper.party_title }}, so next time {{ learnCount === 1 ? "it is" : "they are" }} green.</p>

        <div v-if="dupInfo" class="rounded-xl border-2 border-warn-text bg-warn-bg p-3 text-warn-text">
          <div class="font-bold">This paper was already used</div>
          <p class="text-[14px]">It became {{ dupInfo.doc }} on {{ fmtDate(dupInfo.saved_on) }}. Save another order anyway?</p>
          <button type="button" class="mt-2 min-h-secondary w-full rounded-xl border-2 border-warn-text font-bold" :disabled="saving" @click="save(lastSend, true)">Save anyway</button>
        </div>
        <div v-if="saveUnknown" class="rounded-xl border-2 border-warn-text bg-warn-bg p-3 text-warn-text">
          <div class="font-bold">Not sure it was saved</div>
          <p class="text-[14px]">The connection dropped. Tap <b>Check and finish</b> — if it was saved you will see it; it is never saved twice.</p>
        </div>
        <p v-if="saveError" class="rounded-lg bg-danger-bg p-3 font-semibold text-danger-text">{{ saveError }}</p>
      </div>
      <div class="safe-bottom space-y-2 border-t border-surface-line bg-surface px-4 pt-3">
        <template v-if="saveUnknown">
          <button type="button" class="min-h-action w-full rounded-xl bg-brand-deep text-[17px] font-bold text-white disabled:opacity-40" :disabled="saving" @click="save(lastSend, lastDup)">{{ saving ? "Checking…" : "Check and finish" }}</button>
        </template>
        <template v-else-if="isPo">
          <button v-if="paper.save.can_send" type="button" class="min-h-action w-full rounded-xl bg-brand-deep text-[17px] font-bold text-white disabled:opacity-40" :disabled="saving" @click="save(true)">
            {{ saving && lastSend ? "Saving…" : "Save and send for approval" }}
          </button>
          <button type="button" class="min-h-secondary w-full rounded-xl border-2 border-brand-deep font-bold text-brand-deep disabled:opacity-40" :disabled="saving" @click="save(false)">
            {{ saving && !lastSend ? "Saving…" : "Save as draft only" }}
          </button>
          <p v-if="paper.save.approval && owners" class="text-center text-[13px] text-ink-faint">{{ owners }} approve it, as with every PO.</p>
        </template>
        <button v-else type="button" class="min-h-action w-full rounded-xl bg-brand-deep text-[17px] font-bold text-white disabled:opacity-40" :disabled="saving" @click="save(false)">
          {{ saving ? "Saving…" : "Save the Sales Order (draft)" }}
        </button>
      </div>
    </div>

    <!-- Read again -->
    <div v-if="rereadOpen" class="scrim fixed inset-0 z-50 flex items-end" @click.self="rereadOpen = false">
      <div class="safe-bottom w-full rounded-t-2xl bg-surface p-4">
        <h2 class="text-[17px] font-bold">Read again with</h2>
        <p class="mb-3 text-[14px] text-ink-muted">Lines you already checked stay as you left them when the same line is read again.</p>
        <button v-for="m in otherModels" :key="m.model" type="button" class="mb-2 w-full rounded-xl border border-surface-line p-3 text-left" :disabled="busy" @click="reread(m.model)">
          <span class="block font-bold">{{ m.label }}</span><span class="block text-[13px] text-ink-faint">{{ m.note }}</span>
        </button>
        <button type="button" class="min-h-secondary w-full font-semibold" @click="rereadOpen = false">Cancel</button>
      </div>
    </div>

    <!-- The paper itself -->
    <div v-if="viewing" class="fixed inset-0 z-50 flex flex-col bg-surface-page">
      <AppHeader title="The paper">
        <template #right><button type="button" class="px-3 py-2 font-semibold text-brand-deep" @click="viewing = false">Close</button></template>
      </AppHeader>
      <div class="flex-1 space-y-3 overflow-auto p-2">
        <template v-for="(f, i) in paper.files" :key="f.url">
          <img v-if="f.kind === 'image'" :src="f.url" :alt="`Page ${i + 1}`" class="w-full rounded-lg border border-surface-line bg-surface" />
          <a v-else :href="f.url" target="_blank" rel="noopener" class="block rounded-xl border border-surface-line bg-surface p-4 text-center font-bold text-brand-deep">📄 Open the PDF</a>
        </template>
      </div>
    </div>

    <PartySheet
      v-if="partyOpen"
      :purpose="paper.purpose"
      :label="partyLabel"
      :printed="paper.paper.party_text || paper.paper.school_or_class || ''"
      :gstin="paper.paper.gstin || ''"
      :candidates="paper.party_candidates"
      @pick="pickParty"
      @close="partyOpen = false"
    />
    <ChooseItemSheet v-if="choosing" :line="choosing" :party-title="paper.party_title" @pick="pickItem" @leave="leaveChoosing" @close="choosing = null" />
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue"

import AppHeader from "@/components/AppHeader.vue"
import ChooseItemSheet from "@/components/ChooseItemSheet.vue"
import PaperLine from "@/components/PaperLine.vue"
import PartySheet from "@/components/PartySheet.vue"
import { newRef } from "@/data/draft.js"
import { fmt, fmtDate } from "@/data/format.js"
import { discardPaper, getPaper, money, rereadPaper, saveOrder, searchSchools, setParty, updateLines } from "@/data/paper.js"

const props = defineProps({ name: { type: String, required: true } })

const paper = ref(null)
const loadError = ref("")
const actionError = ref("")
const busy = ref(false)
const busyIdx = ref(null)
const flash = ref(null)
const elapsed = ref(0)
const partyOpen = ref(false)
const choosing = ref(null)
const viewing = ref(false)
const rereadOpen = ref(false)
const onlyPending = ref(false)
const saveOpen = ref(false)
const saving = ref(false)
const saveError = ref("")
const saveUnknown = ref(false)
const dupInfo = ref(null)
const done = ref(null)
const lastSend = ref(false)
const lastDup = ref(false)
const schoolTxt = ref("")
const schools = ref([])
const form = reactive({ needed_by: "", warehouse: "", rate_mode: "paper" })
const today = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10)
let saveRef = newRef()

const isPo = computed(() => !paper.value || paper.value.purpose !== "Sales Order")
const partyLabel = computed(() => (isPo.value ? "Supplier" : "Customer"))
const reading = computed(() => paper.value && ["Uploaded", "Reading"].includes(paper.value.status))
const lines = computed(() => paper.value?.lines || [])
const copies = computed(() => paper.value?.copies || 0)
const newLink = computed(() => `/paper?for=${isPo.value ? "po" : "so"}`)
const title = computed(() => {
  if (!paper.value) return "Order from paper"
  if (reading.value) return "Reading"
  if (paper.value.status === "Saved") return "Saved"
  if (paper.value.status === "Ready") return isPo.value ? "Check the lines" : "Check the lines · Sales Order"
  return "Order from paper"
})

const stateOf = (l) => (l.decision === "left" ? "left" : l.decision === "ok" || l.by_person ? "confirmed" : l.colour || "red")
const counts = computed(() => {
  const c = { sure: 0, pending: 0, missing: 0, left: 0 }
  for (const l of lines.value) {
    const s = stateOf(l)
    if (s === "green" || s === "confirmed") c.sure++
    else if (s === "amber") c.pending++
    else if (s === "red") c.missing++
    else c.left++
  }
  return c
})
const shownLines = computed(() => (onlyPending.value ? lines.value.filter((l) => stateOf(l) === "amber") : lines.value))
const kept = computed(() => lines.value.filter((l) => ["green", "confirmed"].includes(stateOf(l)) && l.item_code && (l.can_keep || l.by_person)))
const leftOut = computed(() => lines.value.filter((l) => stateOf(l) === "left" || (stateOf(l) === "red" && !l.by_person)))
const keptQty = computed(() => kept.value.reduce((s, l) => s + Number(l.qty || 0), 0))
const orderTotal = computed(() => kept.value.reduce((s, l) => s + (l.paper_rate ? l.paper_rate * Number(l.qty || 0) : 0), 0))
const readQty = computed(() => lines.value.reduce((s, l) => s + Number(l.paper_qty || 0), 0))
const readTotal = computed(() => lines.value.reduce((s, l) => s + Number(l.paper_amount || 0), 0))
const totalCheck = computed(() => {
  const p = paper.value?.paper || {}
  if (p.items_total && lines.value.every((l) => l.paper_amount != null)) {
    const diff = Math.abs(readTotal.value - p.items_total)
    if (diff <= Math.max(1, p.items_total * 0.005)) return { ok: true, text: "Same as the paper — no line was missed." }
    return { ok: false, text: `The paper says ₹${money(p.items_total)}, we read ₹${money(readTotal.value)} — a line may be missing or misread. Check against the paper.` }
  }
  if (p.total_qty) {
    if (Math.abs(readQty.value - p.total_qty) < 0.001) return { ok: true, text: "Same quantity as the paper." }
    return { ok: false, text: `The paper says ${fmt(p.total_qty)} in all, we read ${fmt(readQty.value)}.` }
  }
  return null
})
const blockReason = computed(() => {
  if (!paper.value || paper.value.status !== "Ready") return ""
  if (!paper.value.can_save) return "Your account cannot make this order."
  if (!paper.value.party) return `Choose the ${partyLabel.value.toLowerCase()} first`
  const n = counts.value.pending
  if (n) return `Check ${n} more line${n === 1 ? "" : "s"} first`
  if (!kept.value.length) return "Every line is left out"
  const noQty = kept.value.filter((l) => !Number(l.qty)).length
  if (noQty) return `Enter the quantity on ${noQty} line${noQty === 1 ? "" : "s"}`
  return ""
})
const partyHow = computed(() => {
  const p = paper.value
  if (!p || !p.party) return p && p.paper.party_text ? `The paper says "${p.paper.party_text}"` : "Not found on the paper"
  return (
    {
      gstin: `Found by GSTIN ${p.paper.gstin || ""}`,
      last_time: `Same as last time for "${p.paper.party_text}"`,
      name: "Found by the name on the paper — check it",
      chosen: "Chosen by you",
    }[p.party_how] || ""
  )
})
const KIND = { quotation: "Quotation", price_list: "Price list", order: "Order", bill: "Bill", school_book_list: "Book list", other: "Paper" }
const paperLine = computed(() => {
  const p = paper.value?.paper || {}
  const bits = [KIND[p.kind] || "Paper"]
  if (p.no) bits[0] += ` ${p.no}`
  if (p.date) bits.push(p.date)
  if (p.school_or_class) bits.push(p.school_or_class)
  if (p.discount_note) bits.push(p.discount_note)
  if (paper.value?.model_label) bits.push(`read by ${paper.value.model_label}`)
  return bits.join(" · ")
})
const otherModels = computed(() => (paper.value?.models || []).filter((m) => m.model !== paper.value.model))
const betterModels = computed(() => otherModels.value.slice(0, 2))
const owners = computed(() => {
  const o = paper.value?.owners || []
  return o.length ? o.join(" and ") : ""
})
const sentForApproval = computed(() => paper.value?.created_status === "Pending Approval")
const doneTitle = computed(() => {
  if (!isPo.value) return "Sales Order saved as a draft"
  if (sentForApproval.value) return "Purchase Order sent for approval"
  if (paper.value?.created_status === "Approved") return "Purchase Order approved"
  return "Purchase Order saved as a draft"
})
const docUrl = computed(() => `/app/${isPo.value ? "purchase-order" : "sales-order"}/${encodeURIComponent(paper.value?.created_doc || "")}`)
const rateWarnings = computed(() =>
  kept.value
    .filter((l) => l.paper_rate && l.last_purchase_rate)
    .map((l) => {
      const factor = Number(l.conversion_factor || 1)
      const last = l.last_purchase_rate * factor
      const diff = (l.paper_rate - last) / last
      if (Math.abs(diff) <= 0.2) return null
      return `${l.item_name}: ₹${money(l.paper_rate)} on this paper, ₹${money(last)} last time (${diff > 0 ? "+" : ""}${Math.round(diff * 100)}%). Please check.`
    })
    .filter(Boolean)
)
// The net rates must explain one of the paper's printed totals (before tax, or
// with a usual GST rate on top); otherwise a discount was probably missed.
const rateTotalWarning = computed(() => {
  const p = paper.value?.paper || {}
  const all = lines.value
  if (!all.length || all.some((l) => !l.paper_rate || !l.paper_qty)) return ""
  const net = all.reduce((s, l) => s + l.paper_rate * Number(l.paper_qty), 0)
  const near = (a, b) => Math.abs(a - b) <= Math.max(1, b * 0.005)
  const head = `At the paper's rates the lines come to ₹${money(net)}, but the paper's`
  // a final total below the lines = a discount that is not in the rates
  if (p.grand_total && p.grand_total < net - Math.max(1, net * 0.005)) {
    const note = p.discount_note && !all.some((l) => l.discount_percent) ? ` (it says "${p.discount_note}")` : ""
    return `${head} final total is only ₹${money(p.grand_total)}${note}. A discount may be missing from the rates — check them before saving.`
  }
  const totals = [p.items_total, p.grand_total].filter(Boolean)
  if (!totals.length || totals.some((t) => [0, 5, 12, 18, 28, 40].some((g) => near(net * (1 + g / 100), t)))) return ""
  return `${head} total is ₹${money(totals[totals.length - 1])}. Check the rates before saving.`
})
const noPrice = computed(() => kept.value.filter((l) => !l.paper_rate).length)
const learnCount = computed(() => kept.value.filter((l) => l.by_person || !["alias_code", "alias_text"].includes(l.how)).length)

let flashTimer = null
function say(text, ok = false) {
  flash.value = { text, ok }
  clearTimeout(flashTimer)
  flashTimer = setTimeout(() => (flash.value = null), 5000)
}
const msg = (e, fallback) => (e && e.display ? e.display() : fallback)

// ── loading + polling while the job reads ───────────────────────────────────
let pollTimer = null
let started = Date.now()
async function load() {
  loadError.value = ""
  try {
    paper.value = await getPaper(props.name)
    if (reading.value) schedulePoll()
  } catch (e) {
    loadError.value = msg(e, "Could not load the paper.")
  }
}
function schedulePoll() {
  clearTimeout(pollTimer)
  pollTimer = setTimeout(poll, 2000)
}
async function poll() {
  elapsed.value = Math.round((Date.now() - started) / 1000)
  try {
    const r = await getPaper(props.name, 1)
    if (["Uploaded", "Reading"].includes(r.status)) schedulePoll()
    else await load()
  } catch {
    schedulePoll() // a dropped connection must not stop the wait
  }
}

// ── changes: one at a time, in order (each carries the version it was based on)
let queue = Promise.resolve()
function push(changes, extra = {}, idx = null) {
  queue = queue.then(async () => {
    busy.value = true
    busyIdx.value = idx
    try {
      const r = await updateLines(props.name, changes, paper.value.version, extra.copies)
      if (r.conflict) {
        paper.value = r.paper
        say("Someone else changed this paper — it was reloaded.")
        return
      }
      paper.value.version = r.version
      for (const nl of r.lines) {
        const i = paper.value.lines.findIndex((l) => l.idx === nl.idx)
        if (i >= 0) paper.value.lines[i] = nl
      }
      if (extra.copies !== undefined) paper.value.copies = extra.copies
    } catch (e) {
      say(msg(e, "Could not save that change."))
      await load()
    } finally {
      busy.value = false
      busyIdx.value = null
    }
  })
  return queue
}
function decide(l, decision) {
  l.decision = decision // shown at once; the server's answer replaces the line
  push([{ idx: l.idx, decision }], {}, l.idx)
}
function change(l, patch) {
  push([{ idx: l.idx, ...patch }], {}, l.idx)
}
function pickItem(itemCode) {
  const l = choosing.value
  choosing.value = null
  if (l) push([{ idx: l.idx, item_code: itemCode }], {}, l.idx)
}
function leaveChoosing() {
  const l = choosing.value
  choosing.value = null
  if (l) decide(l, "left")
}
let copiesTimer = null
function setCopies(v) {
  const n = Math.max(0, Math.min(10000, parseInt(v, 10) || 0))
  paper.value.copies = n
  clearTimeout(copiesTimer)
  copiesTimer = setTimeout(() => push([], { copies: n }), 500)
}

async function pickParty(party) {
  partyOpen.value = false
  await queue
  busy.value = true
  try {
    const r = await setParty(props.name, party, paper.value.version)
    paper.value = r.conflict ? r.paper : r
    if (r.conflict) say("Someone else changed this paper — it was reloaded.")
  } catch (e) {
    say(msg(e, "Could not set it."))
  } finally {
    busy.value = false
  }
}

async function reread(model) {
  rereadOpen.value = false
  actionError.value = ""
  busy.value = true
  try {
    await queue
    await rereadPaper(props.name, model)
    started = Date.now()
    elapsed.value = 0
    paper.value.status = "Reading"
    schedulePoll()
  } catch (e) {
    actionError.value = msg(e, "Could not start the reading.")
    say(actionError.value)
  } finally {
    busy.value = false
  }
}

async function discard() {
  if (!window.confirm("Discard this paper? Nothing is saved from it.")) return
  busy.value = true
  try {
    await queue
    await discardPaper(props.name)
    await load()
  } catch (e) {
    say(msg(e, "Could not discard it."))
  } finally {
    busy.value = false
  }
}

// ── save ────────────────────────────────────────────────────────────────────
function openSave() {
  const s = paper.value.save || {}
  form.needed_by = form.needed_by || s.needed_by
  form.warehouse = form.warehouse || s.warehouse
  saveError.value = ""
  dupInfo.value = null
  saveOpen.value = true
}
let schoolTimer = null
function findSchools() {
  clearTimeout(schoolTimer)
  schoolTimer = setTimeout(async () => {
    try {
      schools.value = (await searchSchools(schoolTxt.value.trim())) || []
    } catch {
      schools.value = []
    }
  }, 300)
}
async function save(send, allowDuplicate = false) {
  lastSend.value = !!send
  lastDup.value = !!allowDuplicate
  saving.value = true
  saveError.value = ""
  try {
    await queue
    const r = await saveOrder({
      name: props.name,
      client_ref: saveRef,
      send_for_approval: send ? 1 : 0,
      warehouse: form.warehouse,
      needed_by: form.needed_by,
      school: schoolTxt.value.trim() || null,
      rate_mode: form.rate_mode,
      allow_duplicate: allowDuplicate ? 1 : 0,
      version: paper.value.version,
    })
    saveUnknown.value = false
    if (r.conflict) {
      paper.value = r.paper
      saveOpen.value = false
      say("Someone else changed this paper — check it again.")
      return
    }
    if (r.ok === 0 && r.duplicate) {
      dupInfo.value = r.duplicate
      return
    }
    done.value = r
    saveOpen.value = false
    await load()
    window.scrollTo(0, 0)
  } catch (e) {
    if (e.excType === "Timeout" || e.excType === "NetworkError" || (e.status >= 500 && e.status !== 503)) saveUnknown.value = true
    saveError.value = msg(e, "Could not save.")
  } finally {
    saving.value = false
  }
}

watch(() => props.name, () => {
  saveRef = newRef()
  started = Date.now()
  load()
})
onMounted(load)
onBeforeUnmount(() => {
  clearTimeout(pollTimer)
  clearTimeout(flashTimer)
  clearTimeout(copiesTimer)
  clearTimeout(schoolTimer)
})
</script>
