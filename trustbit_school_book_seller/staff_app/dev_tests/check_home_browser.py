"""Headless phone-size test of the /staff Home, the bottom tab bar and More (1.14.0), on
http://127.0.0.1:8001 (site1.local). Needs `bench --site site1.local serve --port 8001` and the
test users made by check_staff_api.py / check_paper_api.py (staff1, paper_po, nostock) plus
home_owner@example.com (Shop Owner + Purchase + Stock, made by this script if missing).
Run with a Python that has playwright:
    python3 check_home_browser.py
It plants two papers for home_owner (one "to check", one "not read") and turns Receipts and
Bills on for home_owner only; the settings are put back at the end (also on failure)."""
import json
import os
import re
import subprocess

from playwright.sync_api import expect, sync_playwright

S = os.path.dirname(os.path.abspath(__file__)) + "/"
APP = os.path.abspath(S + "../../..") + "/"  # apps/trustbit_school_book_seller/
BENCH = os.path.abspath(S + "../../../../..") + "/"  # frappe-bench/
BASE = "http://127.0.0.1:8001"
EXE = "/Users/warroom/Library/Caches/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-mac-arm64/chrome-headless-shell"
PW = "Kgs-Test-2026!x"
OWNER, BUYER, STOCK, NOROLE = "home_owner@example.com", "paper_po@example.com", "staff1@example.com", "nostock@example.com"
PHONE = dict(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
VERSION = re.search(r"^## \[(\d+\.\d+\.\d+)\]", open(APP + "CHANGELOG.md").read(), re.M).group(1)
RESULTS = []


def check(name, cond, detail=""):
	RESULTS.append((name, bool(cond)))
	print(("PASS " if cond else "FAIL ") + name + (f" — {detail}" if detail and not cond else ""), flush=True)


def ok(name, fn):
	try:
		fn()
		check(name, True)
	except Exception as e:
		check(name, False, str(e).splitlines()[0][:200])


def bench_py(code):
	pre = "import frappe, json\nfrappe.init(site='site1.local', sites_path='.')\nfrappe.connect()\n"
	r = subprocess.run([BENCH + "env/bin/python", "-c", pre + code], cwd=BENCH + "sites", capture_output=True, text=True, timeout=120)
	if r.returncode:
		raise RuntimeError(r.stderr[-800:])
	out = [ln for ln in r.stdout.splitlines() if ln.strip()]
	return json.loads(out[-1]) if out else None


# ── setup + API checks (bench side) ──────────────────────────────────────────
SETUP = bench_py(f"""
from frappe.utils.password import update_password
if not frappe.db.exists("User", {OWNER!r}):
	u = frappe.get_doc({{"doctype": "User", "email": {OWNER!r}, "first_name": "Saransh", "last_name": "(test)", "send_welcome_email": 0}})
	u.insert(ignore_permissions=True)
	u.add_roles("Shop Owner", "Purchase User", "Purchase Manager", "Stock User", "Stock Manager")
for u in ({OWNER!r}, {BUYER!r}, {STOCK!r}, {NOROLE!r}):
	update_password(u, {PW!r})
s = frappe.get_doc("Order Paper Settings")
before = {{"enabled": s.enabled, "pr_pi_enabled": s.pr_pi_enabled, "receivers": [r.user for r in s.receivers]}}
s.enabled, s.pr_pi_enabled = 1, 1
if {OWNER!r} not in before["receivers"]:
	s.append("receivers", {{"user": {OWNER!r}}})
s.save(ignore_permissions=True)
frappe.set_user({OWNER!r})
made = []
for status, party in (("Ready", "Home Test Publisher"), ("Failed", "Home Test Unread Co")):
	d = frappe.get_doc({{"doctype": "Order Paper", "purpose": "Purchase Order", "status": status, "paper_party_text": party, "page_count": 1}})
	d.insert(ignore_permissions=True)
	made.append(d.name)
frappe.set_user("Administrator")
# the Continue-transfer step adds a pen: other suites may have moved every pen out of Stores
if (frappe.db.get_value("Bin", {{"item_code": "KGS-T-PEN", "warehouse": "Stores - DCV"}}, "actual_qty") or 0) < 5:
	se = frappe.get_doc({{"doctype": "Stock Entry", "stock_entry_type": "Material Receipt",
		"company": frappe.db.get_value("Warehouse", "Stores - DCV", "company"),
		"items": [{{"item_code": "KGS-T-PEN", "qty": 20, "t_warehouse": "Stores - DCV", "basic_rate": 5}}]}})
	se.insert()
	se.submit()
frappe.cache.delete_keys("kgs_staff_rl:")
frappe.db.commit()
since =str(frappe.utils.add_days(frappe.utils.nowdate(), -30))
def mine(user, status):
	return frappe.db.count("Order Paper", {{"owner": user, "status": status, "creation": [">=", since]}})
pending = frappe.db.count("Purchase Order", {{"docstatus": 0, "workflow_state": "Pending Approval"}})
buyer_pending = frappe.db.count("Purchase Order", {{"docstatus": 0, "workflow_state": "Pending Approval", "owner": {BUYER!r}}})
from trustbit_school_book_seller.staff_app import api
res = {{}}
for u in ({OWNER!r}, {BUYER!r}, {STOCK!r}, {NOROLE!r}):
	frappe.set_user(u)
	try:
		res[u] = api.po_waiting()
	except frappe.PermissionError as e:
		res[u] = "403"
frappe.set_user("Guest")
try:
	api.po_waiting()
	res["Guest"] = "open"
except frappe.PermissionError:
	res["Guest"] = "403"
frappe.set_user("Administrator")
frappe.cache.delete_keys("kgs_staff_rl:")
print(json.dumps({{"before": before, "made": made, "pending": pending, "buyer_pending": buyer_pending,
	"owner_ready": mine({OWNER!r}, "Ready"), "owner_failed": mine({OWNER!r}, "Failed"),
	"buyer_ready": mine({BUYER!r}, "Ready"), "buyer_failed": mine({BUYER!r}, "Failed"), "api": res}}, default=str))
""")
API = SETUP["api"]
a = API[OWNER].get("approve") or {}
check("api: owner gets every PO waiting for approval", a.get("count") == SETUP["pending"] and "mine" not in API[OWNER], API[OWNER])
check("api: owner's per-sender counts add up", sum(b["n"] for b in a.get("by", [])) == a.get("count"), a.get("by"))
check("api: owner link opens the pending list in the ERP", a.get("url") == "/app/purchase-order?workflow_state=Pending%20Approval", a.get("url"))
m = API[BUYER].get("mine") or {}
check("api: purchase user gets only their own pending POs", m.get("count") == SETUP["buyer_pending"] and "approve" not in API[BUYER], API[BUYER])
check("api: purchase user's link is filtered to them", m.get("url", "").endswith("&owner=paper_po%40example.com"), m.get("url"))
check("api: since_days / since_time are given", isinstance(m.get("since_days"), int) and re.fullmatch(r"\d\d:\d\d", m.get("since_time", "")), m)
check("api: stock-only user (no POs made) gets nothing", API[STOCK] == {}, API[STOCK])
check("api: user without an app role is refused", API[NOROLE] == "403", API[NOROLE])
check("api: Guest is refused", API["Guest"] == "403", API["Guest"])


def login(page, email):
	page.goto(f"{BASE}/staff/login")
	page.fill("input[type=email]", email)
	page.fill("input[type=password]", PW)
	page.click("button[type=submit]")
	expect(page).to_have_url(re.compile(r"/staff/home"), timeout=15000)


def no_sideways(page):
	return page.evaluate("document.documentElement.scrollWidth") <= 390


def nav(page):
	return page.locator("nav[aria-label=Main]")


def tab_names(page):
	return [t.split(",")[0].strip() for t in nav(page).locator(".tab-label").all_inner_texts()]


def plural(n, word):
	return f"{n} {word}{'' if n == 1 else 's'}"


try:
	with sync_playwright() as p:
		browser = p.chromium.launch(executable_path=EXE)
		errors = []

		def watch(page):
			page.on("pageerror", lambda e: errors.append(f"pageerror {e}"))
			page.on("response", lambda r: errors.append(f"{r.status} {r.url}") if r.status >= 500 else None)

		# ── 1. Owner: approvals, papers to check, 4 Start tiles, 4 tabs ──────
		ctx = browser.new_context(**PHONE)
		page = ctx.new_page()
		watch(page)
		login(page, OWNER)
		ok("owner: greeting with first name", lambda: expect(page.get_by_text(re.compile(r"^Good (morning|afternoon|evening), Saransh$"))).to_be_visible(timeout=10000))
		ok("owner: KGS mark in the header", lambda: expect(page.locator("header").get_by_text("KGS", exact=True)).to_be_visible())
		ok("owner: no Sign out on Home any more", lambda: expect(page.get_by_role("button", name="Sign out")).to_have_count(0))
		wait = page.locator("section", has=page.get_by_role("heading", name="Waiting for you"))
		appr = wait.get_by_role("link", name=re.compile(rf"^{SETUP['pending']} Purchase Orders? to approve"))
		ok("owner: 'N Purchase Orders to approve' row", lambda: expect(appr).to_be_visible(timeout=10000))
		check("owner: approve row opens the ERP's pending list", appr.get_attribute("href") == "/app/purchase-order?workflow_state=Pending%20Approval", appr.get_attribute("href"))
		ok("owner: approve row names who sent them", lambda: expect(appr).to_contain_text(re.compile(r"paper_po \d+ · po_creator \d+ · oldest")))
		ok("owner: papers to check row", lambda: expect(wait.get_by_role("link", name=re.compile(rf"^{plural(SETUP['owner_ready'], 'paper')} to check"))).to_be_visible())
		ok("owner: papers not read row", lambda: expect(wait.get_by_role("link", name=re.compile(r"could not be read"))).to_be_visible())
		start = page.locator("section", has=page.get_by_role("heading", name="Start"))
		ok("owner: Start = Purchase Order, Receipt, Bill, Transfer", lambda: expect(start.get_by_role("link")).to_have_text([re.compile(r"^Purchase Order"), re.compile(r"^Receipt"), re.compile(r"^Bill"), re.compile(r"^Transfer")]))
		check("owner: Start tile links", [start.get_by_role("link").nth(i).get_attribute("href") for i in range(4)] == ["/staff/paper?for=po", "/staff/paper?for=pr", "/staff/paper?for=pi", "/staff/transfer"])
		ok("owner: one Recent list (papers + transfers), no See all", lambda: (expect(page.get_by_role("heading", name="Recent", exact=True)).to_be_visible(), expect(page.get_by_role("link", name="See all")).to_have_count(0)))
		recent = page.locator("section", has=page.get_by_role("heading", name="Recent", exact=True))
		ok("owner: Recent has rows", lambda: expect(recent.get_by_role("link").first).to_be_visible(timeout=10000))
		check("owner: Recent shows at most 5 rows", 1 <= recent.get_by_role("link").count() <= 5, recent.get_by_role("link").count())
		ok("owner: tabs Home · Papers · Transfers · More", lambda: check("owner: tab names", tab_names(page) == ["Home", "Papers", "Transfers", "More"], tab_names(page)))
		ok("owner: Home tab is the current one", lambda: expect(nav(page).get_by_role("link", name="Home")).to_have_attribute("aria-current", "page"))
		badge = SETUP["owner_ready"] + SETUP["owner_failed"]
		ok("owner: Papers badge = papers to check + not read", lambda: expect(nav(page).get_by_role("link", name=re.compile(r"^Papers"))).to_contain_text(str(badge if badge < 10 else "9+")))
		check("owner: no sideways scroll on Home", no_sideways(page))
		page.screenshot(path=S + "shot_home_owner.png")
		page.screenshot(path=S + "shot_home_owner_full.png", full_page=True)

		wait.get_by_role("link", name=re.compile(r"to check")).click()
		ok("owner: papers-to-check row opens the paper / the filtered list", lambda: expect(page).to_have_url(re.compile(r"/staff/paper/OP-|/staff/papers\?status=Ready")))
		ok("owner: no tab bar while checking a paper", lambda: expect(nav(page)).to_have_count(0) if "/paper/" in page.url else None)

		page.goto(f"{BASE}/staff/papers?status=Ready")
		ok("papers: '?status=Ready' shows only papers to check", lambda: expect(page.get_by_text("Only To check")).to_be_visible(timeout=10000))
		ok("papers: filtered rows are all 'To check'", lambda: expect(page.locator("main a[href^='/staff/paper/']").first).to_contain_text("To check", timeout=10000))
		ok("papers: tab bar shown, Papers current", lambda: expect(nav(page).get_by_role("link", name=re.compile(r"^Papers"))).to_have_attribute("aria-current", "page"))
		ok("papers: no Back button on a tab screen", lambda: expect(page.get_by_role("button", name="Back")).to_have_count(0))
		page.get_by_role("link", name="Show all").click()
		ok("papers: Show all drops the filter", lambda: (expect(page).to_have_url(re.compile(r"/staff/papers$")), expect(page.get_by_text("Only To check")).to_have_count(0)))
		page.goto(f"{BASE}/staff/papers?status=Failed")
		ok("papers: '?status=Failed' shows only papers not read", lambda: expect(page.get_by_text("Only Not read")).to_be_visible(timeout=10000))

		nav(page).get_by_role("link", name="Transfers").click()
		ok("tabs: Transfers tab opens the transfer list", lambda: (expect(page).to_have_url(re.compile(r"/staff/transfers$")), expect(page.get_by_role("heading", name="Transfers")).to_be_visible()))

		nav(page).get_by_role("link", name="More").click()
		ok("more: opens on the More tab", lambda: (expect(page).to_have_url(re.compile(r"/staff/more$")), expect(page.get_by_role("heading", name="More")).to_be_visible()))
		ok("more: name + what this person can do", lambda: (expect(page.get_by_text("Saransh (test)")).to_be_visible(), expect(page.get_by_text("Shop Owner · Purchase · Stock")).to_be_visible()))
		ok("more: Remembered names + Settings rows", lambda: (expect(page.get_by_role("link", name=re.compile(r"^Remembered names"))).to_have_attribute("href", "/staff/names"), expect(page.get_by_role("link", name=re.compile(r"^Settings"))).to_have_attribute("href", "/staff/settings")))
		page.get_by_role("button", name=re.compile(r"^Add to home screen")).click()
		ok("more: Add to home screen explains how (no install offer in a test browser)", lambda: expect(page.get_by_text(re.compile(r"Add to Home screen|Add to Home Screen")).first).to_be_visible())
		ok("more: version from the changelog", lambda: expect(page.get_by_text(f"KGS Staff · version {VERSION}")).to_be_visible())
		check("more: no sideways scroll", no_sideways(page))
		page.screenshot(path=S + "shot_more.png", full_page=True)

		page.goto(f"{BASE}/staff/home")
		start.get_by_role("link", name=re.compile(r"^Transfer")).click()
		ok("owner: Transfer tile opens the transfer screen, no tab bar there", lambda: (expect(page).to_have_url(re.compile(r"/staff/transfer$")), expect(nav(page)).to_have_count(0)))

		page.goto(f"{BASE}/staff/more")
		page.get_by_role("button", name="Sign out").click()
		ok("more: Sign out returns to the login page", lambda: expect(page).to_have_url(re.compile(r"/staff/login$"), timeout=10000))
		ok("login page has no tab bar", lambda: expect(nav(page)).to_have_count(0))
		ctx.close()

		# ── 2. Purchase User (no stock): own pending POs, one wide tile ───────
		ctx = browser.new_context(**PHONE)
		page = ctx.new_page()
		watch(page)
		login(page, BUYER)
		wait = page.locator("section", has=page.get_by_role("heading", name="Waiting for you"))
		n = SETUP["buyer_pending"]
		mine_row = wait.get_by_role("link", name=re.compile(r"^Your PO waits for approval" if n == 1 else rf"^{n} of your POs wait for approval"))
		ok("buyer: own POs waiting for approval", lambda: expect(mine_row).to_be_visible(timeout=10000))
		ok("buyer: says how long they have been with the owners", lambda: expect(mine_row).to_contain_text(re.compile(r"With the owners (since \d\d:\d\d|since yesterday|for \d+ days)")))
		check("buyer: the row opens their own pending POs in the ERP", (mine_row.get_attribute("href") or "").endswith("&owner=paper_po%40example.com"), mine_row.get_attribute("href"))
		ok("buyer: no approve row", lambda: expect(page.get_by_text(re.compile(r"to approve"))).to_have_count(0))
		start = page.locator("section", has=page.get_by_role("heading", name="Start"))
		ok("buyer: one Start tile, full width", lambda: (expect(start.get_by_role("link")).to_have_count(1), expect(start.get_by_role("link")).to_have_class(re.compile(r"col-span-2"))))
		ok("buyer: 'Your recent papers' with See all", lambda: (expect(page.get_by_role("heading", name="Your recent papers")).to_be_visible(), expect(page.get_by_role("link", name="See all")).to_have_attribute("href", "/staff/papers")))
		ok("buyer: tabs Home · Papers · More (no Transfers)", lambda: check("buyer: tab names", tab_names(page) == ["Home", "Papers", "More"], tab_names(page)))
		check("buyer: no sideways scroll", no_sideways(page))
		page.screenshot(path=S + "shot_home_buyer.png", full_page=True)
		ctx.close()

		# ── 3. Stock User: one wide tile, transfers list, continue bar ───────
		ctx = browser.new_context(**PHONE)
		page = ctx.new_page()
		watch(page)
		login(page, STOCK)
		ok("stock: no 'Waiting for you' when nothing waits", lambda: (expect(page.get_by_role("heading", name="Your recent transfers")).to_be_visible(timeout=10000), expect(page.get_by_role("heading", name="Waiting for you")).to_have_count(0)))
		start = page.locator("section", has=page.get_by_role("heading", name="Start"))
		ok("stock: one wide 'New transfer' tile", lambda: (expect(start.get_by_role("link")).to_have_count(1), expect(start.get_by_role("link")).to_contain_text("New transfer")))
		ok("stock: tabs Home · Transfers · More", lambda: check("stock: tab names", tab_names(page) == ["Home", "Transfers", "More"], tab_names(page)))
		recent = page.locator("section", has=page.get_by_role("heading", name="Your recent transfers"))
		first = recent.get_by_role("link", name=re.compile(r"MAT-STE-")).first
		ok("stock: transfer rows show a zero-padded time", lambda: expect(first).to_contain_text(re.compile(r"MAT-STE-\d+-\d+ · (today \d\d:\d\d|yesterday \d\d:\d\d|\d+ [A-Z][a-z]{2})")))
		check("stock: no '5:56:'-style broken time", not re.search(r"\b\d:\d\d:", recent.inner_text()), recent.inner_text()[:200])
		ok("stock: See all opens the transfer list", lambda: expect(page.get_by_role("link", name="See all")).to_have_attribute("href", "/staff/transfers"))
		page.screenshot(path=S + "shot_home_stock.png", full_page=True)

		start.get_by_role("link").click()
		expect(page.locator("#from-wh")).to_be_visible(timeout=10000)
		page.select_option("#from-wh", "Stores - DCV")
		page.select_option("#to-wh", "Godown - DCV")
		page.fill("input[aria-label='Barcode, ISBN or item code']", "KGS-T-PEN")
		page.keyboard.press("Enter")
		expect(page.locator("div.font-semibold", has_text="Test Blue Pen").first).to_be_visible(timeout=10000)
		page.goto(f"{BASE}/staff/home")
		ok("stock: 'Continue transfer' bar for the transfer left on the phone", lambda: expect(page.get_by_role("link", name=re.compile(r"Continue transfer\s*1 item scanned · Stores( - DCV)? → Godown"))).to_be_visible(timeout=10000))
		check("stock: no sideways scroll", no_sideways(page))
		page.screenshot(path=S + "shot_home_stock_draft.png", full_page=True)
		page.get_by_role("link", name=re.compile(r"Continue transfer")).click()
		ok("stock: the bar opens the same transfer", lambda: expect(page.locator("div.font-semibold", has_text="Test Blue Pen").first).to_be_visible(timeout=10000))
		ctx.close()

		check("no page errors or server errors", not errors, "; ".join(errors[:5]))
		browser.close()
finally:
	bench_py(f"""
s = frappe.get_doc("Order Paper Settings")
b = {SETUP["before"]!r}
s.enabled, s.pr_pi_enabled = b["enabled"], b["pr_pi_enabled"]
s.set("receivers", [])
for u in b["receivers"]:
	s.append("receivers", {{"user": u}})
s.save(ignore_permissions=True)
for n in {SETUP["made"]!r}:
	frappe.db.set_value("Order Paper", n, "status", "Discarded")
frappe.cache.delete_keys("kgs_staff_rl:")
frappe.db.commit()
print(json.dumps(1))
""")

passed = sum(1 for _, c in RESULTS if c)
print(f"\n{passed}/{len(RESULTS)} passed")
raise SystemExit(0 if passed == len(RESULTS) else 1)
