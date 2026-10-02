// The transfer being built is kept in localStorage (per user), so a reload, a
// closed app or an expired session never loses scanned lines. Cleared only
// after the server confirms the transfer. Storage can be missing (private
// mode) — every access is wrapped and the app works without it.
import { reactive, watch } from "vue"

import { session } from "./session.js"

const key = () => `kgs-staff-draft:${session.user || "?"}`
const LAST_PAIR = "kgs-staff-last-pair"

export function newRef() {
  if (window.crypto && crypto.randomUUID) return crypto.randomUUID()
  return "r-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 12)
}

function empty() {
  // sent = the exact request of a submit whose result is unknown (network
  // dropped). While set, the draft is locked and only that request is retried.
  return { from: "", to: "", lines: [], remarks: "", clientRef: newRef(), sent: null }
}

export const draft = reactive(empty())

export function loadDraft() {
  let saved = null
  try {
    saved = JSON.parse(localStorage.getItem(key()) || "null")
  } catch {
    saved = null
  }
  Object.assign(draft, empty(), saved || {})
  if (!draft.from && !draft.to) {
    try {
      const pair = JSON.parse(localStorage.getItem(LAST_PAIR) || "null")
      if (pair) Object.assign(draft, { from: pair.from || "", to: pair.to || "" })
    } catch {
      /* ignore */
    }
  }
  if (!draft.clientRef) draft.clientRef = newRef()
}

export function clearDraft({ keepWarehouses = false } = {}) {
  const { from, to } = draft
  Object.assign(draft, empty(), keepWarehouses ? { from, to } : {})
  try {
    localStorage.removeItem(key())
  } catch {
    /* ignore */
  }
}

export function rememberPair(from, to) {
  try {
    localStorage.setItem(LAST_PAIR, JSON.stringify({ from, to }))
  } catch {
    /* ignore */
  }
}

watch(
  draft,
  (d) => {
    try {
      if (d.lines.length || d.remarks || d.sent) localStorage.setItem(key(), JSON.stringify(d))
      else localStorage.removeItem(key())
    } catch {
      /* ignore */
    }
  },
  { deep: true }
)
