// Post-build: move the Vite shell to www/staff.html with the Jinja/CSRF
// markers, stamp + place the service worker and manifest, copy icons and the
// barcode WASM, and enforce the build-time safety checks.
// Ported from the Betul exec PWA (trustbit_ethanol frontend/scripts/postbuild.mjs).
import { createHash } from "node:crypto"
import fs from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"

const here = path.dirname(fileURLToPath(import.meta.url))
const FRONTEND = path.resolve(here, "..")
const APP_ROOT = path.resolve(FRONTEND, "..") // apps/trustbit_school_book_seller
const MODULE = path.join(APP_ROOT, "trustbit_school_book_seller")
const OUT = path.join(MODULE, "public", "staff")
const WWW = path.join(MODULE, "www")
const WWW_STAFF = path.join(WWW, "staff")

function fail(msg) {
  console.error(`\npostbuild FAILED: ${msg}\n`)
  process.exit(1)
}

// 1. No package.json at the app root, ever: frappe's bench build runs
//    `yarn build` in any app root that has one and aborts on failure.
if (fs.existsSync(path.join(APP_ROOT, "package.json"))) {
  fail("package.json exists at the APP ROOT — it would abort bench build on production. Keep it in frontend/.")
}

// 2. No v-html anywhere (item names and remarks are free text).
const srcDir = path.join(FRONTEND, "src")
const sourceFiles = []
;(function scan(dir) {
  for (const f of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, f.name)
    if (f.isDirectory()) scan(p)
    else if (/\.(vue|js)$/.test(f.name)) sourceFiles.push(p)
  }
})(srcDir)
const vhtml = sourceFiles.filter((p) => fs.readFileSync(p, "utf8").includes("v-html"))
if (vhtml.length) fail(`v-html found in: ${vhtml.join(", ")}`)

// 3. No Tailwind opacity modifier on a var() token colour — compiles to nothing.
{
  const re = /(?:bg|text|border|ring)-(?:brand|ink|surface|ok|warn|danger)(?:-[a-z]+)?\/\d+/g
  const bad = []
  for (const p of sourceFiles) {
    for (const m of fs.readFileSync(p, "utf8").matchAll(re)) bad.push(`${path.relative(FRONTEND, p)}: ${m[0]}`)
  }
  if (bad.length) fail(`Tailwind opacity modifier over a var() colour:\n  ${bad.join("\n  ")}`)
}

// Built shell + main bundle
const builtIndex = path.join(OUT, "index.html")
if (!fs.existsSync(builtIndex)) fail("built index.html not found — did vite build run?")
const assetsDir = path.join(OUT, "assets")
const bundle = fs.readdirSync(assetsDir).find((f) => /^index-.+\.js$/.test(f))
if (!bundle) fail("hashed index-*.js bundle not found")
const swVersion = createHash("sha256")
  .update(fs.readFileSync(path.join(assetsDir, bundle)))
  .digest("hex")
  .slice(0, 12)

// Shell → www/staff.html (GENERATED — never hand-edit it)
let html = fs.readFileSync(builtIndex, "utf8")
if (!html.includes("<!-- staff:jinja-head -->")) fail("staff:jinja-head marker missing from built index.html")
html = html.replace(
  "<!-- staff:jinja-head -->",
  [
    // The injected csrf snippet assigns frappe.csrf_token; this standalone page
    // has no global frappe object of its own.
    "<script>window.frappe = window.frappe || {};</script>",
    "<!-- csrf_token -->",
    "<script>window.staffEnv = { enabled: {{ staff_enabled }}, sw: {{ staff_sw }}, allowed: {{ staff_allowed }}, user: {{ staff_user }} };</script>",
    // no <!-- no-cache --> marker: deprecated in v15; www/staff.py sets no_cache = 1
  ].join("\n    ")
)
for (const v of ["staff_enabled", "staff_sw", "staff_allowed", "staff_user"]) {
  if (!html.includes(`{{ ${v} }}`)) fail(`placeholder {{ ${v} }} missing from staff.html`)
}
// frappe safe_render rejects a template containing ".__" (dunder guard).
if (html.includes(".__")) fail('".__" found in staff.html — frappe safe_render would refuse it')
fs.writeFileSync(path.join(WWW, "staff.html"), html)
fs.rmSync(builtIndex) // never ship the raw shell under /assets

// Service worker → www/staff/sw.min.js (".min.js" so frappe serves it raw,
// not through Jinja; under /staff/ so its scope is /staff/ and never /app)
fs.mkdirSync(WWW_STAFF, { recursive: true })
const sw = fs.readFileSync(path.join(srcDir, "sw.js"), "utf8").replace("__SW_VERSION__", swVersion)
if (sw.includes("__SW_VERSION__")) fail("SW version stamp failed")
if (!/pathname\.startsWith\("\/api\/"\)\) return/.test(sw)) fail("service worker /api early-return guard missing")
fs.writeFileSync(path.join(WWW_STAFF, "sw.min.js"), sw)

// Manifest → www/staff/ (NOT /assets: that path is cached ~1 year)
fs.copyFileSync(path.join(FRONTEND, "manifest.webmanifest"), path.join(WWW_STAFF, "manifest.webmanifest"))

// Icons (emptyOutDir wipes them every build)
const iconDst = path.join(OUT, "icons")
fs.mkdirSync(iconDst, { recursive: true })
for (const f of fs.readdirSync(path.join(FRONTEND, "icons"))) {
  fs.copyFileSync(path.join(FRONTEND, "icons", f), path.join(iconDst, f))
}
for (const f of ["icon-192.png", "icon-512.png", "icon-512-maskable.png", "apple-touch-icon-180.png", "favicon-32.png"]) {
  if (!fs.existsSync(path.join(iconDst, f))) fail(`required icon missing: ${f}`)
}

// Barcode decoder WASM for iPhone (no native BarcodeDetector), self-hosted so
// the phone never fetches code from a CDN. The folder carries the zxing-wasm
// version because /assets is cached ~1 year. src/data/scanner.js must point
// at the same folder.
const zxingPkg = JSON.parse(fs.readFileSync(path.join(FRONTEND, "node_modules", "zxing-wasm", "package.json"), "utf8"))
const wasmDir = path.join(OUT, `zxing-${zxingPkg.version}`)
fs.mkdirSync(wasmDir, { recursive: true })
fs.copyFileSync(
  path.join(FRONTEND, "node_modules", "zxing-wasm", "dist", "reader", "zxing_reader.wasm"),
  path.join(wasmDir, "zxing_reader.wasm")
)
const allJs = fs.readdirSync(assetsDir).filter((f) => f.endsWith(".js"))
if (!allJs.some((f) => fs.readFileSync(path.join(assetsDir, f), "utf8").includes(`zxing-${zxingPkg.version}/`))) {
  fail(`no bundle references zxing-${zxingPkg.version}/ — update ZXING_DIR in src/data/scanner.js`)
}

// 4. No credentials or resource-API writes in the shipped JS
for (const f of allJs) {
  const text = fs.readFileSync(path.join(assetsDir, f), "utf8")
  for (const needle of ["api_key", "api_secret", "Authorization: token", "/api/resource"]) {
    if (text.includes(needle)) fail(`forbidden string in shipped bundle ${f}: ${needle}`)
  }
}

console.log(`postbuild OK — sw ${swVersion}, bundle ${bundle}, zxing ${zxingPkg.version}`)
