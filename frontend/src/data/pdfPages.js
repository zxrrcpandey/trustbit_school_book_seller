// Draws the pages of a PDF as small pictures for the reading screen.
// pdf.js (about 1 MB with its worker) is downloaded only the first time a
// phone shows a PDF; the worker is a separate .js file (nginx serves .mjs
// without a JavaScript type, which a worker refuses).
let lib = null

async function load() {
  if (!lib) {
    const [pdfjs, { default: PdfWorker }] = await Promise.all([
      import("pdfjs-dist/legacy/build/pdf.min.mjs"),
      import("pdfjs-dist/legacy/build/pdf.worker.min.mjs?worker"),
    ])
    pdfjs.GlobalWorkerOptions.workerPort = new PdfWorker()
    lib = pdfjs
  }
  return lib
}

function fromBase64(b64) {
  const bin = atob(b64)
  const out = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i)
  return out
}

// source: { data: base64 } (just sent from this phone) or { url } (the stored copy).
// onPage(index, jpegDataUrl) is called page by page; stopped() ends it early.
export async function drawPdfPages(source, maxPages, width, onPage, stopped) {
  const pdfjs = await load()
  let bytes
  if (source.data) {
    bytes = fromBase64(source.data)
  } else {
    const res = await fetch(source.url, { credentials: "same-origin" })
    if (!res.ok) throw new Error(`PDF ${res.status}`)
    bytes = new Uint8Array(await res.arrayBuffer())
  }
  if (stopped()) return
  const doc = await pdfjs.getDocument({ data: bytes, isEvalSupported: false, enableXfa: false }).promise
  try {
    const n = Math.min(doc.numPages, maxPages)
    for (let i = 1; i <= n && !stopped(); i++) {
      const page = await doc.getPage(i)
      const vp = page.getViewport({ scale: width / page.getViewport({ scale: 1 }).width })
      const canvas = document.createElement("canvas")
      canvas.width = Math.ceil(vp.width)
      canvas.height = Math.ceil(vp.height)
      const ctx = canvas.getContext("2d")
      ctx.fillStyle = "white"
      ctx.fillRect(0, 0, canvas.width, canvas.height)
      await page.render({ canvasContext: ctx, viewport: vp }).promise
      onPage(i - 1, canvas.toDataURL("image/jpeg", 0.82))
      page.cleanup()
    }
  } finally {
    doc.destroy()
  }
}
