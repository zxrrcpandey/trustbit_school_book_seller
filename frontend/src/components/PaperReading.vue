<template>
  <main class="reading px-4 pb-10 pt-5" :class="{ rm: reduced }">
    <p class="h-5 truncate text-center text-[13px] text-ink-muted">{{ fromLine }}</p>
    <div class="stage">
      <!-- the pages, with real progress: ticked = read, outlined = being read -->
      <div ref="stripEl" class="strip" :class="{ fits }">
        <div
          v-for="k in pageCount"
          :key="k"
          class="th"
          :class="{ done: isDone(k), on: !isDone(k) && started && k === cur, todo: !isDone(k) && !(started && k === cur) }"
          :aria-label="`${Word} ${k}${isDone(k) ? ', read' : ''}`"
        >
          <img v-if="pics[k - 1]" :src="pics[k - 1]" alt="" :class="isPdf ? 'contain' : 'cover'" />
          <span v-else class="plain" aria-hidden="true"><i /><i /><i /><i /></span>
          <b>{{ k }}</b>
        </div>
      </div>

      <!-- the page being read -->
      <div class="main">
        <Transition name="turn">
          <div :key="cur" class="mpage" :class="{ sheet: !pics[cur - 1] }">
            <img v-if="pics[cur - 1]" :src="pics[cur - 1]" :alt="`${Word} ${cur}`" />
            <span v-else class="plain big" aria-hidden="true"><i /><i /><i /><i /><i /><i /><i /><em>{{ cur }}</em></span>
            <i v-if="sweeping" class="sweep" aria-hidden="true" />
            <span v-if="isPdf" class="pdfmark">PDF</span>
          </div>
        </Transition>
      </div>

      <!-- each line as the AI writes it: title, quantity and rate as printed -->
      <TransitionGroup name="card" tag="div" class="cards">
        <div v-for="c in cards" :key="c.key" class="lc">
          <b>{{ c.text }}</b>
          <span class="qr tnum">{{ qtyRate(c) }}</span>
          <em v-if="pageCount > 1">p{{ c.page }}</em>
        </div>
      </TransitionGroup>

      <div v-if="finished" class="finish">
        <svg viewBox="0 0 52 52" aria-hidden="true"><circle cx="26" cy="26" r="25" /><path d="M15 27 l7 7 l15 -16" /></svg>
        <span>{{ lineCount }} line{{ lineCount === 1 ? "" : "s" }} found<br />on {{ pageCount }} {{ word }}{{ pageCount === 1 ? "" : "s" }}</span>
      </div>
    </div>

    <div class="mt-3 text-center">
      <div class="text-[20px] font-bold" :class="finished ? 'text-ok-text' : ''" role="status">{{ title }}</div>
      <p class="tnum mt-1 text-ink-muted">{{ sub }}</p>
      <p v-if="note" class="mt-2 rounded-lg p-2 text-[14px]" :class="fallback ? 'bg-warn-bg font-semibold text-warn-text' : 'text-ink-muted'">{{ note }}</p>
      <p class="mt-2 text-[14px] text-ink-faint">
        You can leave this screen — the paper waits under <router-link to="/papers" class="font-semibold text-brand-deep">Papers</router-link>.
      </p>
    </div>
  </main>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"

import { fmt } from "@/data/format.js"
import { money } from "@/data/paper.js"
import { drawPdfPages } from "@/data/pdfPages.js"

// live = {run, attempt, phase, model, note, party, no, count, lines: [{text, qty, unit, rate, mrp, amount, page}]}
const props = defineProps({
  files: { type: Array, default: () => [] }, // the stored copies [{url, kind}]
  local: { type: Array, default: null }, // the pages this phone just sent [{kind, preview, data}]
  pages: { type: Number, default: 1 },
  live: { type: Object, default: null },
  elapsed: { type: Number, default: 0 },
  finished: { type: Boolean, default: false },
  found: { type: Number, default: 0 }, // the real number of lines, once the reading is done
})

const reduced = typeof window !== "undefined" && window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)").matches : false
const isPdf = computed(() => (props.local?.[0]?.kind || props.files?.[0]?.kind) === "pdf")
const pageCount = computed(() => Math.max(1, props.pages || props.files?.length || 1))
const word = computed(() => (isPdf.value ? "page" : "photo"))
const Word = computed(() => (isPdf.value ? "Page" : "Photo"))
const lines = computed(() => props.live?.lines || [])
const lineCount = computed(() => (props.finished && props.found) || Math.max(props.live?.count || 0, lines.value.length))
const matching = computed(() => props.live?.phase === "matching")
const fallback = computed(() => (props.live?.attempt || 0) > 1)
const note = computed(() => props.live?.note || "")

// ── playing the lines as cards, a little behind the 2-second polls ─────────
const shown = ref(0)
const cards = ref([])
const maxPage = ref(1)
let runSeen
let timer = null

const pageOf = (l) => Math.min(pageCount.value, Math.max(1, Number(l?.page) || 1))
const started = computed(() => shown.value > 0)
const cur = computed(() => maxPage.value)
const isDone = (k) => props.finished || matching.value || (started.value && k < cur.value)
const sweeping = computed(() => !props.finished && !matching.value && !reduced)

function step() {
  timer = null
  const ls = lines.value
  if (shown.value >= ls.length) return
  const l = ls[shown.value]
  shown.value++
  maxPage.value = Math.max(maxPage.value, pageOf(l))
  cards.value = [{ ...l, key: `${runSeen}:${shown.value}` }, ...cards.value].slice(0, 3)
  const left = ls.length - shown.value
  if (left > 0) timer = setTimeout(step, Math.min(450, Math.max(90, 1800 / left)))
}

watch(
  () => [props.live?.run, lines.value.length],
  () => {
    const run = props.live?.run || null
    if (run !== runSeen) {
      // a new reading (or the better model starting over): drop the cards
      runSeen = run
      clearTimeout(timer)
      timer = null
      cards.value = []
      shown.value = Math.max(0, lines.value.length - 3) // opened mid-way: play only the last few
      maxPage.value = shown.value ? pageOf(lines.value[shown.value - 1]) : 1
    }
    if (reduced) {
      shown.value = lines.value.length
      cards.value = lines.value.slice(-3).reverse().map((l, i) => ({ ...l, key: `${runSeen}:${shown.value - i}` }))
      if (lines.value.length) maxPage.value = Math.max(maxPage.value, pageOf(lines.value[lines.value.length - 1]))
    } else if (!timer && shown.value < lines.value.length) {
      timer = setTimeout(step, 0)
    }
  },
  { immediate: true }
)

function qtyRate(l) {
  const q = l.qty != null ? `${fmt(l.qty)}${l.unit ? ` ${l.unit}` : ""}` : ""
  if (l.rate) return q ? `${q} × ${money(l.rate)}` : money(l.rate)
  if (l.mrp) return `${q ? `${q} · ` : ""}MRP ${money(l.mrp)}`
  return q
}

// ── texts ───────────────────────────────────────────────────────────────────
const fromLine = computed(() => [props.live?.party, props.live?.no].filter(Boolean).join(" · "))
const secs = computed(() => (props.elapsed > 5 ? ` · ${props.elapsed} s` : ""))
const title = computed(() => {
  if (props.finished) return "Done. Opening the lines…"
  if (matching.value) return "Matching with our items…"
  if (fallback.value) return "Reading again more carefully…"
  return "Reading the paper…"
})
const sub = computed(() => {
  const n = pageCount.value
  if (props.finished || matching.value) return `${lineCount.value} line${lineCount.value === 1 ? "" : "s"} read${secs.value}`
  if (started.value) return `${Word.value} ${cur.value} of ${n} · ${shown.value} line${shown.value === 1 ? "" : "s"} so far${secs.value}`
  return `${n} ${word.value}${n === 1 ? "" : "s"} · ${n >= 6 ? "can take a few minutes" : "usually under a minute"}${secs.value}`
})

// ── page pictures: the photos as sent, or the PDF drawn by pdf.js ───────────
const pics = ref([])
let stopped = false
onMounted(() => {
  if (isPdf.value) {
    const src = props.local?.[0]?.data ? { data: props.local[0].data } : props.files?.[0]?.url ? { url: props.files[0].url } : null
    if (src) {
      drawPdfPages(src, pageCount.value, 240, (i, url) => (pics.value[i] = url), () => stopped).catch(() => {
        // pdf.js missing or the PDF unreadable here: plain sheets stand in
      })
    }
  } else {
    pics.value = props.local?.length ? props.local.map((p) => p.preview) : props.files.map((f) => f.url)
  }
})

// keep the page being read in view in a long strip
const stripEl = ref(null)
const fits = computed(() => pageCount.value * 40 + 10 <= 330)
watch(cur, async () => {
  await nextTick()
  const el = stripEl.value
  const th = el && el.children[cur.value - 1]
  if (el && th && !fits.value) el.scrollTo({ left: th.offsetLeft - (el.clientWidth - th.clientWidth) / 2, behavior: reduced ? "auto" : "smooth" })
})

onBeforeUnmount(() => {
  stopped = true
  clearTimeout(timer)
})
</script>

<style scoped>
.stage {
  position: relative;
  max-width: 340px;
  height: 364px;
  margin: 8px auto 0;
}
.strip {
  display: flex;
  gap: 6px;
  height: 58px;
  padding: 7px 8px;
  overflow-x: auto;
  scrollbar-width: none;
  border-radius: 10px;
  background: var(--kgs-strip);
}
.strip::-webkit-scrollbar {
  display: none;
}
.strip.fits {
  justify-content: center;
}
.th {
  position: relative;
  flex: none;
  width: 34px;
  height: 44px;
  overflow: visible;
  border-radius: 4px;
  background: var(--kgs-surface);
  box-shadow: 0 1px 3px var(--kgs-shadow);
  transition: opacity 0.3s, box-shadow 0.3s, transform 0.3s;
}
.th img {
  width: 100%;
  height: 100%;
  border-radius: 4px;
}
.th img.cover {
  object-fit: cover;
}
.th img.contain {
  object-fit: contain;
}
.th.todo {
  opacity: 0.45;
}
.th.on {
  box-shadow: 0 0 0 2px var(--kgs-brand);
  transform: translateY(-1px);
}
.th.done::after {
  content: "";
  position: absolute;
  right: -4px;
  top: -4px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--kgs-brand) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 12'%3E%3Cpath d='M2.5 6.2l2.3 2.3 4.7-5' fill='none' stroke='white' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E") center / 9px no-repeat;
}
.th b {
  position: absolute;
  right: 2px;
  bottom: 2px;
  padding: 1px 3px;
  border-radius: 3px;
  font-size: 9px;
  line-height: 1;
  color: var(--kgs-surface);
  background: var(--kgs-badge);
}
.plain {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
  height: 100%;
  padding: 6px 5px;
  border-radius: 4px;
  background: var(--kgs-surface);
}
.plain i {
  display: block;
  height: 3px;
  border-radius: 2px;
  background: var(--kgs-sheet-bar);
}
.plain i:first-child {
  width: 60%;
}
.main {
  position: relative;
  height: 170px;
  margin-top: 10px;
}
.mpage {
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  width: fit-content;
  height: 170px;
  max-width: 100%;
  margin: 0 auto;
  overflow: hidden;
  border-radius: 4px;
  background: var(--kgs-surface);
  box-shadow: 0 6px 16px var(--kgs-shadow);
}
.mpage img {
  display: block;
  height: 170px;
  width: auto;
  max-width: 300px;
  object-fit: contain;
}
.mpage.sheet {
  width: 124px;
}
.plain.big {
  position: relative;
  gap: 10px;
  padding: 16px 14px;
}
.plain.big i {
  height: 6px;
}
.plain.big em {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 10px;
  text-align: center;
  font-style: normal;
  font-weight: 700;
  color: var(--kgs-ink-faint);
}
.pdfmark {
  position: absolute;
  right: 4px;
  top: 4px;
  padding: 2px 4px;
  border-radius: 3px;
  font-size: 8px;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: var(--kgs-surface);
  background: var(--kgs-pdf);
}
/* a band sweeping down the page while the AI reads it (where on the page is not known) */
.sweep {
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  height: 18px;
  background: var(--kgs-scan);
  box-shadow: 0 1px 0 var(--kgs-scan-edge), 0 -1px 0 var(--kgs-scan-edge);
  animation: sweep 2.6s ease-in-out infinite;
}
@keyframes sweep {
  0% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(152px);
  }
  100% {
    transform: translateY(0);
  }
}
.turn-enter-active,
.turn-leave-active {
  transition: transform 0.45s ease, opacity 0.45s ease;
}
.turn-enter-from {
  opacity: 0;
  transform: translateX(10%) rotate(4deg);
}
.turn-leave-to {
  opacity: 0;
  transform: translateX(-160%) rotate(-6deg);
}
.cards {
  position: relative;
  height: 112px;
  margin-top: 12px;
  overflow: hidden;
}
.lc {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 32px;
  margin-bottom: 5px;
  padding: 0 8px;
  border: 1px solid var(--kgs-line);
  border-left: 3px solid var(--kgs-brand);
  border-radius: 8px;
  background: var(--kgs-surface);
  box-shadow: 0 2px 6px var(--kgs-shadow);
  font-size: 13px;
}
.lc b {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.lc .qr {
  white-space: nowrap;
  color: var(--kgs-ink-muted);
}
.lc em {
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 10px;
  font-style: normal;
  font-weight: 700;
  color: var(--kgs-surface);
  background: var(--kgs-ink-faint);
}
.card-enter-active {
  transition: transform 0.45s cubic-bezier(0.3, 0.7, 0.3, 1), opacity 0.35s;
}
.card-enter-from {
  opacity: 0;
  transform: translateY(-70px) scale(0.6);
}
.card-move {
  transition: transform 0.4s ease;
}
.card-leave-active {
  position: absolute;
  left: 0;
  right: 0;
  transition: opacity 0.3s;
}
.card-leave-to {
  opacity: 0;
}
.finish {
  position: absolute;
  inset: 0;
  z-index: 2;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 10px;
  text-align: center;
  font-weight: 700;
  color: var(--kgs-ok-text);
  background: var(--kgs-page);
}
.finish svg {
  width: 76px;
  height: 76px;
  animation: pop 0.5s cubic-bezier(0.3, 1.5, 0.5, 1) both;
}
.finish circle {
  fill: var(--kgs-brand);
}
.finish path {
  fill: none;
  stroke: var(--kgs-surface);
  stroke-width: 4;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-dasharray: 36;
  stroke-dashoffset: 36;
  animation: draw 0.35s 0.3s ease-out forwards;
}
@keyframes pop {
  from {
    transform: scale(0.4);
  }
  to {
    transform: scale(1);
  }
}
@keyframes draw {
  to {
    stroke-dashoffset: 0;
  }
}
.rm * {
  transition: none !important;
  animation: none !important;
}
.rm .finish path {
  stroke-dashoffset: 0;
}
</style>
