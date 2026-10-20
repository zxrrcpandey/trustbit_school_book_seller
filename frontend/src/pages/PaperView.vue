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

    <!-- Reading: the lines appear as the AI writes them -->
    <PaperReading
      v-else-if="reading"
      :files="paper.files || []"
      :local="sentPages(paper.name)"
      :pages="paper.page_count || 1"
      :live="live"
      :elapsed="elapsed"
      :finished="finishing"
      :found="found"
    />

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

    <!-- Saved: Receipt / Bill -->
    <main v-else-if="paper.status === 'Saved' && isBuy" class="space-y-3 p-4">
      <div class="rounded-xl p-4" :class="paper.created_docstatus === 1 ? 'bg-ok-bg text-ok-text' : 'bg-brand-soft text-ink'">
        <div class="text-[19px] font-bold">{{ kindTitle }} {{ paper.created_docstatus === 1 ? "submitted" : "saved as a draft" }}</div>
        <p class="mt-1 text-[15px]">{{ paper.created_doc }} · {{ kept.length }} line{{ kept.length === 1 ? "" : "s" }}<template v-if="paper.created_total"> · ₹{{ money(paper.created_total) }}</template></p>
      </div>
      <p v-if="done && done.submit_error" class="rounded-lg bg-warn-bg p-3 font-semibold text-warn-text">Saved as a draft, but it could not be submitted: {{ done.submit_error }}</p>
      <dl class="tnum divide-y divide-surface-line rounded-xl border border-surface-line bg-surface">
        <div class="flex justify-between gap-3 px-4 py-3"><dt class="text-ink-muted">Supplier</dt><dd class="text-right font-semibold">{{ paper.party_title }}</dd></div>
        <div v-if="paper.links && paper.links.docs && paper.links.docs.length" class="flex justify-between gap-3 px-4 py-3"><dt class="text-ink-muted">Linked to</dt><dd class="text-right font-semibold">{{ paper.links.docs.join(", ") }}</dd></div>
        <div v-for="d in paper.still_due || []" :key="d.doc" class="flex justify-between gap-3 px-4 py-3"><dt class="text-ink-muted">Still due on {{ d.doc }}</dt><dd class="font-semibold">{{ d.lines }} line{{ d.lines === 1 ? "" : "s" }}</dd></div>
        <div class="flex justify-between gap-3 px-4 py-3"><dt class="text-ink-muted">Saved by</dt><dd class="text-right">{{ paper.saved_by_name }} · {{ fmtDate(paper.saved_on) }}</dd></div>
      </dl>
      <p class="text-[14px] text-ink-muted">The paper is attached to {{ paper.created_doc }}.</p>
      <section v-if="paper.bill" class="rounded-xl border-2 border-brand-deep bg-surface p-3">
        <div class="text-[16px] font-bold">Next for this paper: the Bill</div>
        <template v-if="paper.bill.paper">
          <p class="text-[14px] text-ink-muted">{{ paper.bill.doc ? `It became ${paper.bill.doc}.` : "The bill paper is ready to check." }}</p>
          <router-link :to="`/paper/${encodeURIComponent(paper.bill.paper)}`" class="mt-2 block min-h-secondary rounded-xl bg-brand-deep py-3 text-center font-bold text-white">Open the bill</router-link>
        </template>
        <template v-else-if="paper.bill.can">
          <p class="text-[14px] text-ink-muted">From {{ paper.created_doc }}, using this reading. No second AI read.</p>
          <button type="button" class="mt-2 min-h-action w-full rounded-xl bg-brand-deep font-bold text-white disabled:opacity-40" :disabled="busy" @click="doMakeBill">{{ busy ? "Making it…" : "Make the bill now" }}</button>
        </template>
        <p v-else-if="paper.bill.waiting" class="text-[14px] text-ink-muted">The Receipt is a draft. The bill can be made from here once the office submits it.</p>
        <p v-else class="text-[14px] text-ink-muted">Not available: the Receipt is billed already, or your account cannot make bills.</p>
      </section>
      <p v-if="actionError" class="rounded-lg bg-danger-bg p-3 font-semibold text-danger-text">{{ actionError }}</p>
      <div v-if="leftOut.length" class="rounded-xl border-2 border-warn-text bg-warn-bg p-3 text-warn-text">
        <div class="font-bold">Left out ({{ leftOut.length }})</div>
        <div v-for="l in leftOut" :key="l.idx" class="mt-1 text-[14px]">{{ l.text }}<template v-if="l.paper_qty"> · {{ fmt(l.paper_qty) }}</template></div>
        <p class="mt-2 text-[14px]">Create the item{{ leftOut.length === 1 ? "" : "s" }} in the ERP, then receive {{ leftOut.length === 1 ? "it" : "them" }} separately.</p>
      </div>
      <a :href="docUrl" class="block min-h-action rounded-xl border-2 border-brand-deep py-4 text-center font-bold text-brand-deep">Open in the ERP</a>
      <router-link :to="newLink" class="block min-h-action rounded-xl bg-brand-deep py-4 text-center font-bold text-white">Read another paper</router-link>
    </main>

    <!-- Link the PO / Receipt first -->
    <PaperLinkStep
      v-else-if="linkStep"
      :paper="paper"
      :party-how="partyHow"
      :busy="busy"
      :error="actionError"
      @party="partyOpen = true"
      @link="doLink"
    />

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

      <section v-if="isBuy" class="flex items-center justify-between gap-2 rounded-xl border border-surface-line bg-surface p-3">
        <div class="min-w-0 text-[14px]">
          <div class="text-[13px] font-semibold uppercase tracking-wide text-ink-faint">Linked to</div>
          <div class="font-semibold">{{ linkedText }}</div>
        </div>
        <button type="button" class="min-h-secondary flex-none rounded-xl border border-surface-line px-3 font-semibold text-brand-deep" :disabled="busy" @click="doLink('change')">Change</button>
      </section>
      <div v-if="isBuy && redBar" class="sticky top-14 z-20 rounded-xl border-2 border-danger-text bg-danger-bg p-3 text-[15px] font-bold text-danger-text" role="alert">
        ✗ {{ redBar }}
      </div>
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
        :kind="kind"
        :party-title="paper.party_title"
        :disabled="busy && busyIdx === l.idx"
        :last="(paper.last_bought || {})[l.item_code] || null"
        :usual-discount="paper.usual_discount"
        @ok="decide(l, 'ok')"
        @leave="decide(l, 'left')"
        @undo="decide(l, null)"
        @change="choosing = l"
        @qty="(v) => change(l, { qty: v === '' ? null : Number(v) })"
        @uom="(v) => change(l, { uom: v })"
        @rate="(v) => change(l, { rate: v === '' ? null : Number(v) })"
        @fix="change(l, { fix: 'qty' })"
        @read="(r) => change(l, r)"
        @last="lastOf = l"
      />

      <details v-if="isBuy && paper.not_on_paper && paper.not_on_paper.length" class="rounded-xl border border-surface-line bg-surface p-3">
        <summary class="cursor-pointer font-semibold">On the {{ linkKindShort }}, not on this paper · {{ paper.not_on_paper.length }} line{{ paper.not_on_paper.length === 1 ? "" : "s" }}</summary>
        <p class="mt-1 text-[13px] text-ink-faint">They stay due for the next delivery. Nothing is changed.</p>
        <div v-for="r in paper.not_on_paper" :key="r.doc + r.idx" class="mt-1 text-[14px]">{{ r.doc }} line {{ r.idx }} · {{ r.item_name }} · {{ fmt(r.due) }} {{ r.uom }}</div>
      </details>

      <section v-if="isBuy && paper.totals" class="tnum space-y-1 rounded-xl border border-surface-line bg-surface p-3 text-[14px]">
        <div class="flex justify-between gap-3"><span class="text-ink-muted">{{ kindTitle }} lines ({{ kept.length }})</span><b>₹{{ money(paper.totals.lines_net) }}</b></div>
        <div v-for="n in paper.totals.notes" :key="n.kind + n.idx" class="flex justify-between gap-3"><span class="text-ink-muted">{{ n.kind === "left" ? `Left out (line ${n.idx})` : `Not received (line ${n.idx}, ${fmt(n.qty)})` }}</span><span>₹{{ money(n.amount) }}</span></div>
        <div v-if="paper.totals.against" class="flex justify-between gap-3"><span class="text-ink-muted">{{ paper.totals.against.kind === "items" ? "Paper's item total" : "Paper's total less tax and charges" }}</span><b>₹{{ money(paper.totals.against.amount) }}</b></div>
        <div v-if="(paper.charges || []).length" class="flex justify-between gap-3"><span class="text-ink-muted">Charges on the paper</span><span>{{ paper.charges.map((c) => `${c.label} ₹${money0(c.amount)}`).join(", ") }}</span></div>
        <div class="pt-1 font-semibold" :class="paper.totals.ok ? 'text-ok-text' : 'text-danger-text'">{{ totalsLine }}</div>
      </section>
      <section v-else class="tnum space-y-1 rounded-xl border border-surface-line bg-surface p-3 text-[14px]">
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
    <div v-if="paper && paper.status === 'Ready' && !linkStep" class="safe-bottom fixed inset-x-0 bottom-0 z-30 border-t border-surface-line bg-surface px-4 pt-3">
      <div class="mx-auto max-w-lg">
        <p v-if="blockReason" class="mb-2 text-center text-[14px] font-semibold text-warn-text">{{ blockReason }}</p>
        <button type="button" class="min-h-action w-full rounded-xl bg-brand-deep text-[17px] font-bold text-white disabled:opacity-40" :disabled="!!blockReason || busy || !paper.can_save" @click="openSave">
          {{ isBuy ? `Next: save the ${kindTitle}` : `Next: make the ${isPo ? "Purchase Order" : "Sales Order"}` }}
        </button>
      </div>
    </div>

    <PurchaseSave
      v-if="saveOpen && isBuy"
      :paper="paper"
      :kept="kept"
      :left-out="leftOut"
      :queue="() => queue"
      @close="saveOpen = false"
      @conflict="onSaveConflict"
      @saved="onPurchaseSaved"
    />
    <LastBoughtSheet v-if="lastOf" :line="lastOf" :last="(paper.last_bought || {})[lastOf.item_code] || null" :usual="paper.usual_discount" :party-title="paper.party_title" :buy="isBuy" @close="lastOf = null" />

    <!-- Save -->
    <div v-if="saveOpen && !isBuy" class="fixed inset-0 z-40 flex flex-col bg-surface-page">
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
    <ChooseItemSheet v-if="choosing" :line="choosing" :party-title="paper.party_title" :paper-name="paper.name" @pick="pickItem" @leave="leaveChoosing" @close="choosing = null" />
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue"

import AppHeader from "@/components/AppHeader.vue"
import ChooseItemSheet from "@/components/ChooseItemSheet.vue"
import LastBoughtSheet from "@/components/LastBoughtSheet.vue"
import PaperLine from "@/components/PaperLine.vue"
import PaperLinkStep from "@/components/PaperLinkStep.vue"
import PaperReading from "@/components/PaperReading.vue"
import PartySheet from "@/components/PartySheet.vue"
import PurchaseSave from "@/components/PurchaseSave.vue"
import { newRef } from "@/data/draft.js"
import { fmt, fmtDate } from "@/data/format.js"
import {
  PURPOSE,
  discardPaper,
  getPaper,
  makeBill,
  money,
  money0,
  purposeKey,
  rereadPaper,
  saveOrder,
  searchSchools,
  sentPages,
  setLinks,
  setParty,
  updateLines,
  lastCompare,
} from "@/data/paper.js"
import { useRouter } from "vue-router"

const props = defineProps({ name: { type: String, required: true } })

const paper = ref(null)
const loadError = ref("")
const actionError = ref("")
const busy = ref(false)
const busyIdx = ref(null)
const flash = ref(null)
const elapsed = ref(0)
const live = ref(null) // the lines read so far, while the AI is still writing
const finishing = ref(false)
const found = ref(0)
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

const router = useRouter()
const lastOf = ref(null)
const isPo = computed(() => !paper.value || paper.value.purpose !== "Sales Order")
const kind = computed(() => (paper.value ? purposeKey(paper.value.purpose) : "po"))
const isBuy = computed(() => kind.value === "pr" || kind.value === "pi")
const kindTitle = computed(() => PURPOSE[kind.value].title)
const partyLabel = computed(() => (isPo.value ? "Supplier" : "Customer"))
const reading = computed(() => paper.value && ["Uploaded", "Reading"].includes(paper.value.status))
const lines = computed(() => paper.value?.lines || [])
const copies = computed(() => paper.value?.copies || 0)
const newLink = computed(() => `/paper?for=${kind.value}`)
const title = computed(() => {
  if (!paper.value) return "Order from paper"
  if (reading.value) return "Reading"
  if (paper.value.status === "Saved") return "Saved"
  if (linkStep.value) return kind.value === "pi" ? "Link the bill" : "Link the PO"
  if (paper.value.status === "Ready" && isBuy.value) return `${kindTitle.value} from paper`
  if (paper.value.status === "Ready") return isPo.value ? "Check the lines" : "Check the lines · Sales Order"
  return "Order from paper"
})
const linkStep = computed(() => !!paper.value && isBuy.value && paper.value.status === "Ready" && !paper.value.links)
const linkKindShort = computed(() => (paper.value?.links?.doctype === "Purchase Receipt" ? "Receipt" : "PO"))
const linkedText = computed(() => {
  const l = paper.value?.links || {}
  if (l.mode === "docs") return l.docs.join(", ")
  return kind.value === "pi" ? "Nothing — the bill adds the stock" : "No PO"
})
// the money check: red until the lines add up to the paper (both save buttons stay off)
const redBar = computed(() => {
  const p = paper.value
  if (!p || !isBuy.value || !p.totals) return ""
  const probs = (p.problems || []).length
  const miss = (p.totals.missing_bill_lines || []).length
  const bits = []
  if (!p.totals.ok && p.totals.against && !miss) {
    const d = Number(p.totals.diff || 0)
    bits.push(`₹${money(Math.abs(d))} ${d < 0 ? "short of" : "more than"} the paper`)
  }
  if (miss) bits.push(`${miss} line${miss === 1 ? "" : "s"} left out — a Bill must carry every line`)
  if (probs) bits.push(`${probs} line${probs === 1 ? "" : "s"} to fix`)
  return bits.join(" · ")
})
const totalsLine = computed(() => {
  const t = paper.value?.totals
  if (!t) return ""
  if (!t.has_total) return "No total printed on the paper — each line is checked on its own."
  if (t.ok) return t.gross_needed ? "✓ Lines add up. The grand total with GST is checked on the next screen." : "✓ Adds up to the paper."
  return `✗ ₹${money(Math.abs(t.diff))} ${t.diff < 0 ? "short of" : "more than"} the paper`
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
  if (isBuy.value) {
    const probs = (paper.value.problems || []).length
    if (probs) return `Fix ${probs} line${probs === 1 ? "" : "s"} first`
    const t = paper.value.totals || {}
    if ((t.missing_bill_lines || []).length) return "A Bill must carry every line of the paper"
    if (!t.ok && !t.gross_needed) return "The lines don't add up to the paper yet"
  }
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
const docUrl = computed(() => `/app/${PURPOSE[kind.value].slug}/${encodeURIComponent(paper.value?.created_doc || "")}`)
// dearer than the last bill (per stock unit, after its discount) — shown, never changed
const rateWarnings = computed(() =>
  kept.value
    .map((l) => {
      const c = lastCompare(l, (paper.value.last_bought || {})[l.item_code], false)
      if (!c || !c.dearer) return null
      return `${l.item_name}: ₹${money(l.paper_rate / (Number(l.conversion_factor) || 1))} a copy on this paper, ₹${money(c.prev.rate)} on ${c.prev.doc} (${fmtDate(c.prev.date)}). ${c.chips.map((x) => x.text).join(" · ")}`
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
let finishTimer = null
let started = Date.now()
async function load() {
  loadError.value = ""
  try {
    paper.value = await getPaper(props.name)
    finishing.value = false
    if (reading.value) {
      mergeLive(paper.value.live)
      schedulePoll()
    }
  } catch (e) {
    loadError.value = msg(e, "Could not load the paper.")
  }
}
// a poll brings only the lines added since the last one (same run); a new run = start over
function mergeLive(l) {
  if (!l) return
  const had = live.value
  live.value = !had || had.run !== l.run ? { ...l, lines: [...(l.lines || [])] } : { ...l, lines: had.lines.slice(0, l.since).concat(l.lines || []) }
}
function schedulePoll() {
  clearTimeout(pollTimer)
  pollTimer = setTimeout(poll, 2000)
}
async function poll() {
  elapsed.value = Math.round((Date.now() - started) / 1000)
  try {
    const r = await getPaper(props.name, 1, live.value?.lines.length || 0, live.value?.run || null)
    if (["Uploaded", "Reading"].includes(r.status)) {
      mergeLive(r.live)
      schedulePoll()
    } else if (r.status === "Ready") {
      // the poll returned the whole paper: the tick with the real line count, then the check screen
      found.value = (r.lines || []).length
      finishing.value = true
      clearTimeout(finishTimer)
      finishTimer = setTimeout(() => {
        paper.value = r
        finishing.value = false
      }, 1300)
    } else await load()
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
      for (const k of ["totals", "problems", "not_on_paper"]) if (r[k] !== undefined) paper.value[k] = r[k]
      if (lastOf.value) lastOf.value = paper.value.lines.find((l) => l.idx === lastOf.value.idx) || null
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
    if (!r.conflict && reading.value) {
      // another supplier on a Receipt / Bill: matched again in the background
      started = Date.now()
      live.value = null
      schedulePoll()
    }
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
    live.value = null
    finishing.value = false
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

// ── Receipt / Bill: links, save, the bill from the same reading ────────────
async function doLink(mode, docs = []) {
  actionError.value = ""
  await queue
  busy.value = true
  try {
    const r = await setLinks(props.name, mode, docs, paper.value.version)
    paper.value = r.conflict ? r.paper : r
    if (r.conflict) say("Someone else changed this paper — it was reloaded.")
    window.scrollTo(0, 0)
  } catch (e) {
    actionError.value = msg(e, "Could not link it.")
    say(actionError.value)
  } finally {
    busy.value = false
  }
}
function onSaveConflict(p) {
  paper.value = p
  saveOpen.value = false
  say("Someone else changed this paper — check it again.")
}
async function onPurchaseSaved(r) {
  done.value = r
  saveOpen.value = false
  await load()
  window.scrollTo(0, 0)
}
async function doMakeBill() {
  actionError.value = ""
  busy.value = true
  try {
    const r = await makeBill(props.name)
    router.push(`/paper/${encodeURIComponent(r.name)}`)
  } catch (e) {
    actionError.value = msg(e, "Could not make the bill.")
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
  live.value = null
  load()
})
onMounted(load)
onBeforeUnmount(() => {
  clearTimeout(pollTimer)
  clearTimeout(finishTimer)
  clearTimeout(flashTimer)
  clearTimeout(copiesTimer)
  clearTimeout(schoolTimer)
})
</script>
