<template>
  <div class="fixed inset-0 z-50 flex flex-col bg-black text-white">
    <div class="safe-top flex items-center justify-between px-3 py-2">
      <div class="text-[16px] font-semibold">Scan barcodes</div>
      <div class="flex items-center gap-2">
        <button v-if="torchSupported" type="button" class="rounded-full bg-white px-4 py-2 text-[14px] font-bold text-black" @click="toggleTorch">
          {{ torchOn ? "Light off" : "Light on" }}
        </button>
        <button type="button" class="rounded-full bg-white px-5 py-2 text-[15px] font-bold text-black" @click="$emit('close')">Done</button>
      </div>
    </div>

    <div class="relative flex-1 overflow-hidden">
      <video ref="video" class="h-full w-full object-cover" playsinline muted autoplay />
      <div class="pointer-events-none absolute inset-0 flex items-center justify-center">
        <div class="h-40 w-[80%] max-w-sm rounded-2xl border-4 border-white" style="box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.35)" />
      </div>
      <div v-if="message" class="absolute inset-x-0 top-4 flex justify-center px-4">
        <div class="max-w-sm rounded-xl bg-white px-4 py-3 text-center text-[15px] font-semibold text-ink">{{ message }}</div>
      </div>
    </div>

    <div class="safe-bottom min-h-[96px] px-4 pt-3 text-center">
      <div v-if="last" class="rounded-xl px-4 py-3 text-[15px] font-semibold" :class="last.ok ? 'bg-ok-bg text-ok-text' : 'bg-danger-bg text-danger-text'">
        {{ last.text }}
      </div>
      <div v-else class="text-[14px] opacity-80">Point the camera at a barcode. Keep scanning — each scan adds 1.</div>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from "vue"

import { getDetector } from "@/data/scanner.js"

// `last` = {ok, text} from the parent after it handled the previous code.
defineProps({ last: { type: Object, default: null } })
const emit = defineEmits(["code", "close"])

const video = ref(null)
const message = ref("Starting camera…")
const torchSupported = ref(false)
const torchOn = ref(false)
let stream = null
let stopped = false
let timer = null
let busy = false
let lastCode = ""
let lastAt = 0

async function start() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    message.value = "This browser cannot use the camera. Type the code or use Search instead."
    return
  }
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 720 } },
      audio: false,
    })
  } catch (e) {
    message.value =
      e && e.name === "NotAllowedError"
        ? "Camera permission was refused. Allow the camera for this site in your phone's settings."
        : "Could not open the camera."
    return
  }
  if (stopped) return stop()
  video.value.srcObject = stream
  try {
    await video.value.play()
  } catch {
    /* autoplay attribute covers most phones */
  }
  const track = stream.getVideoTracks()[0]
  try {
    torchSupported.value = !!(track.getCapabilities && track.getCapabilities().torch)
  } catch {
    torchSupported.value = false
  }
  let detector
  try {
    message.value = "Loading scanner…"
    detector = await getDetector()
  } catch {
    message.value = "The scanner could not load. Type the code or use Search instead."
    return
  }
  message.value = ""
  timer = setInterval(async () => {
    if (busy || stopped || !video.value || video.value.readyState < 2) return
    busy = true
    try {
      const codes = await detector.detect(video.value)
      const raw = codes && codes[0] && codes[0].rawValue ? String(codes[0].rawValue).trim() : ""
      const now = Date.now()
      // the same code stays in view for a while — count it once per 1.5 s
      if (raw && (raw !== lastCode || now - lastAt > 1500)) {
        lastCode = raw
        lastAt = now
        emit("code", raw)
      }
    } catch {
      /* a frame that could not be read */
    } finally {
      busy = false
    }
  }, 200)
}

async function toggleTorch() {
  try {
    const track = stream && stream.getVideoTracks()[0]
    await track.applyConstraints({ advanced: [{ torch: !torchOn.value }] })
    torchOn.value = !torchOn.value
  } catch {
    torchSupported.value = false
  }
}

function stop() {
  stopped = true
  clearInterval(timer)
  if (stream) stream.getTracks().forEach((t) => t.stop())
  stream = null
}

onMounted(start)
onBeforeUnmount(stop)
</script>
