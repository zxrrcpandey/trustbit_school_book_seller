// Order from Paper — wrappers over staff_app/paper.py + the photo shrinking
// done on the phone before upload (long side 2000 px, JPEG): a 4 MB camera
// photo becomes ~0.5 MB, so 10 pages upload on shop Wi-Fi.
import { apiCall } from "./session.js"

const M = "trustbit_school_book_seller.staff_app.paper."

async function call(name, args, opts) {
  const { message } = await apiCall(M + name, args, opts)
  return message
}

export const uploadPaper = (purpose, files, clientRef, copies) =>
  call("upload_paper", { purpose, files, client_ref: clientRef, copies: copies || null }, { timeoutMs: 120000 })
// light = the 2-second poll while the AI reads: since/run = the live lines this phone already has
export const getPaper = (name, light = 0, since = 0, run = null) =>
  call("get_paper", light ? { name, light, since, run } : { name, light })
export const setParty = (name, party, version) => call("set_party", { name, party, version })
export const updateLines = (name, changes, version, copies) =>
  call("update_lines", { name, changes, version, ...(copies === undefined ? {} : { copies }) })
export const searchParties = (purpose, txt) => call("search_parties", { purpose, txt })
export const searchPaperItems = (txt) => call("search_items", { txt })
export const searchSchools = (txt) => call("search_schools", { txt })
export const rereadPaper = (name, model) => call("reread", { name, model })
export const discardPaper = (name) => call("discard_paper", { name })
export const myPapers = (scope = "mine", days = 30) => call("my_papers", { scope, days })
// Saving inserts the order, attaches the pages and learns the names — give it time.
export const saveOrder = (args) => call("save_order", args, { timeoutMs: 120000 })

export const aliasParties = (partyType, txt) => call("alias_parties", { party_type: partyType, txt })
export const listAliases = (partyType, party, txt, start = 0) => call("list_aliases", { party_type: partyType, party, txt, start })
export const changeAlias = (name, itemCode) => call("change_alias", { name, item_code: itemCode })
export const deleteAlias = (name) => call("delete_alias", { name })

// Receipts and Bills
export const setLinks = (name, mode, docs, version) => call("set_links", { name, mode, docs: docs || [], version })
export const previewPurchase = (args) => call("preview_purchase", args, { timeoutMs: 60000 })
export const makeBill = (name) => call("make_bill", { name }, { timeoutMs: 60000 })
export const getItemFacts = (name, itemCodes) => call("get_item_facts", { name, item_codes: itemCodes })
export const searchReceivers = (txt) => call("search_receivers", { txt })

export const getPaperSettings = () => call("get_paper_settings", {})
export const savePaperSettings = (values) => call("save_paper_settings", { values })

export const PURPOSE = {
  po: { doctype: "Purchase Order", party: "Supplier", partyLower: "supplier", short: "PO", title: "Purchase Order", slug: "purchase-order" },
  so: { doctype: "Sales Order", party: "Customer", partyLower: "customer", short: "SO", title: "Sales Order", slug: "sales-order" },
  pr: { doctype: "Purchase Receipt", party: "Supplier", partyLower: "supplier", short: "PR", title: "Receipt", slug: "purchase-receipt" },
  pi: { doctype: "Purchase Invoice", party: "Supplier", partyLower: "supplier", short: "PI", title: "Bill", slug: "purchase-invoice" },
}
export const purposeKey = (doctype) => Object.keys(PURPOSE).find((k) => PURPOSE[k].doctype === doctype) || "po"

// match % colours: 90+ sure, 60–89 to check, below 60 not found
export const band = (pct) => (pct >= 90 ? "bg-ok-bg text-ok-text" : pct >= 60 ? "bg-warn-bg text-warn-text" : "bg-danger-bg text-danger-text")

// "Last bought" against this line, per stock unit. Only informs: never blocks.
// When the discount is the same and the MRP moved, a dearer rate is the new MRP, not a worse deal.
export function lastCompare(l, last, buy) {
  if (!last || !last.length) return null
  const prev = last[0]
  const cf = Number(l.conversion_factor || 1) || 1
  const rate = Number(buy ? l.buy_rate : l.paper_rate) || 0
  const out = { prev, chips: [], dearer: false, extra: 0 }
  if (!rate) return out
  const mine = rate / cf
  const diff = mine - prev.rate
  const disc = l.discount_percent != null && l.discount_percent !== "" ? Number(l.discount_percent) : null
  const list = l.mrp ? Number(l.mrp) / cf : null
  const sameDisc = disc != null && prev.discount != null && Math.abs(disc - prev.discount) < 0.5
  const mrpMoved = list && prev.list && Math.abs(list - prev.list) > Math.max(0.5, prev.list * 0.005)
  if (Math.abs(diff) <= Math.max(0.01, prev.rate * 0.005)) {
    out.chips.push({ ok: true, text: "Same rate as last time" })
    return out
  }
  if (sameDisc) out.chips.push({ ok: true, text: `Same ${fmtPct(disc)}% off` })
  else if (disc != null && prev.discount != null) out.chips.push({ ok: disc > prev.discount, text: `${fmtPct(disc)}% off, was ${fmtPct(prev.discount)}%` })
  if (mrpMoved) out.chips.push({ info: true, text: `MRP ₹${money0(prev.list)} → ₹${money0(list)}` })
  const qty = Number(l.qty || 0) * cf
  if (diff > 0 && !(sameDisc && mrpMoved)) {
    out.dearer = true
    out.extra = diff * qty
    out.chips.push({ ok: false, text: `+₹${money0(diff)} a copy${qty ? ` · ₹${money0(diff * qty)}` : ""}` })
  } else if (diff < 0) out.chips.push({ ok: true, text: `₹${money0(-diff)} a copy cheaper` })
  return out
}
const fmtPct = (n) => (Math.round(Number(n) * 10) / 10).toString()
export function money0(n) {
  const v = Number(n || 0)
  return v % 1 ? money(v) : v.toLocaleString("en-IN")
}

export function money(n) {
  return Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ── files ───────────────────────────────────────────────────────────────────

const MAX_SIDE = 2000
const QUALITY = 0.85

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => resolve(String(r.result).split(",")[1] || "")
    r.onerror = () => reject(new Error("Could not read the file."))
    r.readAsDataURL(blob)
  })
}

function loadImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => resolve({ img, url })
    img.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error("This photo could not be opened."))
    }
    img.src = url
  })
}

async function shrinkPhoto(file) {
  // <img> applies the camera's rotation (EXIF) itself and decodes HEIC on iPhone
  const { img, url } = await loadImage(file)
  try {
    const w0 = img.naturalWidth
    const h0 = img.naturalHeight
    if (!w0 || !h0) throw new Error("This photo could not be opened.")
    const scale = Math.min(1, MAX_SIDE / Math.max(w0, h0))
    const canvas = document.createElement("canvas")
    canvas.width = Math.round(w0 * scale)
    canvas.height = Math.round(h0 * scale)
    const ctx = canvas.getContext("2d")
    ctx.fillStyle = "#ffffff"
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", QUALITY))
    if (!blob) throw new Error("This photo could not be opened.")
    return blob
  } finally {
    URL.revokeObjectURL(url)
  }
}

// Pages this phone has just sent, so the reading screen shows them without
// downloading them again. Only the last two papers are kept.
const justSent = new Map()
export function rememberSent(name, pages) {
  justSent.set(name, pages.map((p) => ({ kind: p.kind, preview: p.preview, data: p.kind === "pdf" ? p.data : "" })))
  while (justSent.size > 2) {
    const [oldest, old] = justSent.entries().next().value
    old.forEach((p) => p.preview && URL.revokeObjectURL(p.preview))
    justSent.delete(oldest)
  }
}
export const sentPages = (name) => justSent.get(name) || null

// → {kind: "image" | "pdf", name, size, data (base64), preview (object URL or "")}
export async function prepareFile(file) {
  const isPdf = file.type === "application/pdf" || /\.pdf$/i.test(file.name || "")
  if (isPdf) {
    if (file.size > 10 * 1024 * 1024) throw new Error("The PDF is larger than 10 MB.")
    return { kind: "pdf", name: file.name || "paper.pdf", size: file.size, data: await blobToBase64(file), preview: "" }
  }
  if (!/^image\//.test(file.type || "") && !/\.(jpe?g|png|webp|heic|heif)$/i.test(file.name || "")) {
    throw new Error("Only photos and PDF files can be read.")
  }
  const blob = await shrinkPhoto(file)
  return { kind: "image", name: file.name || "photo.jpg", size: blob.size, data: await blobToBase64(blob), preview: URL.createObjectURL(blob) }
}
