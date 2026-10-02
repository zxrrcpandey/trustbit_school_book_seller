import { fileURLToPath, URL } from "node:url"

import vue from "@vitejs/plugin-vue"
import { defineConfig } from "vite"

// Built assets are committed under trustbit_school_book_seller/public/staff/
// and served from /assets/trustbit_school_book_seller/staff/ (bench symlinks
// {app}/public into sites/assets/{app}). The shell HTML is moved to
// www/staff.html by scripts/postbuild.mjs, which adds the Jinja/CSRF markers.
// Pattern copied from the Betul exec PWA (trustbit_ethanol, /exec).
export default defineConfig({
  plugins: [vue()],
  base: "/assets/trustbit_school_book_seller/staff/",
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
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
