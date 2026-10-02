<template>
  <div class="mx-auto min-h-dvh w-full max-w-lg">
    <div v-if="disabled" class="flex min-h-dvh flex-col items-center justify-center gap-3 px-8 text-center">
      <div class="text-lg font-semibold">KGS Staff is switched off</div>
      <p class="text-ink-muted">Transfers can still be made in the ERP. Please try again later.</p>
    </div>
    <div v-else-if="notAllowed" class="flex min-h-dvh flex-col items-center justify-center gap-3 px-8 text-center">
      <div class="text-lg font-semibold">This app is for stock staff</div>
      <p class="text-ink-muted">Your account does not have the Stock User role. Ask the office to add it.</p>
      <a href="/app" class="mt-2 flex min-h-secondary w-48 items-center justify-center rounded-xl bg-brand-deep px-4 font-bold text-white">
        Open the ERP
      </a>
      <button type="button" class="min-h-secondary font-semibold text-ink-faint" @click="logout">Sign out</button>
    </div>
    <template v-else>
      <OfflineBanner />
      <router-view />
    </template>
  </div>
</template>

<script setup>
import OfflineBanner from "./components/OfflineBanner.vue"
import { logout } from "./data/session.js"

// From www/staff.py. Presentation only — every endpoint re-checks on the server.
// Missing keys default to "on", so an old cached shell can never lock anyone out.
const env = window.staffEnv || {}
const disabled = Number(env.enabled ?? 1) === 0
const notAllowed = Number(env.allowed ?? 1) === 0
</script>
