// Numbers as the shop reads them: no decimals when whole, Indian grouping.
export function fmt(n) {
  const v = Number(n || 0)
  return v.toLocaleString("en-IN", { maximumFractionDigits: 3 })
}

export function fmtDate(d) {
  if (!d) return ""
  const [y, m, day] = String(d).slice(0, 10).split("-")
  return `${day}-${m}-${y}`
}

export function shortWarehouse(name) {
  // "SBGD - KGS" → "SBGD"; keeps company suffix off small screens
  return String(name || "").replace(/ - (KGS|SB)$/, "")
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`

// "today 16:05", "yesterday 18:22", "18 Oct", "18 Oct 2025" — for lists.
// Frappe times are the shop's local time (IST), and so is the phone.
export function fmtWhen(dt) {
  if (!dt) return ""
  const s = String(dt)
  const day = s.slice(0, 10)
  const time = s.slice(11, 16)
  const now = new Date()
  if (day === ymd(now)) return time ? `today ${time}` : "today"
  if (day === ymd(new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1))) return time ? `yesterday ${time}` : "yesterday"
  const [y, m, d] = day.split("-")
  return `${Number(d)} ${MONTHS[Number(m) - 1] || m}` + (Number(y) !== now.getFullYear() ? ` ${y}` : "")
}

// "5:56:06.39" (a Frappe time before 10:00 has no leading zero) → "05:56"
export function hhmm(t) {
  const [h, m] = String(t || "").split(":")
  return h && m ? `${h.padStart(2, "0")}:${m.slice(0, 2)}` : ""
}
