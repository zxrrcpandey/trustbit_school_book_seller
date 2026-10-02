"""Browser checks of shortfall → Stock Reconciliation on http://127.0.0.1:8001 (site1.local, bench serve running).
Run after check_staff_reco.py."""
import os
import re
import sys

from playwright.sync_api import expect, sync_playwright

S = os.path.dirname(os.path.abspath(__file__)) + "/"
BASE = "http://127.0.0.1:8001"
EXE = "/Users/warroom/Library/Caches/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-mac-arm64/chrome-headless-shell"
PW = "Kgs-Test-2026!x"
RESULTS = []

# A never-stocked item made fresh for this run (other suites move test stock around).
import subprocess
import uuid

RUN = uuid.uuid4().hex[:6].upper()
NS, NS_NAME = f"KGS-T-NS-{RUN}", f"Test Never Bought {RUN}"
subprocess.run(
	["../env/bin/python", "-c", "import frappe;frappe.init(site='site1.local',sites_path='.');frappe.connect();"
	f"frappe.get_doc({{'doctype':'Item','item_code':'{NS}','item_name':'{NS_NAME}','item_group':'All Item Groups',"
	"'stock_uom':'PCS','is_stock_item':1}).insert(ignore_permissions=True);"
	# earlier runs move every pen out of Stores — top it up so the Stock User part has stock to scan
	"q=frappe.db.get_value('Bin',{'item_code':'KGS-T-PEN','warehouse':'Stores - DCV'},'actual_qty') or 0;"
	"se=frappe.get_doc({'doctype':'Stock Entry','stock_entry_type':'Material Receipt','company':'Development Company V1.0',"
	"'items':[{'item_code':'KGS-T-PEN','qty':50,'t_warehouse':'Stores - DCV','basic_rate':5}]}) if q < 20 else None;"
	"se and (se.insert(ignore_permissions=True), se.submit());frappe.db.commit()"],
	check=True,
)


def check(name, cond, detail=""):
	RESULTS.append((name, bool(cond)))
	print(("PASS " if cond else "FAIL ") + name + (f" — {detail}" if detail and not cond else ""), flush=True)


def ok(name, fn):
	try:
		fn()
		check(name, True)
	except Exception as e:
		check(name, False, str(e).splitlines()[0][:200])


def login(page, user):
	page.goto(f"{BASE}/staff/login")
	page.fill("input[type=email]", user)
	page.fill("input[type=password]", PW)
	page.click("button[type=submit]")
	page.wait_for_url(re.compile(r"/staff/home$"), timeout=15000)


def start(page):
	page.goto(f"{BASE}/staff/transfer")
	page.select_option("#from-wh", "Stores - DCV")
	page.select_option("#to-wh", "Godown - DCV")
	if page.get_by_role("button", name="Clear").count():
		page.once("dialog", lambda d: d.accept())
		page.get_by_role("button", name="Clear").click()


def add(page, code):
	page.fill("input[aria-label='Barcode, ISBN or item code']", code)
	page.keyboard.press("Enter")


def qty(page, name, value):
	page.locator("div.rounded-xl", has_text=name).first.locator("input[aria-label='Quantity']").fill(str(value))


with sync_playwright() as p:
	browser = p.chromium.launch(executable_path=EXE)
	phone = dict(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)

	# Stock User: short stays blocked
	ctx = browser.new_context(**phone)
	page = ctx.new_page()
	login(page, "staff1@example.com")
	start(page)
	add(page, NS)
	ok("Stock User: no-stock scan refused", lambda: expect(page.get_by_text(re.compile("No stock in Stores - DCV")).first).to_be_visible(timeout=10000))
	add(page, "KGS-T-PEN")
	page.wait_for_timeout(800)
	qty(page, "Test Blue Pen", 99999)
	ok("Stock User: short line is red + review blocked", lambda: (expect(page.get_by_text(re.compile(r"Only \d+ Nos"))).to_be_visible(), expect(page.get_by_role("button", name=re.compile("Review"))).to_be_disabled()))
	page.once("dialog", lambda d: d.accept())
	page.get_by_role("button", name="Clear").click()
	ctx.close()

	# Stock Manager
	ctx = browser.new_context(**phone)
	page = ctx.new_page()
	errors = []
	page.on("pageerror", lambda e: errors.append(str(e)))
	login(page, "mgr1@example.com")
	start(page)
	add(page, NS)
	ok("Manager: no-stock item added", lambda: expect(page.locator("div.font-semibold", has_text=NS_NAME).first).to_be_visible(timeout=10000))
	qty(page, NS_NAME, 5)
	add(page, "KGS-T-PEN")
	page.wait_for_timeout(800)
	pen_card = page.locator("div.rounded-xl", has_text="Test Blue Pen").first
	avail = int(re.search(r"Available: (\d+)", pen_card.inner_text()).group(1))
	qty(page, "Test Blue Pen", avail + 5)
	ok("Manager: short lines amber, review allowed", lambda: (expect(page.get_by_text(re.compile("You can count it on the next screen")).first).to_be_visible(), expect(page.get_by_role("button", name=re.compile("Review"))).to_be_enabled()))

	page.get_by_role("button", name=re.compile("Review")).click()
	ok("warning banner", lambda: expect(page.get_by_text(re.compile(r"Not enough stock in Stores - DCV"))).to_be_visible(timeout=10000))
	ok("rate empty when no purchase rate / valuation → Accept blocked", lambda: expect(page.get_by_role("button", name=re.compile("Accept"))).to_be_disabled())
	page.get_by_role("button", name="Reject").click()
	ok("Reject returns to the list, nothing moved", lambda: expect(page.get_by_role("button", name=re.compile("Review"))).to_be_visible())
	page.get_by_role("button", name=re.compile("Review")).click()

	never = page.locator("div[data-reco]", has_text=NS_NAME).first
	never.locator("input[type=number]").nth(1).fill("9")
	never.locator("select").select_option("Found extra stock")
	pen = page.locator("div[data-reco]", has_text="Test Blue Pen").first
	pen.locator("input[type=number]").first.fill(str(avail + 2))  # counted less than the 5 extra asked
	ok("count below the transfer: reduce note", lambda: expect(pen.get_by_text(re.compile(r"Only \d+ Nos will move"))).to_be_visible())
	ok("pen rate prefilled from current valuation", lambda: expect(pen.get_by_text("Filled from the current stock value.")).to_be_visible())
	pen.locator("input[type=number]").nth(1).fill("50")
	ok("rate far from last purchase rate → warning (none for pen: no LPR)", lambda: expect(pen.get_by_text(re.compile("very different from the last purchase price"))).to_have_count(0))
	pen.locator("select").select_option("Other")
	ok("Other needs a note", lambda: expect(page.get_by_role("button", name=re.compile("Accept"))).to_be_disabled())
	pen.locator("input[placeholder='What happened? (required)']").fill("found behind shelf")
	ok("value change shown (9 × 5 = 45 for the new item)", lambda: expect(never.get_by_text("₹45.00")).to_be_visible())
	page.screenshot(path=S + "shot_reco_review.png", full_page=True)
	ok("Accept enabled when all filled", lambda: expect(page.get_by_role("button", name=re.compile("Accept"))).to_be_enabled())
	page.get_by_role("button", name=re.compile("Accept")).click()
	ok("success page lists the reconciliation", lambda: (expect(page.get_by_text("Stock moved")).to_be_visible(timeout=60000), expect(page.get_by_text("Stock reconciled first").first).to_be_visible()))
	ok("detail: pen reduced to the count", lambda: expect(page.get_by_text(f"{avail + 2} Nos")).to_be_visible())
	ok("detail remarks name the reconciliation", lambda: expect(page.get_by_text(re.compile(r"Stock reconciled first: MAT-RECO-"))).to_be_visible())
	page.screenshot(path=S + "shot_reco_done.png", full_page=True)
	check("no JS errors", not errors, errors[:3])
	ctx.close()
	browser.close()

print(f"\n{sum(1 for r in RESULTS if r[1])}/{len(RESULTS)} passed")
sys.exit(0 if all(r[1] for r in RESULTS) else 1)
