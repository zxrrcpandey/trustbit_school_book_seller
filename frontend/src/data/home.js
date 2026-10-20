// My papers of the last 30 days, shared by Home ("Waiting for you", Recent)
// and the bottom bar's Papers badge, so switching tabs does not ask the
// server again and again. One request at a time; a fresh copy is reused.
import { computed, reactive } from "vue"

import { myPapers } from "./paper.js"

const state = reactive({ rows: null, at: 0 })
let inflight = null

export const myRecentPapers = computed(() => state.rows)
// what the person has to do something about: check a read paper, or read one again
export const papersToCheck = computed(() => (state.rows || []).filter((p) => p.status === "Ready"))
export const papersNotRead = computed(() => (state.rows || []).filter((p) => p.status === "Failed"))
export const paperBadge = computed(() => papersToCheck.value.length + papersNotRead.value.length)

export function loadMyPapers(maxAgeMs = 0) {
  if (inflight) return inflight
  if (state.rows && Date.now() - state.at < maxAgeMs) return Promise.resolve(state.rows)
  inflight = myPapers("mine", 30)
    .then((r) => {
      state.rows = r || []
      state.at = Date.now()
      return state.rows
    })
    .finally(() => {
      inflight = null
    })
  return inflight
}
