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

export const getPaperSettings = () => call("get_paper_settings", {})
export const savePaperSettings = (values) => call("save_paper_settings", { values })

export const PURPOSE = {
  po: { doctype: "Purchase Order", party: "Supplier", partyLower: "supplier", short: "PO" },
  so: { doctype: "Sales Order", party: "Customer", partyLower: "customer", short: "SO" },
}
export const purposeKey = (doctype) => (doctype === "Sales Order" ? "so" : "po")

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
