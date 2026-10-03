// Option B (owner, 2026-10-03): the transfer moves only what the system has in From;
// the extra the person counted is added in the To warehouse by a Stock Reconciliation.
// Mirrors staff_app/api.py _create_transfer_with_recos — keep the two in step.
import { fmt } from "./format.js"

export function money(n) {
  return Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// info: reco_preview row · needed: stock qty the transfer asks for · model: {counted, rate, reason, note}
export function recoCalc(info, needed, model, whole, from, to) {
  const out = { notes: [], warnings: [], error: "", reconciles: false, movable: 0, extra: 0, effect: 0, moveTotal: 0 }
  if (!info || !model) return { ...out, error: "Loading…" }
  const counted = model.counted === "" ? NaN : Number(model.counted)
  const q0 = info.current_qty
  const movable = Math.max(q0, 0)
  out.movable = movable
  if (q0 < 0) out.warnings.push(`⚠ ${from} stock is in minus (${fmt(q0)}). The app will not fix this — tell the office.`)
  if (!(counted >= 0)) return { ...out, error: "Enter the count." }
  if (whole && !Number.isInteger(counted)) return { ...out, error: `${info.stock_uom} must be a whole number.` }

  const extra = Math.min(counted, needed) - movable
  if (extra <= 1e-9) {
    out.moveTotal = counted
    if (counted < movable)
      out.notes.push(`Only ${fmt(counted)} ${info.stock_uom} will move. The system will still show ${fmt(movable - counted)} more in ${from} — tell the office.`)
    else out.notes.push(`Your count is the same as the system stock. ${fmt(counted)} ${info.stock_uom} will move. Nothing is added.`)
    return out
  }
  out.reconciles = true
  out.extra = extra
  out.moveTotal = movable + extra
  out.notes.push(`${fmt(movable)} ${info.stock_uom} will move by transfer, and ${fmt(extra)} ${info.stock_uom} will be added in ${to}.`)
  if (counted < needed) out.notes.push(`You counted less than you are moving. Only ${fmt(counted)} ${info.stock_uom} will move in total.`)
  if (counted > needed) out.notes.push(`The other ${fmt(counted - needed)} ${info.stock_uom} stay in ${from}. The system will not show them — tell the office.`)

  // destination after the transfer, then + extra (value of moved units ≈ From's rate)
  const destQ = info.dest_qty + movable
  const destV = info.dest_value + movable * (info.valuation_rate || 0)
  const destAfter = destQ + extra
  const rate = Number(model.rate || 0)
  out.effect = destQ > 0 && destV > 0 ? extra * rate : destAfter * rate - destV
  if (destAfter <= 1e-9) return { ...out, error: `${to} stock is in minus (${fmt(info.dest_qty)}). Adding ${fmt(extra)} is not enough — ask the office.` }
  if (info.dest_qty < 0) out.warnings.push(`⚠ ${to} stock is in minus (${fmt(info.dest_qty)}). Stock value will change by about ₹${money(out.effect)}.`)
  if (!(rate > 0)) return { ...out, error: "Enter a price above zero." }
  if (!model.reason) return { ...out, error: "Choose a reason." }
  if (model.reason === "Other" && !String(model.note || "").trim()) return { ...out, error: "Write what happened." }
  return out
}
