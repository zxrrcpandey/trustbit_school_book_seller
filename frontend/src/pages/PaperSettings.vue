<template>
  <div class="pb-28">
    <AppHeader title="Order from paper · Settings" back="/home" />
    <div v-if="error && !data" class="m-4 rounded-lg bg-danger-bg p-3 text-danger-text">{{ error }}</div>
    <div v-else-if="!data" class="space-y-3 p-4"><div class="skeleton h-32" /><div class="skeleton h-40" /></div>

    <main v-else class="space-y-4 p-4">
      <p class="text-[13px] text-ink-faint">Only System Manager and Shop Owner can change these. A change works from the next paper.</p>

      <section class="space-y-2 rounded-2xl border border-surface-line bg-surface p-4">
        <label class="flex min-h-secondary items-center justify-between gap-3 text-[15px] font-semibold">
          Order from paper is on
          <input v-model="v.enabled" type="checkbox" class="h-6 w-6 accent-[var(--kgs-brand-deep)]" />
        </label>
        <label class="flex min-h-secondary items-center justify-between gap-3 text-[15px] font-semibold">
          Sales Orders from paper are on
          <input v-model="v.so_enabled" type="checkbox" class="h-6 w-6 accent-[var(--kgs-brand-deep)]" />
        </label>
        <p class="text-[13px] text-ink-faint">Off: the tile disappears from the staff app and nothing can be read.</p>
      </section>

      <section class="space-y-2 rounded-2xl border border-surface-line bg-surface p-4">
        <h2 class="text-[15px] font-extrabold">AI provider</h2>
        <div v-for="p in data.providers" :key="p.name" class="flex items-center gap-3 rounded-xl px-3 py-3" :class="p.active ? 'border-2 border-brand-deep bg-brand-soft' : 'border border-dashed border-ink-faint text-ink-muted'">
          <span class="flex-1 font-bold">{{ p.label }}</span>
          <span class="rounded-full px-3 py-[2px] text-[12px] font-bold" :class="p.active ? 'bg-brand-deep text-white' : 'bg-surface-line text-ink-muted'">{{ p.active ? (v.provider === p.name ? "In use" : "Ready") : "Coming soon" }}</span>
        </div>
        <p class="text-[13px]" :class="data.key_set ? 'text-ok-text' : 'font-semibold text-danger-text'">
          {{ data.key_set ? "The AI key is set on the server." : data.fake ? "Test mode: no AI key, a fixed sample reading is used." : "No AI key on the server yet — papers cannot be read. Trustbit sets it (it is never shown here)." }}
        </p>
      </section>

      <section class="space-y-2 rounded-2xl border border-surface-line bg-surface p-4">
        <h2 class="text-[15px] font-extrabold">Model for reading</h2>
        <button
          v-for="m in models"
          :key="m.model"
          type="button"
          class="flex w-full items-center gap-3 rounded-xl bg-surface px-3 py-3 text-left"
          :class="v.ai_model === m.model ? 'border-2 border-brand-deep' : 'border border-surface-line'"
          :aria-pressed="v.ai_model === m.model"
          @click="v.ai_model = m.model"
        >
          <span class="h-[18px] w-[18px] flex-none rounded-full" :class="v.ai_model === m.model ? 'border-[6px] border-brand-deep' : 'border-2 border-ink-faint'" />
          <span class="min-w-0 flex-1"><span class="block font-bold">{{ m.label }}</span><span class="block text-[13px] text-ink-faint">{{ m.note }}</span></span>
          <span class="tnum text-[13px] font-bold text-ink-muted">≈ ₹{{ m.inr_per_page.toFixed(2) }}</span>
        </button>
        <p class="text-[12px] text-ink-faint">Estimated price per page, including {{ v.gst_percent }}% GST, at ₹{{ v.usd_rate }} per dollar. The real cost of each paper is counted below.</p>
      </section>

      <section class="space-y-3 rounded-2xl border border-surface-line bg-surface p-4">
        <h2 class="text-[15px] font-extrabold">When a reading looks wrong</h2>
        <label class="flex items-center gap-3 text-[15px]">
          <input v-model="v.auto_fallback" type="checkbox" class="h-6 w-6 accent-[var(--kgs-brand-deep)]" />
          Read again once with a better model
        </label>
        <label v-if="v.auto_fallback" class="block text-[14px] font-semibold text-ink-muted">
          Better model
          <select v-model="v.fallback_model" class="mt-1 h-12 w-full rounded-lg border border-surface-line bg-surface px-2 text-[16px] text-ink">
            <option v-for="m in models" :key="m.model" :value="m.model">{{ m.label }}</option>
          </select>
        </label>
        <p class="text-[13px] text-ink-faint">"Looks wrong" = the lines do not add up to the paper's total, or 2 or more lines could not be read.</p>
        <label class="flex items-center gap-3 text-[15px]">
          <input v-model="v.rerank" type="checkbox" class="h-6 w-6 accent-[var(--kgs-brand-deep)]" />
          AI double-check of unsure lines
        </label>
        <p class="text-[13px] text-ink-faint">A short extra question per paper: the AI picks among OUR closest items. The line still needs one tap.</p>
      </section>

      <section class="space-y-3 rounded-2xl border border-surface-line bg-surface p-4">
        <h2 class="text-[15px] font-extrabold">Spending</h2>
        <label class="flex items-center justify-between gap-3 text-[15px]">
          Monthly page limit
          <input v-model.number="v.month_page_limit" type="number" min="0" inputmode="numeric" class="tnum h-11 w-24 rounded-lg border border-surface-line text-center font-bold" />
        </label>
        <label class="flex items-center justify-between gap-3 text-[15px]">
          Limit in March and April
          <input v-model.number="v.peak_month_page_limit" type="number" min="0" inputmode="numeric" class="tnum h-11 w-24 rounded-lg border border-surface-line text-center font-bold" />
        </label>
        <div class="grid grid-cols-2 gap-3">
          <label class="text-[14px] font-semibold text-ink-muted">₹ per dollar<input v-model.number="v.usd_rate" type="number" min="1" step="0.01" class="tnum mt-1 h-11 w-full rounded-lg border border-surface-line text-center font-bold text-ink" /></label>
          <label class="text-[14px] font-semibold text-ink-muted">GST %<input v-model.number="v.gst_percent" type="number" min="0" step="0.01" class="tnum mt-1 h-11 w-full rounded-lg border border-surface-line text-center font-bold text-ink" /></label>
        </div>
        <div class="tnum space-y-1 border-t border-surface-line pt-3 text-[14px]">
          <div class="font-bold">{{ data.usage.month }} so far</div>
          <div v-if="!data.usage.models.length" class="text-ink-muted">Nothing read yet this month.</div>
          <div v-for="u in data.usage.models" :key="u.model" class="flex justify-between gap-3">
            <span class="text-ink-muted">{{ u.label }} · {{ u.pages }} page{{ u.pages === 1 ? "" : "s" }}, {{ u.calls }} call{{ u.calls === 1 ? "" : "s" }}</span><b>₹{{ u.inr_gst.toFixed(2) }}</b>
          </div>
          <div class="flex justify-between gap-3 text-[15px]">
            <span>Total incl. GST ({{ data.usage.pages }} of {{ data.usage.limit || "∞" }} pages)</span><b>₹{{ data.usage.inr_gst.toFixed(2) }}</b>
          </div>
        </div>
      </section>

      <section class="space-y-2 rounded-2xl border border-surface-line bg-surface p-4">
        <button type="button" class="flex w-full items-center justify-between text-left text-[15px] font-extrabold" :aria-expanded="pricesOpen" @click="pricesOpen = !pricesOpen">
          Model prices (USD per million tokens) <span>{{ pricesOpen ? "▴" : "▾" }}</span>
        </button>
        <template v-if="pricesOpen">
          <p class="text-[13px] text-ink-faint">Change these when Anthropic changes its prices. A newer model needs a row here before it can be chosen.</p>
          <div v-for="(m, i) in models" :key="i" class="space-y-2 rounded-xl border border-surface-line p-3">
            <input v-model="m.model" placeholder="Model id, e.g. claude-haiku-5-5" class="h-11 w-full rounded-lg border border-surface-line px-3 font-mono text-[14px]" aria-label="Model id" />
            <input v-model="m.label" placeholder="Shown as" class="h-11 w-full rounded-lg border border-surface-line px-3" aria-label="Shown as" />
            <div class="grid grid-cols-2 gap-2">
              <label class="text-[13px] text-ink-muted">Input $<input v-model.number="m.input_per_mtok" type="number" min="0" step="0.001" class="tnum mt-1 h-11 w-full rounded-lg border border-surface-line text-center text-ink" /></label>
              <label class="text-[13px] text-ink-muted">Output $<input v-model.number="m.output_per_mtok" type="number" min="0" step="0.001" class="tnum mt-1 h-11 w-full rounded-lg border border-surface-line text-center text-ink" /></label>
            </div>
            <input v-model="m.note" placeholder="Note, e.g. Better on handwriting" class="h-11 w-full rounded-lg border border-surface-line px-3" aria-label="Note" />
            <button v-if="models.length > 1 && m.model !== v.ai_model && m.model !== v.fallback_model" type="button" class="text-[14px] font-semibold text-danger-text" @click="models.splice(i, 1)">Remove this model</button>
          </div>
          <button type="button" class="min-h-secondary w-full rounded-xl border border-surface-line font-semibold text-brand-deep" @click="models.push({ model: '', label: '', note: '', input_per_mtok: 0, output_per_mtok: 0, inr_per_page: 0 })">Add a model</button>
        </template>
      </section>
      <p v-if="error" class="rounded-lg bg-danger-bg p-3 font-semibold text-danger-text">{{ error }}</p>
      <p v-if="saved" class="rounded-lg bg-ok-bg p-3 font-semibold text-ok-text">Saved. The next paper uses these settings.</p>
    </main>

    <div v-if="data" class="safe-bottom fixed inset-x-0 bottom-0 z-30 border-t border-surface-line bg-surface px-4 pt-3">
      <div class="mx-auto max-w-lg">
        <button type="button" class="min-h-action w-full rounded-xl bg-brand-deep text-[18px] font-bold text-white disabled:opacity-40" :disabled="busy" @click="save">{{ busy ? "Saving…" : "Save settings" }}</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue"

import AppHeader from "@/components/AppHeader.vue"
import { getPaperSettings, savePaperSettings } from "@/data/paper.js"

const data = ref(null)
const v = reactive({})
const models = ref([])
const error = ref("")
const busy = ref(false)
const saved = ref(false)
const pricesOpen = ref(false)

function apply(d) {
  data.value = d
  Object.assign(v, d.values)
  for (const k of ["enabled", "so_enabled", "auto_fallback", "rerank"]) v[k] = !!Number(v[k])
  models.value = d.models.map((m) => ({ ...m }))
}

async function save() {
  error.value = ""
  saved.value = false
  busy.value = true
  try {
    const values = { ...v, models: models.value.filter((m) => String(m.model || "").trim()) }
    for (const k of ["enabled", "so_enabled", "auto_fallback", "rerank"]) values[k] = values[k] ? 1 : 0
    apply(await savePaperSettings(values))
    saved.value = true
  } catch (e) {
    error.value = e.display ? e.display() : "Could not save."
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  try {
    apply(await getPaperSettings())
  } catch (e) {
    error.value = e.display ? e.display() : "Could not load the settings."
  }
})
</script>
