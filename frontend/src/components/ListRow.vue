<template>
  <component :is="tag" v-bind="linkAttrs" class="flex min-h-[58px] w-full items-center gap-3 px-4 py-2 text-left text-ink">
    <span v-if="icon" class="flex h-9 w-9 flex-none items-center justify-center rounded-[10px]" :class="TONES[tone] || TONES.brand">
      <Icon :name="icon" :size="iconSize" />
    </span>
    <span class="min-w-0 flex-1">
      <span class="block truncate text-[15px] font-semibold">{{ title }}</span>
      <span v-if="sub" class="block truncate text-[13px] text-ink-faint">{{ sub }}</span>
    </span>
    <slot name="right">
      <Icon v-if="chevron" name="chevron" :size="18" class="flex-none text-ink-faint" />
    </slot>
  </component>
</template>

<script setup>
// One row of a card list (Waiting for you, Recent, More). A router link with
// `to`, a page outside the app (the ERP) with `href`, else a button.
import { computed } from "vue"
import { RouterLink } from "vue-router"

import Icon from "./Icon.vue"

const props = defineProps({
  to: { type: String, default: "" },
  href: { type: String, default: "" },
  icon: { type: String, default: "" },
  iconSize: { type: Number, default: 20 },
  tone: { type: String, default: "brand" },
  title: { type: String, required: true },
  sub: { type: String, default: "" },
  chevron: { type: Boolean, default: true },
})

const TONES = {
  brand: "bg-brand-soft text-brand-deep",
  warn: "bg-warn-bg text-warn-text",
  danger: "bg-danger-bg text-danger-text",
  mute: "bg-surface-mute text-ink-muted",
}
const tag = computed(() => (props.to ? RouterLink : props.href ? "a" : "button"))
const linkAttrs = computed(() => (props.to ? { to: props.to } : props.href ? { href: props.href } : { type: "button" }))
</script>
