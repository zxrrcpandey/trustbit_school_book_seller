<template>
  <div>
    <AppHeader title="More" />
    <main class="flex flex-col gap-[18px] p-4">
      <div class="flex items-center gap-3.5 rounded-2xl border border-surface-line bg-surface px-4 py-3.5">
        <span class="flex h-12 w-12 flex-none items-center justify-center rounded-full bg-brand-soft text-[20px] font-bold text-brand-deep" aria-hidden="true">{{ initial }}</span>
        <span class="min-w-0">
          <span class="block truncate text-[17px] font-bold">{{ info ? info.full_name : "…" }}</span>
          <span v-if="abilities" class="block text-[13px] text-ink-faint">{{ abilities }}</span>
        </span>
      </div>

      <section v-if="paperLinks.length" aria-labelledby="paper-h">
        <h2 id="paper-h" class="mb-2 ml-1 text-[13px] font-bold text-ink-muted">Order from Paper</h2>
        <div class="rows overflow-hidden rounded-2xl border border-surface-line bg-surface">
          <ListRow v-for="l in paperLinks" :key="l.to" :to="l.to" :icon="l.icon" :title="l.title" :sub="l.sub" />
        </div>
      </section>

      <section v-if="!install.standalone" aria-labelledby="phone-h">
        <h2 id="phone-h" class="mb-2 ml-1 text-[13px] font-bold text-ink-muted">This phone</h2>
        <div class="overflow-hidden rounded-2xl border border-surface-line bg-surface">
          <ListRow icon="download" tone="mute" title="Add to home screen" sub="Opens like an app, no browser bar" :chevron="!how" :aria-expanded="how ? 'true' : 'false'" @click="addToHome" />
          <div v-if="how" class="border-t border-surface-mute px-4 pb-4 pt-3 text-[14px] text-ink-muted">
            <p v-if="install.iosSafari">In Safari tap <b>Share</b> (the square with an arrow), then <b>Add to Home Screen</b>.</p>
            <p v-else-if="install.ios">Open <b>splashbox.in/staff</b> in <b>Safari</b>, tap <b>Share</b>, then <b>Add to Home Screen</b>.</p>
            <p v-else>Open the browser menu (<b>⋮</b> at the top right) and tap <b>Add to Home screen</b> or <b>Install app</b>.</p>
            <p class="mt-2">The first time you open it from the icon it may ask you to sign in once more — that is normal.</p>
          </div>
        </div>
      </section>

      <button
        type="button"
        class="flex min-h-[52px] items-center justify-center gap-2.5 rounded-[14px] border border-surface-line bg-surface text-[15px] font-bold text-danger-text"
        @click="logout"
      >
        <Icon name="logout" :size="20" />
        Sign out
      </button>

      <div class="flex flex-col items-center gap-1.5 pt-2">
        <BrandFooter />
        <p class="text-center text-[13px] text-ink-faint">KGS Staff · version {{ version }}</p>
      </div>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"

import AppHeader from "@/components/AppHeader.vue"
import BrandFooter from "@/components/BrandFooter.vue"
import Icon from "@/components/Icon.vue"
import ListRow from "@/components/ListRow.vue"
import { boot } from "@/data/api.js"
import { install, promptInstall } from "@/data/install.js"
import { logout } from "@/data/session.js"

/* global __KGS_VERSION__ */
const version = __KGS_VERSION__ // first heading of CHANGELOG.md, set at build time
const info = ref(null)
const how = ref(false)

const initial = computed(() => (String(info.value?.full_name || "").trim()[0] || "?").toUpperCase())
// what this person can do here, in the words the shop uses
const abilities = computed(() => {
  const i = info.value
  if (!i) return ""
  const p = i.paper || {}
  return [i.shop_owner && "Shop Owner", (p.po || p.pr || p.pi) && "Purchase", p.so && "Sales", i.can_transfer && "Stock"].filter(Boolean).join(" · ")
})
const paperLinks = computed(() => {
  const p = info.value?.paper || {}
  const out = []
  if (p.names) out.push({ to: "/names", icon: "tag", title: "Remembered names", sub: "Names on papers the app has learned" })
  if (p.settings) out.push({ to: "/settings", icon: "settings", title: "Settings", sub: "AI model, who makes Receipts and Bills" })
  return out
})

async function addToHome() {
  // Chrome / Edge on Android: the browser's own install dialog, in one tap
  if (install.available && (await promptInstall())) return
  how.value = !how.value
}

onMounted(async () => {
  try {
    info.value = await boot()
  } catch {
    /* sign out and the version still work */
  }
})
</script>
