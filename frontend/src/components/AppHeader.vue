<template>
  <header class="safe-top sticky top-0 z-30 border-b border-surface-line bg-surface">
    <div class="flex min-h-[56px] items-center gap-1 px-2">
      <button v-if="back" type="button" class="flex h-11 w-11 items-center justify-center rounded-full text-2xl" aria-label="Back" @click="goBack">‹</button>
      <div
        v-else-if="logo"
        class="ml-2 mr-1.5 flex h-8 w-8 flex-none items-center justify-center rounded-[9px] bg-brand-deep text-[10px] font-extrabold tracking-[0.02em] text-white"
        aria-hidden="true"
      >
        KGS
      </div>
      <div v-else class="w-2" />
      <h1 class="min-w-0 flex-1 truncate text-[18px] font-bold">{{ title }}</h1>
      <slot name="right" />
    </div>
  </header>
</template>

<script setup>
import { useRouter } from "vue-router"

const props = defineProps({
  title: { type: String, default: "" },
  back: { type: [String, Boolean], default: false },
  logo: { type: Boolean, default: false }, // the KGS mark, on Home only
})
const router = useRouter()
function goBack() {
  if (typeof props.back === "string") router.push(props.back)
  else if (window.history.length > 1) router.back()
  else router.push("/home")
}
</script>
