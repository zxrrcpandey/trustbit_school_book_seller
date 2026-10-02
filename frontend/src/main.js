import { createApp } from "vue"

import App from "./App.vue"
import "./index.css"
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

createApp(App).use(router).mount("#app")
