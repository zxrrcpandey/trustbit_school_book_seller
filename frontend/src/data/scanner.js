// Barcode detection. Android Chrome has a native BarcodeDetector; iPhone
// Safari does not, so the barcode-detector polyfill (ZXing compiled to WASM)
// is loaded on demand. Its WASM is self-hosted under /assets — by default the
// polyfill would download it from a CDN. ZXING_DIR must match the folder
// scripts/postbuild.mjs creates (it fails the build if they differ).
const ZXING_DIR = "/assets/trustbit_school_book_seller/staff/zxing-1.3.4/"
const FORMATS = ["ean_13", "ean_8", "upc_a", "upc_e", "code_128", "code_39", "itf", "qr_code"]

let detectorPromise = null

async function nativeDetector() {
  if (!("BarcodeDetector" in window)) return null
  try {
    const supported = await window.BarcodeDetector.getSupportedFormats()
    const formats = FORMATS.filter((f) => supported.includes(f))
    if (!formats.includes("ean_13")) return null
    return new window.BarcodeDetector({ formats })
  } catch {
    return null
  }
}

async function polyfillDetector() {
  const mod = await import("barcode-detector/pure")
  mod.setZXingModuleOverrides({
    locateFile: (path, prefix) => (path.endsWith(".wasm") ? ZXING_DIR + path : prefix + path),
  })
  return new mod.BarcodeDetector({ formats: FORMATS })
}

export function getDetector() {
  if (!detectorPromise) {
    detectorPromise = (async () => (await nativeDetector()) || (await polyfillDetector()))()
    detectorPromise.catch(() => {
      detectorPromise = null
    })
  }
  return detectorPromise
}
