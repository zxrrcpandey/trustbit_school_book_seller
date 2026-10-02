// Beep + vibrate on a scan. AudioContext must be created after a user tap
// (iOS), so it is made lazily on the first scan.
let ctx = null

function tone(freq, ms) {
  try {
    ctx = ctx || new (window.AudioContext || window.webkitAudioContext)()
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.frequency.value = freq
    osc.type = "square"
    gain.gain.value = 0.06
    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.start()
    osc.stop(ctx.currentTime + ms / 1000)
  } catch {
    /* sound is optional */
  }
}

export function okBeep() {
  tone(1450, 90)
  if (navigator.vibrate) navigator.vibrate(40)
}

export function errorBeep() {
  tone(300, 260)
  if (navigator.vibrate) navigator.vibrate([80, 60, 80])
}

// Call from a user tap so iOS lets later beeps play.
export function unlockAudio() {
  try {
    ctx = ctx || new (window.AudioContext || window.webkitAudioContext)()
    if (ctx.state === "suspended") ctx.resume()
  } catch {
    /* ignore */
  }
}
