// Thin wrappers over staff_app/api.py — one place that knows the method paths.
import { apiCall } from "./session.js"

const M = "trustbit_school_book_seller.staff_app.api."

async function call(name, args, opts) {
  const { message } = await apiCall(M + name, args, opts)
  return message
}

let bootCache = null
export async function boot(force = false) {
  if (!bootCache || force) bootCache = await call("boot", {})
  return bootCache
}

export const lookupItem = (code, from, to) => call("lookup_item", { code, from_warehouse: from, to_warehouse: to })
export const getItem = (itemCode, from, to) => call("get_item", { item_code: itemCode, from_warehouse: from, to_warehouse: to })
export const searchItems = (txt, from) => call("search_items", { txt, from_warehouse: from })
export const stockLevels = (codes, from, to) => call("stock_levels", { item_codes: codes, from_warehouse: from, to_warehouse: to })
// Submitting can take a while on the shop's 1-CPU server with many lines.
export const createTransfer = (args) => call("create_transfer", args, { timeoutMs: 90000 })
export const myTransfers = (scope = "mine", days = 30) => call("my_transfers", { scope, days })
export const getTransfer = (name) => call("get_transfer", { name })
