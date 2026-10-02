"""HTTP tests for the /staff PWA on http://127.0.0.1:8001 (bench --site site1.local serve).
Temporarily mirrors production auth: session_expiry 01:00, kgs_staff_session_days 7,
2FA (OTP App) for the Stock User role. Everything is restored at the end."""
import json
import re
import subprocess
import time

import pyotp
import requests

import frappe

BASE = "http://127.0.0.1:8001"
PW = "Kgs-Test-2026!x"
RESULTS = []


def check(name, cond, detail=""):
	RESULTS.append((name, bool(cond)))
	print(("PASS " if cond else "FAIL ") + name + (f" — {detail}" if detail and not cond else ""))


frappe.init(site="site1.local", sites_path=".")
frappe.connect()
orig = {
	"session_expiry": frappe.db.get_single_value("System Settings", "session_expiry"),
	"enable_two_factor_auth": frappe.db.get_single_value("System Settings", "enable_two_factor_auth"),
	"two_factor_method": frappe.db.get_single_value("System Settings", "two_factor_method"),
	"role_2fa": frappe.db.get_value("Role", "Stock User", "two_factor_auth"),
	"role_2fa_sales": frappe.db.get_value("Role", "Sales User", "two_factor_auth"),
}


def setcfg(key, value):
	subprocess.run(["bench", "--site", "site1.local", "set-config", key, str(value)], cwd="..", check=True, capture_output=True)


def delcfg(key):
	subprocess.run(["bench", "--site", "site1.local", "set-config", key, "0"], cwd="..", check=True, capture_output=True)


frappe.db.set_single_value("System Settings", {"session_expiry": "01:00", "enable_two_factor_auth": 1, "two_factor_method": "OTP App"})
frappe.db.set_value("Role", "Stock User", "two_factor_auth", 1)
orig["default_expiry"] = frappe.db.get_default("session_expiry")
frappe.db.set_default("session_expiry", "01:00")  # what System Settings.on_update writes
frappe.db.commit()
frappe.clear_cache()
setcfg("kgs_staff_session_days", 7)
# Enrol the test users in the OTP app like production users already are
# (a first-ever OTP-app login e-mails a QR code; this site has no mail account).
from frappe.twofactor import get_otpsecret_for_, set_default as set_2fa_default

for u in ("staff1@example.com", "mgr1@example.com", "nostock@example.com"):
	get_otpsecret_for_(u)
	set_2fa_default(u + "_otplogin", 1)
frappe.db.set_value("Role", "Sales User", "two_factor_auth", 1)
frappe.db.commit()


def sid_max_age(resp):
	for h in resp.raw.headers.getlist("Set-Cookie"):
		if h.startswith("sid="):
			m = re.search(r"Max-Age=(\d+)", h, re.I)
			return int(m.group(1)) if m else None
	return None


def login(email, staff_app=True):
	s = requests.Session()
	extra = {"staff_app": 1} if staff_app else {}
	r = s.post(f"{BASE}/api/method/login", json={"usr": email, "pwd": PW, **extra})
	body = r.json()
	if body.get("verification"):
		tmp = body["tmp_id"]
		secret = get_otpsecret_for_(email)
		otp = pyotp.TOTP(secret).now()
		r = s.post(f"{BASE}/api/method/login", json={"tmp_id": tmp, "otp": otp, **extra})
	return s, r, body


def csrf(s):
	html = s.get(f"{BASE}/staff/").text
	m = re.search(r'frappe\.csrf_token\s*=\s*"([^"]+)"', html)
	return m.group(1) if m else "", html


try:
	# ── static shell ─────────────────────────────────────────────────────────
	g = requests.get(f"{BASE}/staff")
	check("/staff 200 for Guest", g.status_code == 200)
	check("shell has staffEnv rendered", "window.staffEnv = { enabled: 1, sw: 1, allowed: 1, user: \"Guest\" }" in g.text, g.text[:400])
	check("shell has no raw Jinja left", "{{" not in g.text)
	for path in ("/staff/login", "/staff/transfer", "/staff/transfers", "/staff/t/MAT-STE-2026-00007"):
		r = requests.get(BASE + path)
		check(f"{path} serves the shell", r.status_code == 200 and "window.staffEnv" in r.text, r.status_code)
	sw = requests.get(f"{BASE}/staff/sw.min.js")
	check("sw.min.js served raw", sw.status_code == 200 and "staff-shell-" in sw.text and "${SW_VERSION}" in sw.text, sw.status_code)
	check("sw.min.js is javascript", "javascript" in sw.headers.get("Content-Type", ""), sw.headers.get("Content-Type"))
	mf = requests.get(f"{BASE}/staff/manifest.webmanifest")
	check("manifest served", mf.status_code == 200 and json.loads(mf.text)["scope"] == "/staff/", mf.status_code)
	js = re.search(r'src="(/assets/trustbit_school_book_seller/staff/assets/index-[^"]+\.js)"', g.text)
	check("bundle referenced", bool(js))
	check("bundle served", requests.get(BASE + js.group(1)).status_code == 200)
	check("wasm served", requests.get(f"{BASE}/assets/trustbit_school_book_seller/staff/zxing-1.3.4/zxing_reader.wasm").status_code == 200)
	check("icon served", requests.get(f"{BASE}/assets/trustbit_school_book_seller/staff/icons/icon-192.png").status_code == 200)

	# ── staff-app login (2FA) → long session ────────────────────────────────
	s, r, first = login("staff1@example.com", staff_app=True)
	check("2FA step happened", bool(first.get("verification")), first)
	check("login ok after OTP", r.status_code == 200 and r.json().get("message") == "Logged In", r.text[:200])
	check("sid cookie Max-Age = 7 days", sid_max_age(r) == 7 * 86400, sid_max_age(r))
	token, html = csrf(s)
	check("signed-in shell carries a CSRF token", len(token) > 10)
	check("signed-in staff allowed", "allowed: 1" in html)
	b = s.post(f"{BASE}/api/method/trustbit_school_book_seller.staff_app.api.boot", json={}, headers={"X-Frappe-CSRF-Token": token})
	check("boot over HTTP", b.status_code == 200 and b.json()["message"]["user"] == "staff1@example.com", b.text[:200])
	check("API response re-issues 7-day cookie", sid_max_age(b) == 7 * 86400, sid_max_age(b))
	nocsrf = s.post(f"{BASE}/api/method/trustbit_school_book_seller.staff_app.api.boot", json={})
	check("POST without CSRF token refused", nocsrf.status_code in (400, 403), nocsrf.status_code)
	gget = s.get(f"{BASE}/api/method/trustbit_school_book_seller.staff_app.api.my_transfers")
	check("GET on a POST-only endpoint refused", gget.status_code in (403, 405), gget.status_code)
	sid_staff = s.cookies.get("sid")
	frappe.db.commit(); row = frappe.db.sql("select sessiondata from tabSessions where sid=%s", sid_staff)
	check("session row stamped staff_app + 168h", row and "'staff_app': 1" in row[0][0] and "168:00:00" in row[0][0], row)

	# ── desk login (no flag) → normal hour ───────────────────────────────────
	d, r2, _ = login("mgr1@example.com", staff_app=False)
	check("desk login ok", r2.status_code == 200)
	check("desk login keeps 1-hour cookie", sid_max_age(r2) == 3600, sid_max_age(r2))
	sid_desk = d.cookies.get("sid")
	frappe.db.commit(); row = frappe.db.sql("select sessiondata from tabSessions where sid=%s", sid_desk)
	check("desk session NOT stamped", row and "staff_app" not in row[0][0])

	# ── keep-alive job ───────────────────────────────────────────────────────
	frappe.conf["kgs_staff_session_days"] = 7  # this process loaded site_config before setcfg
	old = frappe.utils.add_to_date(frappe.utils.now(), hours=-2, as_string=True)
	frappe.db.commit()
	frappe.db.sql("update tabSessions set lastupdate=%s where sid in (%s, %s)", (old, sid_staff, sid_desk))
	frappe.db.commit()
	from trustbit_school_book_seller.staff_app.session_extend import touch_staff_sessions

	touch_staff_sessions()
	frappe.db.commit()
	lu = dict(frappe.db.sql("select sid, lastupdate from tabSessions where sid in (%s, %s)", (sid_staff, sid_desk)))
	check("touch job slides the staff session", str(lu[sid_staff]) > old, lu)
	check("touch job leaves the desk session", str(lu[sid_desk])[:19] == old[:19], lu)

	# The deploy case: Redis flushed, both rows 2 h old in the DB (global window 1 h).
	for sid in (sid_staff, sid_desk):
		frappe.cache.hdel("session", sid)
		frappe.cache.hdel("last_db_session_update", sid)
	who = s.post(f"{BASE}/api/method/frappe.auth.get_logged_user", json={}, headers={"X-Frappe-CSRF-Token": token})
	check("staff session resumes from DB after cache loss", who.json().get("message") == "staff1@example.com", who.text[:200])
	whod = d.post(f"{BASE}/api/method/frappe.auth.get_logged_user", json={})
	check("idle desk session expires as normal (control)", whod.status_code != 200 or whod.json().get("message") != "mgr1@example.com", whod.text[:200])

	# ── role gate on the shell ───────────────────────────────────────────────
	n, r3, _ = login("nostock@example.com", staff_app=True)
	_, html = csrf(n)
	check("non-stock user sees allowed: 0", "allowed: 0" in html)
	frappe.db.commit(); nrow = frappe.db.sql("select sessiondata from tabSessions where sid=%s", n.cookies.get("sid"))
	check("non-stock user NOT given a long session", nrow and "staff_app" not in nrow[0][0])

	# ── feature off → normal sessions ────────────────────────────────────────
	delcfg("kgs_staff_session_days")
	s4, r4, _ = login("staff1@example.com", staff_app=True)
	check("with the key at 0 the staff login gets 1 hour", sid_max_age(r4) == 3600, sid_max_age(r4))

	# ── logout ───────────────────────────────────────────────────────────────
	lo = s.post(f"{BASE}/api/method/logout", json={}, headers={"X-Frappe-CSRF-Token": token})
	check("logout ok", lo.status_code == 200)
	check("logout does not re-arm the cookie", sid_max_age(lo) in (None, 0) or "sid=Guest" in lo.headers.get("Set-Cookie", ""), lo.headers.get("Set-Cookie"))
finally:
	frappe.db.set_single_value("System Settings", {"session_expiry": orig["session_expiry"],
		"enable_two_factor_auth": orig["enable_two_factor_auth"], "two_factor_method": orig["two_factor_method"]})
	frappe.db.set_value("Role", "Stock User", "two_factor_auth", orig["role_2fa"])
	frappe.db.set_default("session_expiry", orig["default_expiry"])
	frappe.clear_cache()
	frappe.db.set_value("Role", "Sales User", "two_factor_auth", orig["role_2fa_sales"])
	frappe.db.commit()
	delcfg("kgs_staff_session_days")
	print("restored:", orig)

print(f"\n{sum(1 for r in RESULTS if r[1])}/{len(RESULTS)} passed")
