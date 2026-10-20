<template>
  <div class="pb-32">
    <AppHeader title="Order from paper" back="/home" />

    <div v-if="bootError" class="m-4 rounded-lg bg-danger-bg p-3 text-danger-text">{{ bootError }}</div>
    <div v-else-if="!info" class="space-y-3 p-4"><div class="skeleton h-24" /><div class="skeleton h-14" /></div>

    <main v-else class="space-y-4 p-4">
      <p v-if="!aiReady" class="rounded-xl border-2 border-warn-text bg-warn-bg p-3 text-[15px] font-semibold text-warn-text">
        The AI service is not set up yet, so papers cannot be read. Ask the office.
      </p>

      <section v-if="choices.length > 1">
        <h2 class="mb-2 text-[16px] font-bold">What should the paper become?</h2>
        <div class="grid grid-cols-2 gap-2">
          <button
            v-for="c in choices"
            :key="c.key"
            type="button"
            class="min-h-[72px] rounded-xl px-3 text-left"
            :class="purpose === c.key ? 'border-2 border-brand-deep bg-brand-soft' : 'border border-surface-line bg-surface'"
            :aria-pressed="purpose === c.key"
            @click="purpose = c.key"
          >
            <span class="block text-[16px] font-bold">{{ c.title }}</span>
            <span class="block text-[13px] text-ink-faint">{{ c.sub }}</span>
          </button>
        </div>
      </section>
      <h2 v-else class="text-[16px] font-bold">{{ purpose === "so" ? "Sales Order" : "Purchase Order" }} from a paper</h2>
      <p class="text-[14px] text-ink-muted">{{ hint }}</p>

      <section class="grid grid-cols-2 gap-2">
        <label class="flex min-h-action cursor-pointer items-center justify-center rounded-xl bg-brand-deep font-bold text-white" :class="busy || isPdf ? 'pointer-events-none opacity-40' : ''">
          <input type="file" accept="image/*" capture="environment" class="hidden" :disabled="busy || isPdf" @change="addFiles" />
          📷 Take photo
        </label>
        <label class="flex min-h-action cursor-pointer items-center justify-center rounded-xl border-2 border-brand-deep px-2 text-center font-bold text-brand-deep" :class="busy ? 'pointer-events-none opacity-40' : ''">
          <input type="file" accept="image/*,application/pdf" multiple class="hidden" :disabled="busy" @change="addFiles" />
          Choose PDF / photo
        </label>
      </section>

      <p v-if="error" class="rounded-lg bg-danger-bg p-3 font-semibold text-danger-text">{{ error }}</p>
      <p v-if="preparing" class="text-[14px] text-ink-muted">Getting the photo ready…</p>

      <section v-if="pages.length">
        <h3 class="mb-2 text-[15px] font-bold">{{ isPdf ? "PDF added" : `Pages added (${pages.length})` }}</h3>
        <div v-if="isPdf" class="flex items-center justify-between gap-3 rounded-xl border border-surface-line bg-surface p-3">
          <span class="min-w-0"><span class="block truncate font-semibold">📄 {{ pages[0].name }}</span><span class="text-[13px] text-ink-faint">{{ (pages[0].size / 1048576).toFixed(1) }} MB</span></span>
          <button type="button" class="h-11 w-11 flex-none rounded-full text-xl" aria-label="Remove the PDF" @click="remove(0)">×</button>
        </div>
        <div v-else class="grid grid-cols-3 gap-2">
          <div v-for="(p, i) in pages" :key="p.preview" class="relative overflow-hidden rounded-xl border border-surface-line bg-surface">
            <img :src="p.preview" :alt="`Page ${i + 1}`" class="aspect-[3/4] w-full object-cover" />
            <span class="absolute left-1 top-1 rounded-full bg-surface px-2 text-[13px] font-bold">{{ i + 1 }}</span>
            <button type="button" class="absolute right-1 top-1 h-9 w-9 rounded-full bg-surface text-lg font-bold" :aria-label="`Remove page ${i + 1}`" @click="remove(i)">×</button>
          </div>
        </div>
      </section>

      <section v-if="purpose === 'so'" class="rounded-xl border border-surface-line bg-surface p-3">
        <label for="copies" class="block text-[15px] font-semibold">Copies of each book <span class="font-normal text-ink-faint">(optional)</span></label>
        <p class="text-[13px] text-ink-faint">For a book list without quantities: this number goes on every line. You can change it on the next screen.</p>
        <input id="copies" v-model.number="copies" type="number" inputmode="numeric" min="0" max="10000" class="tnum mt-2 h-12 w-32 rounded-lg border border-surface-line text-center text-[18px] font-bold" />
      </section>

      <p class="text-[13px] text-ink-faint">
        For a good read: lay the paper flat, use good light, keep the whole page in the photo. Up to {{ info.paper.max_photos }} photos, or one PDF up to {{ info.paper.max_pages }} pages.
      </p>
    </main>

    <div v-if="info && pages.length" class="safe-bottom fixed inset-x-0 bottom-0 z-30 border-t border-surface-line bg-surface px-4 pt-3">
      <div class="mx-auto max-w-lg">
        <button type="button" class="min-h-action w-full rounded-xl bg-brand-deep text-[17px] font-bold text-white disabled:opacity-40" :disabled="busy || preparing || !aiReady" @click="send">
          {{ busy ? "Uploading…" : isPdf ? "Read the PDF" : `Read the paper (${pages.length} page${pages.length === 1 ? "" : "s"})` }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

import AppHeader from "@/components/AppHeader.vue"
import { boot } from "@/data/api.js"
import { newRef } from "@/data/draft.js"
import { PURPOSE, prepareFile, rememberSent, uploadPaper } from "@/data/paper.js"

const route = useRoute()
const router = useRouter()
const info = ref(null)
const bootError = ref("")
const purpose = ref(route.query.for === "so" ? "so" : "po")
const pages = ref([])
const copies = ref(null)
const busy = ref(false)
const preparing = ref(false)
const error = ref("")
// One reference per set of pages: a retry after a dropped connection returns
// the paper that was already uploaded instead of reading it twice.
let clientRef = newRef()

const choices = computed(() => {
  const p = info.value?.paper || {}
  const out = []
  if (p.po) out.push({ key: "po", title: "Purchase Order", sub: "we buy from a supplier" })
  if (p.so) out.push({ key: "so", title: "Sales Order", sub: "a school or shop buys" })
  return out
})
const aiReady = computed(() => !!info.value?.paper?.ready)
const isPdf = computed(() => pages.value.length === 1 && pages.value[0].kind === "pdf")
const hint = computed(() =>
  purpose.value === "po"
    ? "A quotation, price list or your own order list. The supplier is found from the GSTIN or name on the paper."
    : "A school book list or a shop's order. You choose the customer on the next screen."
)

watch(pages, () => (clientRef = newRef()), { deep: false })

async function addFiles(ev) {
  const files = Array.from(ev.target.files || [])
  ev.target.value = ""
  error.value = ""
  if (!files.length) return
  const max = info.value?.paper?.max_photos || 10
  preparing.value = true
  try {
    const added = []
    for (const f of files) added.push(await prepareFile(f))
    const all = [...pages.value, ...added]
    const pdfs = all.filter((p) => p.kind === "pdf")
    if (pdfs.length && all.length > 1) {
      error.value = "Send one PDF, or photos — not both."
      added.forEach((p) => p.preview && URL.revokeObjectURL(p.preview))
      return
    }
    if (all.length > max) {
      error.value = `Up to ${max} photos per paper.`
      added.forEach((p) => p.preview && URL.revokeObjectURL(p.preview))
      return
    }
    pages.value = all
  } catch (e) {
    error.value = e.message || "This file could not be added."
  } finally {
    preparing.value = false
  }
}

function remove(i) {
  const p = pages.value[i]
  if (p && p.preview) URL.revokeObjectURL(p.preview)
  pages.value = pages.value.filter((_, j) => j !== i)
}

async function send() {
  error.value = ""
  busy.value = true
  try {
    const res = await uploadPaper(
      PURPOSE[purpose.value].doctype,
      pages.value.map((p) => ({ name: p.name, data: p.data })),
      clientRef,
      purpose.value === "so" ? copies.value : null
    )
    rememberSent(res.name, pages.value)
    pages.value = [] // the previews now belong to the reading screen (not revoked on leaving)
    router.replace(`/paper/${encodeURIComponent(res.name)}`)
  } catch (e) {
    error.value = e.display ? e.display() : "The paper could not be uploaded. Please try again."
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  try {
    info.value = await boot()
    const p = info.value.paper || {}
    if (purpose.value === "so" && !p.so) purpose.value = "po"
    if (purpose.value === "po" && !p.po && p.so) purpose.value = "so"
    if (!p.po && !p.so) bootError.value = "Order from paper is not available for your account."
  } catch (e) {
    bootError.value = e.display ? e.display() : "Could not load."
  }
})
onBeforeUnmount(() => pages.value.forEach((p) => p.preview && URL.revokeObjectURL(p.preview)))
</script>
