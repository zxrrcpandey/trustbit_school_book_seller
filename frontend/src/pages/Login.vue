<template>
  <div class="flex min-h-dvh flex-col px-6">
    <div class="pb-6 pt-16 text-center">
      <img :src="icon" alt="" class="mx-auto mb-3 h-16 w-16 rounded-2xl" />
      <div class="text-[18px] font-bold">Khandelwal General Stores</div>
      <div class="text-[14px] text-ink-muted">KGS Staff · warehouse transfers</div>
    </div>

    <div v-if="resetLink" class="rounded-xl border border-surface-line bg-surface p-4">
      <div class="font-bold">Your password must be changed first</div>
      <p class="mb-3 mt-1 text-[14px] text-ink-muted">Set a new password, then sign in again.</p>
      <a :href="resetLink" class="block min-h-action w-full rounded-xl bg-brand-deep py-4 text-center font-bold text-white">Set a new password</a>
    </div>

    <form v-else-if="tmpId" class="flex flex-col gap-3" @submit.prevent="submitOtp">
      <p class="text-[15px] text-ink-muted">Enter the 6-digit code from your authenticator app.</p>
      <input
        v-model="otp"
        inputmode="numeric"
        autocomplete="one-time-code"
        maxlength="6"
        class="w-full rounded-lg border border-surface-line bg-surface p-3 text-center text-[22px] tracking-[0.4em]"
        aria-label="One-time code"
      />
      <p v-if="error" class="font-semibold text-danger-text">{{ error }}</p>
      <button type="submit" class="min-h-action w-full rounded-xl bg-brand-deep font-bold text-white disabled:opacity-40" :disabled="working || otp.trim().length < 6">
        {{ working ? "Checking…" : "Verify code" }}
      </button>
    </form>

    <form v-else class="flex flex-col gap-3" @submit.prevent="submit">
      <input v-model="usr" type="email" autocomplete="username" autocapitalize="off" placeholder="Email" class="w-full rounded-lg border border-surface-line bg-surface p-3" aria-label="Email" />
      <input v-model="pwd" type="password" autocomplete="current-password" placeholder="Password" class="w-full rounded-lg border border-surface-line bg-surface p-3" aria-label="Password" />
      <p v-if="error" class="font-semibold text-danger-text">{{ error }}</p>
      <button type="submit" class="min-h-action w-full rounded-xl bg-brand-deep font-bold text-white disabled:opacity-40" :disabled="working || !usr.trim() || !pwd">
        {{ working ? "Signing you in…" : "Sign in" }}
      </button>
      <p class="text-center text-[14px] text-ink-faint">Same email, password and code as the ERP.</p>
    </form>
  </div>
</template>

<script setup>
import { ref } from "vue"

import { login, loginOtp } from "@/data/session.js"

const icon = "/assets/trustbit_school_book_seller/staff/icons/icon-192.png"
const usr = ref("")
const pwd = ref("")
const otp = ref("")
const tmpId = ref("")
const resetLink = ref("")
const error = ref("")
const working = ref(false)

// Success is a FULL reload on purpose: the Guest-loaded shell holds the Guest
// CSRF token; the reload brings the signed-in token and staffEnv.
const finish = () => window.location.replace("/staff/home")

async function submit() {
  error.value = ""
  working.value = true
  try {
    const r = await login(usr.value.trim(), pwd.value)
    if (r.kind === "2fa") {
      tmpId.value = r.tmpId
      working.value = false
    } else if (r.kind === "reset_required") {
      resetLink.value = r.redirectTo
      working.value = false
    } else finish()
  } catch (e) {
    error.value = e.status === 401 ? "Wrong email or password." : e.display()
    working.value = false
  }
}

async function submitOtp() {
  error.value = ""
  working.value = true
  try {
    await loginOtp(tmpId.value, otp.value.trim())
    finish()
  } catch (e) {
    error.value = e.status === 401 ? "That code didn't work. Wait for the next one and try again." : e.display()
    working.value = false
  }
}
</script>
