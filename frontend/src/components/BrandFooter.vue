<template>
  <div class="flex items-center justify-center gap-2 text-[12px] font-semibold text-ink-faint">
    <span>Powered by</span>
    <!-- 150×50 source: 24 px tall stays sharp on a 2× phone screen -->
    <img :src="logo" alt="Trustbit" width="72" height="24" class="h-6 w-auto" />
  </div>
</template>

<script setup>
// Same file the loading screen in index.html shows (copied from frontend/icons by postbuild)
const logo = "/assets/trustbit_school_book_seller/staff/icons/trustbit-logo.png"
</script>
