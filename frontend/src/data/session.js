// Session + the ONE network chokepoint (adapted from the Betul exec PWA).
// Hand-rolled fetch: the double-encoded _server_messages envelope must show
// real text, and login has its own 2FA / password-reset branches.

import { reactive } from "vue"

import { FrappeError, errorFromResponse, parseServerMessages } from "./errors.js"

export const session = reactive({
  user: null, // null = unknown, "Guest" = signed out, else email
  booted: false,
})

function csrfToken() {
  return (window.frappe && window.frappe.csrf_token) || ""
}

// Every call POSTs to /api/method/<dotted.path> (the staff endpoints are POST-only).
export async function apiCall(method, args = {}, { timeoutMs = 25000 } = {}) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  let res
  try {
    res = await fetch(`/api/method/${method}`, {
      method: "POST",
      credentials: "same-origin",
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-Frappe-CSRF-Token": csrfToken(),
      },
      body: JSON.stringify(args),
    })
  } catch (e) {
    clearTimeout(timer)
    if (e && e.name === "AbortError") {
      throw new FrappeError({ status: 0, excType: "Timeout", messages: [], text: "The server is taking too long." })
    }
    throw new FrappeError({ status: 0, excType: "NetworkError", messages: [], text: "No connection." })
  }
  clearTimeout(timer)

  const rawText = await res.text()
  let body = null
  try {
    body = rawText ? JSON.parse(rawText) : null
  } catch {
    body = null
  }

  if (!res.ok) {
    const err = errorFromResponse(res.status, body || {}, rawText)
    if (err.isPermissionError || res.status === 401) {
      try {
        if ((await whoami()) === "Guest") {
          session.user = "Guest"
          err.sessionExpired = true
        }
      } catch {
        /* keep the original error */
      }
    }
    if (err.isCSRFError) err.needsReload = true
    throw err
  }
  return { message: body ? body.message : null, warnings: parseServerMessages(body && body._server_messages), body }
}

export async function whoami() {
  const res = await fetch("/api/method/frappe.auth.get_logged_user", {
    method: "POST",
    credentials: "same-origin",
    headers: { Accept: "application/json", "Content-Type": "application/json", "X-Frappe-CSRF-Token": csrfToken() },
    body: "{}",
  })
  if (!res.ok) return "Guest"
  const body = await res.json().catch(() => null)
  return (body && body.message) || "Guest"
}

export async function bootSession() {
  // www/staff.py renders the signed-in user into the shell; the network call
  // is only a fallback (e.g. a shell served from the service-worker cache).
  const rendered = (window.staffEnv || {}).user
  if (rendered && !session.booted) {
    session.user = rendered
    session.booted = true
    return session.user
  }
  try {
    session.user = await whoami()
  } catch {
    session.user = "Guest"
  }
  session.booted = true
  return session.user
}

// staff_app: 1 rides on BOTH login calls: the server's on_session_creation
// hook only gives the long staff-app session to logins that carry it
// (staff_app/session_extend.py). Desk logins keep the 1-hour window.
//  success          → {message:"Logged In"}       → full reload
//  2FA              → {verification, tmp_id}       → OTP screen
//  password expired → "Password Reset" + redirect_to → blocking notice
//  bad credentials  → 401                          → inline error
export async function login(usr, pwd) {
  const { body } = await apiCall("login", { usr, pwd, staff_app: 1 })
  const msg = body || {}
  if (msg.verification && msg.tmp_id) return { kind: "2fa", tmpId: msg.tmp_id, verification: msg.verification }
  if (msg.message === "Password Reset" && msg.redirect_to) return { kind: "reset_required", redirectTo: msg.redirect_to }
  return { kind: "ok" }
}

export async function loginOtp(tmpId, otp) {
  await apiCall("login", { tmp_id: tmpId, otp, staff_app: 1 })
  return { kind: "ok" }
}

export async function logout() {
  try {
    await apiCall("logout", {})
  } finally {
    session.user = "Guest"
    window.location.replace("/staff/login")
  }
}
