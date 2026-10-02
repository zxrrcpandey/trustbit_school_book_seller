"""Browser checks of the bulk features on http://127.0.0.1:8001 (site1.local), with a
local `bench worker --queue long` running. Run AFTER check_staff_bulk.py (test set + 320 items).
Moves ALL stock Stores - DCV → Godown - DCV in the background, then all of it back."""
import os
import re
import sys

from playwright.sync_api import expect, sync_playwright

S = os.path.dirname(os.path.abspath(__file__)) + "/"
BASE = "http://127.0.0.1:8001"
EXE = "/Users/warroom/Library/Caches/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-mac-arm64/chrome-headless-shell"
PW = "Kgs-Test-2026!x"
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


def login(page, user):
	page.goto(f"{BASE}/staff/login")
	page.fill("input[type=email]", user)
	page.fill("input[type=password]", PW)
	page.click("button[type=submit]")
	page.wait_for_url(re.compile(r"/staff/home$"), timeout=15000)


def new_transfer(page, src, dst):
	page.goto(f"{BASE}/staff/transfer")
	page.select_option("#from-wh", src)
	page.select_option("#to-wh", dst)
	if page.get_by_role("button", name="Clear").count():
		page.once("dialog", lambda d: d.accept())
		page.get_by_role("button", name="Clear").click()


def move_all_in_background(page, src, dst, label):
	new_transfer(page, src, dst)
	page.get_by_role("button", name=re.compile("Add in bulk")).click()
	page.get_by_role("button", name="All stock", exact=True).click()
	page.get_by_role("button", name=re.compile(f"Load all items in {src}")).click()
	ok(f"{label}: all stock loaded", lambda: expect(page.get_by_text(re.compile(r"Everything in .*lines? added"))).to_be_visible(timeout=60000))
	page.get_by_role("button", name="Back to the transfer").click()
	page.get_by_role("button", name=re.compile("Review")).click()
	ok(f"{label}: review offers background move", lambda: expect(page.get_by_role("button", name=re.compile(r"Move in background \(\d+ transfers\)"))).to_be_visible())
	page.screenshot(path=S + f"shot_bulk_review_{label}.png")
	page.get_by_role("button", name=re.compile("Move in background")).click()
	ok(f"{label}: progress page", lambda: expect(page).to_have_url(re.compile(r"/staff/bulk/"), timeout=120000))
	ok(f"{label}: all stock moved", lambda: expect(page.get_by_text("All stock moved")).to_be_visible(timeout=300000))
	page.screenshot(path=S + f"shot_bulk_done_{label}.png", full_page=True)


with sync_playwright() as p:
	browser = p.chromium.launch(executable_path=EXE)
	phone = dict(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)

	# ── Stock User: school set + CSV ─────────────────────────────────────────
	ctx = browser.new_context(**phone)
	page = ctx.new_page()
	errors = []
	page.on("pageerror", lambda e: errors.append(str(e)))
	login(page, "staff1@example.com")
	new_transfer(page, "Stores - DCV", "Godown - DCV")
	page.get_by_role("button", name=re.compile("Add in bulk")).click()
	page.fill("input[aria-label='Search school sets']", "rdps 3")
	page.get_by_text("Test RDPS 3 Book Set").first.click()
	page.fill("#sets", "2")
	page.get_by_role("button", name="Add 2 sets").click()
	ok("school set added", lambda: expect(page.get_by_text(re.compile(r"Test RDPS 3 Book Set × 2: 2 lines added"))).to_be_visible(timeout=20000))
	ok("set shows the 2 left-out items with reasons", lambda: expect(page.get_by_text("2 not added")).to_be_visible())
	page.screenshot(path=S + "shot_bulk_set.png", full_page=True)
	page.get_by_role("button", name="Back to the transfer").click()
	ok("set lines in the draft", lambda: expect(page.get_by_text("2 lines ·")).to_be_visible())

	page.get_by_role("button", name=re.compile("Add in bulk")).click()
	page.get_by_role("button", name="Excel / CSV").click()
	csv = S + "upload_test.csv"
	open(csv, "w").write("Code,Qty\n9789999999990,3\nKGS-T-PEN,1\nNOPE-1,5\n")
	page.set_input_files("input[type=file]", csv)
	ok("csv loaded: 2 merged onto existing lines", lambda: expect(page.get_by_text(re.compile(r"upload_test\.csv \(3 rows\): 0 lines added, 2 added onto existing lines"))).to_be_visible(timeout=20000))
	ok("csv unknown row reported", lambda: expect(page.get_by_text(re.compile("Row 4"))).to_be_visible())
	os.remove(csv)
	page.get_by_role("button", name="Back to the transfer").click()
	book = page.locator("div.rounded-xl", has_text="Test Viva Maths 3").first
	ok("merged qty = 2 + 3 = 5", lambda: expect(book.locator("input[aria-label='Quantity']")).to_have_value("5"))
	page.get_by_role("button", name=re.compile("Review")).click()
	page.get_by_role("button", name=re.compile("Move stock now")).click()
	ok("small bulk-loaded transfer submits normally", lambda: expect(page.get_by_text("Stock moved")).to_be_visible(timeout=60000))

	# Stock User cannot go over 150
	new_transfer(page, "Stores - DCV", "Godown - DCV")
	page.get_by_role("button", name=re.compile("Add in bulk")).click()
	page.get_by_role("button", name="All stock", exact=True).click()
	page.get_by_role("button", name=re.compile("Load all items")).click()
	page.get_by_role("button", name="Back to the transfer").click(timeout=60000)
	ok("Stock User blocked above 150 lines", lambda: expect(page.get_by_text(re.compile(r"A Stock Manager can move more in the background"))).to_be_visible())
	ok("paging: only 100 lines rendered", lambda: expect(page.get_by_role("button", name=re.compile(r"Show 100 more"))).to_be_visible())
	page.once("dialog", lambda d: d.accept())
	page.get_by_role("button", name="Clear").click()
	check("no JS errors (staff)", not errors, errors[:3])
	ctx.close()

	# ── Stock Manager: everything, in the background, there and back ─────────
	ctx = browser.new_context(**phone)
	page = ctx.new_page()
	login(page, "mgr1@example.com")
	move_all_in_background(page, "Stores - DCV", "Godown - DCV", "there")
	move_all_in_background(page, "Godown - DCV", "Stores - DCV", "back")
	ctx.close()
	browser.close()

print(f"\n{sum(1 for r in RESULTS if r[1])}/{len(RESULTS)} passed")
sys.exit(0 if all(r[1] for r in RESULTS) else 1)
