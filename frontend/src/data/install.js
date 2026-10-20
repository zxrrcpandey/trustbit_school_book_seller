// "Add to home screen" (More tab). Chrome fires beforeinstallprompt once, early,
// on any page of the app, so it is caught here at start-up, not by a screen.
// Its own install bar is left alone (no preventDefault): staff still see it.
import { reactive } from "vue"

const standalone = () => window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true
const ua = navigator.userAgent

export const install = reactive({
  standalone: standalone(),
  available: false, // Chrome / Edge on Android: one tap opens the browser's install dialog
  ios: /iPhone|iPad|iPod/.test(ua),
  iosSafari: /iPhone|iPad|iPod/.test(ua) && /Safari/.test(ua) && !/CriOS|FxiOS|EdgiOS/.test(ua),
})

let deferred = null
window.addEventListener("beforeinstallprompt", (e) => {
  deferred = e
  install.available = true
})
window.addEventListener("appinstalled", () => {
  deferred = null
  install.available = false
})

export async function promptInstall() {
  if (!deferred) return false
  const e = deferred
  deferred = null
  install.available = false
  e.prompt()
  try {
    return (await e.userChoice).outcome === "accepted"
  } catch {
    return false
  }
}
