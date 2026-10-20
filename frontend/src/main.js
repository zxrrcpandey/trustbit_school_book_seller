import { createApp } from "vue"

import App from "./App.vue"
import "./index.css"
// catches Chrome's one-time install offer for More → "Add to home screen"
import "./data/install.js"
import { router } from "./router.js"

// Service worker: scope /staff/ only — it never controls /app (the desk).
// window.staffEnv comes from www/staff.py; site_config kgs_staff_app_sw_off=1
// renders sw=0 and every phone unregisters on its next launch, no deploy.
const env = window.staffEnv || {}
if ("serviceWorker" in navigator && window.location.protocol === "https:") {
  if (Number(env.sw) === 0) {
    navigator.serviceWorker.getRegistrations().then((regs) => regs.forEach((r) => r.unregister()))
  } else if (import.meta.env.PROD) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/staff/sw.min.js").catch(() => {
        /* the app works without a service worker */
      })
    })
  }
}

// Mount once the first screen is decided (sign-in check done), so the loading
// screen in index.html stays up until then instead of flashing an empty page.
// Mounting replaces it. A failed first navigation still mounts, as before.
const app = createApp(App).use(router)
router
  .isReady()
  .catch(() => {})
  .then(() => app.mount("#app"))
