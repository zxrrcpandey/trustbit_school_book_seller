import fs from "node:fs"
import { fileURLToPath, URL } from "node:url"

import vue from "@vitejs/plugin-vue"
import { defineConfig } from "vite"

// The app's release number is kept in CHANGELOG.md only (the Python metadata
// still says 1.0.0): the first "## [x.y.z]" heading is the version shown on More.
const changelog = fs.readFileSync(new URL("../CHANGELOG.md", import.meta.url), "utf8")
const VERSION = (changelog.match(/^## \[(\d+\.\d+\.\d+)\]/m) || [])[1] || "dev"

// Built assets are committed under trustbit_school_book_seller/public/staff/
// and served from /assets/trustbit_school_book_seller/staff/ (bench symlinks
// {app}/public into sites/assets/{app}). The shell HTML is moved to
// www/staff.html by scripts/postbuild.mjs, which adds the Jinja/CSRF markers.
// Pattern copied from the Betul exec PWA (trustbit_ethanol, /exec).
export default defineConfig({
  plugins: [vue()],
  define: { __KGS_VERSION__: JSON.stringify(VERSION) },
  base: "/assets/trustbit_school_book_seller/staff/",
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  // pdf.js's worker is an ES module with exports (an iife build cannot hold it);
  // it is emitted as a .js file — nginx serves .mjs without a JavaScript type
  worker: { format: "es" },
  build: {
    outDir: "../trustbit_school_book_seller/public/staff",
    emptyOutDir: true,
    sourcemap: false,
    rollupOptions: {
      input: fileURLToPath(new URL("./index.html", import.meta.url)),
    },
  },
  server: {
    port: 8090,
    proxy: {
      // Dev only — production serves same-origin from the bench.
      "^/(api|assets|files)/.*": { target: "http://site1.local:8001", changeOrigin: true },
    },
  },
})
