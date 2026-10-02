<template>
  <div v-if="visible" class="rounded-xl border border-surface-line bg-brand-soft p-3">
    <div class="flex items-start justify-between gap-2">
      <div class="min-w-0">
        <div class="text-[15px] font-bold">Add KGS Staff to your phone</div>
        <p v-if="mode === 'ios'" class="mt-1 text-[14px] text-ink-muted">
          In Safari tap <b>Share</b>, then <b>Add to Home Screen</b>. The first time you open it from the icon it
          asks you to sign in once more — that is normal.
        </p>
        <p v-else class="mt-1 text-[14px] text-ink-muted">
          Install it for one-tap access from your home screen. You may need to sign in once more from the icon.
        </p>
      </div>
      <button type="button" class="flex h-11 w-11 flex-none items-center justify-center rounded-full text-xl text-ink-faint" aria-label="Dismiss" @click="dismiss">×</button>
    </div>
    <button v-if="mode === 'android'" type="button" class="mt-2 min-h-secondary w-full rounded-lg bg-brand-deep font-bold text-white" @click="install">
      Install app
    </button>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from "vue"

const DISMISS_KEY = "kgs-staff-install-dismissed"
const visible = ref(false)
const mode = ref("")
let deferredPrompt = null

const isStandalone = () => window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true
function dismissed() {
  try {
    return !!localStorage.getItem(DISMISS_KEY)
  } catch {
    return false
  }
}

function onBeforeInstall(e) {
  e.preventDefault() // show our own button; Chrome's mini-infobar is easy to miss
  deferredPrompt = e
  if (!dismissed() && !isStandalone()) {
    mode.value = "android"
    visible.value = true
  }
}

onMounted(() => {
  if (isStandalone() || dismissed()) return
  window.addEventListener("beforeinstallprompt", onBeforeInstall)
  const ua = navigator.userAgent
  if (/iPhone|iPad|iPod/.test(ua) && /Safari/.test(ua) && !/CriOS|FxiOS|EdgiOS/.test(ua)) {
    mode.value = "ios"
    visible.value = true
  }
})
onBeforeUnmount(() => window.removeEventListener("beforeinstallprompt", onBeforeInstall))

async function install() {
  if (!deferredPrompt) return
  deferredPrompt.prompt()
  try {
    await deferredPrompt.userChoice
  } finally {
    deferredPrompt = null
    visible.value = false
  }
}

function dismiss() {
  try {
    localStorage.setItem(DISMISS_KEY, "1")
  } catch {
    /* ignore */
  }
  visible.value = false
}
</script>
