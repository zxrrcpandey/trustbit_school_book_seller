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
