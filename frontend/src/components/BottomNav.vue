<template>
  <nav aria-label="Main" class="safe-nav fixed inset-x-0 bottom-0 z-30 mx-auto w-full max-w-lg border-t border-surface-line bg-surface">
    <div class="grid h-[68px] px-2 pb-2 pt-1.5" :style="{ gridTemplateColumns: `repeat(${tabs.length}, minmax(0, 1fr))` }">
      <router-link
        v-for="t in tabs"
        :key="t.tab"
        :to="t.to"
        :aria-current="current === t.tab ? 'page' : undefined"
        class="flex flex-col items-center justify-center gap-[3px] text-[12px]"
        :class="current === t.tab ? 'font-bold text-brand-deep' : 'font-semibold text-ink-muted'"
      >
        <span class="relative flex h-[30px] w-14 items-center justify-center rounded-full" :class="current === t.tab ? 'bg-brand-soft' : ''">
          <Icon :name="t.icon" :size="22" />
          <span
            v-if="t.badge"
            class="absolute -top-0.5 left-8 h-[18px] min-w-[18px] rounded-full bg-danger-text px-[5px] text-center text-[11px] font-bold leading-[18px] text-white"
            aria-hidden="true"
          >
            {{ t.badge > 9 ? "9+" : t.badge }}
          </span>
        </span>
        <span class="tab-label">{{ t.label }}<span v-if="t.badge" class="sr-only">, {{ t.badge }} waiting</span></span>
      </router-link>
    </div>
  </nav>
</template>

<script setup>
// Shown on the four top screens only (route meta.tab) — never while scanning
// or checking a paper, where the bottom of the screen holds that screen's buttons.
import { computed, onMounted, ref, watch } from "vue"
import { useRoute } from "vue-router"

import Icon from "./Icon.vue"
import { boot } from "@/data/api.js"
import { loadMyPapers, paperBadge } from "@/data/home.js"

const route = useRoute()
const info = ref(null)
const current = computed(() => route.meta.tab)

const paperUser = computed(() => {
  const p = info.value?.paper || {}
  return !!(p.po || p.so || p.pr || p.pi)
})
const tabs = computed(() => {
  const out = [{ tab: "home", to: "/home", icon: "home", label: "Home" }]
  if (paperUser.value) out.push({ tab: "papers", to: "/papers", icon: "file", label: "Papers", badge: paperBadge.value })
  if (info.value?.can_transfer) out.push({ tab: "transfers", to: "/transfers", icon: "transfer", label: "Transfers" })
  out.push({ tab: "more", to: "/more", icon: "menu", label: "More" })
  return out
})

function refreshBadge() {
  // a minute-old count is fine for a badge; Home asks for a fresh one itself
  if (paperUser.value) loadMyPapers(60000).catch(() => {})
}

onMounted(async () => {
  try {
    info.value = await boot()
  } catch {
    return // Home + More still work
  }
  refreshBadge()
})
watch(() => route.fullPath, refreshBadge)
</script>
