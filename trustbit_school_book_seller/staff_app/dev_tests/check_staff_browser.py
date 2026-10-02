"""Headless browser test of the /staff PWA on http://127.0.0.1:8001 (site1.local).
Fake camera = barcode.y4m (EAN-13 9781234567897, a PKT barcode of KGS-T-BOOK1)."""
import os
import re
import sys

from playwright.sync_api import expect, sync_playwright

S = os.path.dirname(os.path.abspath(__file__)) + "/"
BASE = "http://127.0.0.1:8001"
EXE = "/Users/warroom/Library/Caches/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-mac-arm64/chrome-headless-shell"
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


ARGS = ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", f"--use-file-for-fake-video-capture={S}barcode.y4m"]
PHONE = dict(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)

with sync_playwright() as p:
	browser = p.chromium.launch(executable_path=EXE, args=ARGS)

	# ── Run 1: Android-like (native BarcodeDetector if the browser has one) ──
	ctx = browser.new_context(**PHONE)
	ctx.grant_permissions(["camera"], origin=BASE)
	page = ctx.new_page()
	errors = []
	page.on("pageerror", lambda e: errors.append(str(e)))
	page.on("response", lambda r: errors.append(f"{r.status} {r.url}") if r.status >= 400 else None)

	page.goto(f"{BASE}/staff/")
	ok("guest is sent to login", lambda: expect(page).to_have_url(re.compile(r"/staff/login$")))
	page.fill("input[type=email]", "staff1@example.com")
	page.fill("input[type=password]", "Kgs-Test-2026!x")
	page.click("button[type=submit]")
	ok("login lands on home", lambda: expect(page.get_by_text("Recent transfers")).to_be_visible(timeout=15000))
	page.screenshot(path=S + "shot_home.png")
	native = page.evaluate("'BarcodeDetector' in window")
	print("native BarcodeDetector in this browser:", native)

	page.get_by_text("New transfer").first.click()
	ok("transfer screen", lambda: expect(page.locator("#from-wh")).to_be_visible(timeout=10000))
	page.select_option("#from-wh", "Stores - DCV")
	page.select_option("#to-wh", "Godown - DCV")

	# typed code
	page.fill("input[aria-label='Barcode, ISBN or item code']", "KGS-T-PEN")
	page.keyboard.press("Enter")
	ok("typed code adds the pen", lambda: expect(page.locator("div.font-semibold", has_text="Test Blue Pen").first).to_be_visible(timeout=10000))

	# Bluetooth scanner (keyboard wedge, nothing focused): ISBN of the book
	page.evaluate("document.activeElement && document.activeElement.blur()")
	page.keyboard.type("9789999999990", delay=10)
	page.keyboard.press("Enter")
	ok("keyboard-wedge ISBN adds the book (PCS)", lambda: expect(page.locator("text=Test Viva Maths 3")).to_have_count(1, timeout=10000))

	# camera scan → packet barcode → PKT line
	page.get_by_role("button", name="📷 Scan").click()
	ok("camera scan adds a PKT line", lambda: expect(page.get_by_text(re.compile(r"\+1 Test Viva Maths 3 — now 1 PKT")).first).to_be_visible(timeout=20000))
	page.screenshot(path=S + "shot_scanner.png")
	page.get_by_role("button", name="Done").click()
	ok("book now has PCS + PKT lines", lambda: expect(page.locator("text=Test Viva Maths 3")).to_have_count(2))

	# over-available blocks review
	pen = page.locator("div.rounded-xl", has_text="Test Blue Pen").first
	pen.locator("input[aria-label='Quantity']").fill("99999")
	ok("over-available shows the reason", lambda: expect(page.get_by_text(re.compile(r"Only \d+ Nos in Stores - DCV"))).to_be_visible())
	ok("review is blocked", lambda: expect(page.get_by_role("button", name=re.compile("Review"))).to_be_disabled())
	pen.locator("input[aria-label='Quantity']").fill("2")
	ok("fixing qty unblocks review", lambda: expect(page.get_by_role("button", name=re.compile("Review"))).to_be_enabled())
	page.screenshot(path=S + "shot_lines.png", full_page=True)

	# draft survives a reload
	page.reload()
	ok("draft survives reload", lambda: expect(page.locator("text=Test Viva Maths 3")).to_have_count(2, timeout=10000))

	page.get_by_role("button", name=re.compile("Review")).click()
	page.fill("textarea", "Browser test — van MP48")
	page.screenshot(path=S + "shot_review.png")
	page.get_by_role("button", name=re.compile("Move stock now")).click()
	ok("success page", lambda: expect(page.get_by_text("Stock moved")).to_be_visible(timeout=60000))
	name = page.url.split("/t/")[1].split("?")[0]
	print("created", name)
	ok("detail lists 3 lines", lambda: expect(page.get_by_text("3 lines")).to_be_visible())
	ok("slip link present", lambda: expect(page.get_by_text("Print / share slip (PDF)")).to_be_visible())
	page.screenshot(path=S + "shot_done.png", full_page=True)
	page.get_by_text("New transfer (same warehouses)").click()
	ok("new transfer keeps warehouses, empty list", lambda: (expect(page.locator("#from-wh")).to_have_value("Stores - DCV"), expect(page.locator("#to-wh")).to_have_value("Godown - DCV")))
	page.goto(f"{BASE}/staff/transfers")
	ok("transfers list shows it", lambda: expect(page.get_by_text(name)).to_be_visible(timeout=10000))
	page.goto(f"{BASE}/staff/t/{name}")
	ok("hard refresh on /staff/t/<name> works", lambda: expect(page.get_by_text("3 lines")).to_be_visible(timeout=10000))
	check("no JS errors (run 1)", not [e for e in errors if "favicon" not in e], errors[:5])
	ctx.close()

	# ── Run 2: iPhone path — no native BarcodeDetector, WASM polyfill ────────
	ctx = browser.new_context(**PHONE)
	ctx.grant_permissions(["camera"], origin=BASE)
	ctx.add_init_script("delete window.BarcodeDetector")
	page = ctx.new_page()
	wasm = []
	page.on("response", lambda r: wasm.append((r.url, r.status)) if r.url.endswith(".wasm") else None)
	cdn = []
	page.on("request", lambda r: cdn.append(r.url) if "jsdelivr" in r.url or "fastly" in r.url else None)
	page.goto(f"{BASE}/staff/login")
	page.fill("input[type=email]", "staff1@example.com")
	page.fill("input[type=password]", "Kgs-Test-2026!x")
	page.click("button[type=submit]")
	page.wait_for_url(re.compile(r"/staff/home$"), timeout=15000)
	page.goto(f"{BASE}/staff/transfer")
	page.select_option("#from-wh", "Stores - DCV")
	page.select_option("#to-wh", "Godown - DCV")
	check("native detector hidden", not page.evaluate("'BarcodeDetector' in window"))
	page.get_by_role("button", name="📷 Scan").click()
	ok("WASM scanner reads the barcode", lambda: expect(page.get_by_text(re.compile(r"\+1 Test Viva Maths 3")).first).to_be_visible(timeout=30000))
	check("WASM fetched from our own /assets", any("/assets/trustbit_school_book_seller/staff/zxing-1.3.4/" in u and s == 200 for u, s in wasm), wasm)
	check("nothing fetched from a CDN", not cdn, cdn)
	page.get_by_role("button", name="Done").click()
	page.get_by_role("button", name="Clear").click() if False else None
	ctx.close()
	browser.close()

print(f"\n{sum(1 for r in RESULTS if r[1])}/{len(RESULTS)} passed")
sys.exit(0 if all(r[1] for r in RESULTS) else 1)
