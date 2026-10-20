"""Headless phone-size test of Receipts and Bills from paper in the /staff PWA, on the THROWAWAY
site made by setup_paper_purchase_site.py (http://127.0.0.1:8002, paper.local).
Needs: `bench --site paper.local serve --port 8002` and `bench worker --queue default,short`, and
check_paper_purchase.py run once before (it makes the items, suppliers and the pp_* users).
Run with a Python that has playwright:
    <venv>/bin/python check_paper_purchase_browser.py
Flow: Dolly reads a bill → links the open PO (preselected, with its match %) → fixes a misread
quantity, keeps an over-delivery, leaves the unknown line out → the red bar goes → submits the
Receipt → "Make the bill now" → the Bill (same reading, no second AI read) adds the freight →
submits. Then the owner's settings screen. The AI is the fake provider: site_config
"kgs_paper_ai_fake" points at a JSON file this script writes, and is removed again at the end."""
import json
import os
import re
import subprocess
import time

from playwright.sync_api import expect, sync_playwright

S = os.path.dirname(os.path.abspath(__file__)) + "/"
BENCH = os.path.abspath(S + "../../../../..") + "/"  # frappe-bench/
SITE = "paper.local"
BASE = "http://127.0.0.1:8002"
EXE = "/Users/warroom/Library/Caches/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-mac-arm64/chrome-headless-shell"
PW = "Kgs-Test-2026!x"
C, WH = "KGS Test Stores", "Stores - KGS"
SEL = "Selina Test Publishers"
DOLLY, OWNER = "pp_dolly@example.com", "pp_owner@example.com"
FREIGHT = "Freight & Forwarding Charges - KGS"
SPEC = S + "paper_purchase_fake_reading.json"
SAMPLE = S + "paper_sample.jpg"
PHONE = dict(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
RESULTS = []
BILL_NO = "25-26/B" + time.strftime("%H%M%S")


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
	pre = f"import frappe, json\nfrappe.init(site={SITE!r}, sites_path='.')\nfrappe.connect()\n"
	r = subprocess.run([BENCH + "env/bin/python", "-c", pre + code], cwd=BENCH + "sites", capture_output=True, text=True, timeout=180)
	if r.returncode:
		raise RuntimeError(r.stderr[-800:])
	out = [ln for ln in r.stdout.splitlines() if ln.strip()]
	return json.loads(out[-1]) if out else None


def no_sideways(page):
	return page.evaluate("document.documentElement.scrollWidth") <= 390


def line_card(page, text):
	return page.locator("article", has_text=text)


# ── setup (bench side): passwords, settings, an approved PO ──────────────────
setup = bench_py(f"""
from frappe.utils import add_days, nowdate
from frappe.utils.password import update_password
from frappe.model.workflow import apply_workflow
from frappe.installer import update_site_config
from PIL import Image, ImageDraw
img = Image.new("RGB", (1240, 1754), "white")
ImageDraw.Draw(img).text((80, 80), "SELINA PUBLISHERS — TAX INVOICE {BILL_NO}", fill="black")
img.save({SAMPLE!r}, "JPEG", quality=85)
for u in ({DOLLY!r}, {OWNER!r}):
	update_password(u, {PW!r})
s = frappe.get_doc("Order Paper Settings")
s.enabled, s.so_enabled, s.pr_pi_enabled, s.rerank, s.auto_fallback, s.month_page_limit, s.peak_month_page_limit = 1, 0, 1, 0, 0, 0, 0
s.freight_account = {FREIGHT!r}
s.set("receivers", [{{"user": {DOLLY!r}}}])
s.save(ignore_permissions=True)
frappe.db.sql("update `tabOrder Paper` set status = 'Discarded' where status not in ('Saved', 'Discarded')")
frappe.cache.delete_keys("kgs_staff_rl:")
frappe.set_user({OWNER!r})
po = frappe.get_doc({{"doctype": "Purchase Order", "company": {C!r}, "supplier": {SEL!r}, "transaction_date": nowdate(),
	"schedule_date": add_days(nowdate(), 7), "set_warehouse": {WH!r},
	"items": [{{"item_code": c, "qty": q, "rate": r, "schedule_date": add_days(nowdate(), 7), "warehouse": {WH!r}}}
		for c, q, r in (("BK-PHY9", 50, 455), ("BK-CHE10", 40, 350), ("BK-MAT6", 9, 240))]}})
po.insert()
apply_workflow(po, "Send for Approval")
po.reload()
apply_workflow(po, "Approve")
frappe.db.commit()
update_site_config("kgs_paper_ai_fake", {SPEC!r})
print(json.dumps({{"po": po.name, "docstatus": frappe.db.get_value("Purchase Order", po.name, "docstatus"),
	"gstin": frappe.db.get_value("Supplier", {SEL!r}, "gstin")}}))
""")
PO = setup["po"]
check("setup: PO approved + submitted", setup["docstatus"] == 1, str(setup))
READING = {
	"paper_kind": "bill", "party_name": "SELINA PUBLISHERS", "party_gstin": setup["gstin"],
	"buyer_name": C, "paper_no": BILL_NO, "paper_date": time.strftime("%d-%m-%Y"),
	"lines": [
		{"text": "Selina Concise Physics 9", "qty": 50, "mrp": 692, "discount_percent": 30, "rate": 692, "amount": 24220},
		{"text": "Selina Concise Chemistry 10", "qty": 60, "mrp": 500, "discount_percent": 30, "amount": 21000},
		{"text": "Selina Mathematics 6", "qty": 3, "rate": 240, "amount": 2160},
		{"text": "Classmate Register 200 Pages", "qty": 10, "rate": 40, "amount": 400},
		{"text": "Selina Atlas Junior zqx", "qty": 10, "rate": 50, "amount": 500},
	],
	"items_total": 48280, "tax_total": 72, "charges": [{"label": "Freight", "amount": 720}], "grand_total": 49072,
}
with open(SPEC, "w") as f:
	json.dump({"reading": READING, "rerank": {"choices": []}, "_stream_delay": 0.3}, f)


def login(page, email):
	page.goto(f"{BASE}/staff/login")
	page.fill("input[type=email]", email)
	page.fill("input[type=password]", PW)
	page.click("button[type=submit]")


try:
	with sync_playwright() as p:
		browser = p.chromium.launch(executable_path=EXE)
		ctx = browser.new_context(**PHONE)
		page = ctx.new_page()
		errors = []
		page.on("pageerror", lambda e: errors.append(str(e)))
		page.on("response", lambda r: errors.append(f"{r.status} {r.url}") if r.status >= 400 else None)
		page.on("dialog", lambda d: d.accept())

		# ── 1. Receipt from the paper, linked to the PO ──────────────────────
		login(page, DOLLY)
		pr_tile = page.get_by_role("link", name=re.compile(r"^Receipt\s+Goods have arrived"))
		ok("Dolly: Receipt and Bill tiles", lambda: (expect(pr_tile).to_be_visible(timeout=15000),
			expect(page.get_by_role("link", name=re.compile(r"^Bill\s+Supplier's bill"))).to_be_visible()))
		pr_tile.click()
		ok("new paper: PO / Receipt / Invoice to choose from", lambda: (expect(page.get_by_role("button", name=re.compile("^Purchase Receipt"))).to_be_visible(),
			expect(page.get_by_role("button", name=re.compile("^Purchase Invoice"))).to_be_visible()))
		ok("Receipt preselected", lambda: expect(page.get_by_role("button", name=re.compile("^Purchase Receipt"))).to_have_attribute("aria-pressed", "true"))
		check("new paper: no sideways scroll", no_sideways(page))
		page.screenshot(path=S + "shot_pp_new.png")
		page.locator("input[type=file][multiple]").set_input_files(SAMPLE)
		page.get_by_role("button", name="Read the paper (1 page)").click()
		ok("upload → paper page", lambda: expect(page).to_have_url(re.compile(r"/staff/paper/OP-\d{4}-\d+$"), timeout=20000))
		pr_paper = page.url.rsplit("/", 1)[1]
		ok("read → 'Link the PO' step", lambda: expect(page.get_by_text("Link the PO", exact=True)).to_be_visible(timeout=60000))
		po_card = page.get_by_role("button", name=re.compile(PO))
		ok("open PO listed with its match %", lambda: expect(po_card).to_contain_text(re.compile(r"\d+% match")))
		ok("PO ticked as Best fit", lambda: (expect(po_card).to_have_attribute("aria-pressed", "true"), expect(po_card).to_contain_text("Best fit")))
		ok("supplier found by GSTIN", lambda: expect(page.get_by_text(SEL, exact=True)).to_be_visible())
		check("link step: no sideways scroll", no_sideways(page))
		page.screenshot(path=S + "shot_pp_link.png", full_page=True)
		page.get_by_role("button", name="Link 1 PO and check the lines").click()
		ok("linked → check screen", lambda: expect(page.get_by_text("Receipt from paper", exact=True)).to_be_visible(timeout=15000))
		ok("'Linked to' shows the PO", lambda: expect(page.locator("section", has_text="Linked to").get_by_text(PO)).to_be_visible())
		red = page.get_by_role("alert")
		ok("red bar while a line is misread", lambda: expect(red).to_contain_text("1 line to fix"))
		nxt = page.get_by_role("button", name="Next: save the Receipt")
		ok("Next blocked while lines need checking / fixing", lambda: (expect(nxt).to_be_disabled(),
			expect(page.get_by_text(re.compile(r"^(Fix|Check) \d+ (more )?lines? first"))).to_be_visible()))
		phy = line_card(page, "Selina Concise Physics 9")
		ok("line 1: on the PO, 100% match", lambda: (expect(phy).to_contain_text("On the PO"), expect(phy).to_contain_text("100%")))
		page.screenshot(path=S + "shot_pp_check.png", full_page=True)
		check("check screen: no sideways scroll", no_sideways(page))

		mat = line_card(page, "Selina Mathematics 6")
		ok("line 3: 'doesn't add up' with a fix", lambda: expect(mat.get_by_role("button", name="Make it 9")).to_be_visible())
		mat.get_by_role("button", name="Make it 9").click()
		ok("line 3 fixed → qty 9", lambda: expect(mat.get_by_role("button", name="Make it 9")).to_have_count(0, timeout=10000))
		che = line_card(page, "Selina Concise Chemistry 10")
		ok("line 2: over-delivery card (60 against 40 due)", lambda: expect(che.get_by_role("button", name="Keep 60")).to_be_visible())
		che.get_by_role("button", name="Keep 60").click()
		page.wait_for_timeout(800)
		reg = line_card(page, "Classmate Register")
		ok("line 4: not on the PO", lambda: expect(reg).to_contain_text("Not on the linked PO"))
		if reg.get_by_role("button", name="Correct").count():
			reg.get_by_role("button", name="Correct").click()
			page.wait_for_timeout(800)
		atl = line_card(page, "Selina Atlas Junior")
		if atl.get_by_role("button", name="Leave out").count():
			atl.get_by_role("button", name="Leave out").click()
			page.wait_for_timeout(800)
		ok("all fixed → red bar gone", lambda: expect(page.get_by_role("alert")).to_have_count(0, timeout=10000))
		ok("totals line: adds up", lambda: expect(page.get_by_text(re.compile(r"✓ (Lines add up|Adds up)"))).to_be_visible())
		ok("Next enabled", lambda: expect(nxt).to_be_enabled(timeout=10000))
		page.screenshot(path=S + "shot_pp_fixed.png", full_page=True)
		nxt.click()
		ok("save screen: GST from the ERP", lambda: expect(page.get_by_text(re.compile("GST"))).to_be_visible(timeout=20000))
		ok("save screen: Submit now", lambda: expect(page.get_by_role("button", name="Submit now")).to_be_enabled(timeout=20000))
		page.screenshot(path=S + "shot_pp_save.png", full_page=True)
		check("save screen: no sideways scroll", no_sideways(page))
		page.get_by_role("button", name="Submit now").click()
		ok("Receipt submitted", lambda: expect(page.get_by_text("Receipt submitted")).to_be_visible(timeout=60000))
		pr_doc = page.locator("p", has_text=re.compile(r"^MAT-PRE-|^PR-|^MAT-")).first.inner_text().split("·")[0].strip()
		ok("saved screen: Make the bill now", lambda: expect(page.get_by_role("button", name="Make the bill now")).to_be_visible())
		page.screenshot(path=S + "shot_pp_saved.png", full_page=True)
		check("saved screen: no sideways scroll", no_sideways(page))
		got = bench_py(f"""
d = frappe.get_doc("Purchase Receipt", {pr_doc!r})
print(json.dumps({{"docstatus": d.docstatus, "supplier": d.supplier, "dn": d.supplier_delivery_note,
	"rows": sorted([i.item_code, i.qty, round(i.rate, 2), i.purchase_order or ""] for i in d.items),
	"tax": d.taxes_and_charges, "files": frappe.db.count("File", {{"attached_to_doctype": "Purchase Receipt", "attached_to_name": d.name}})}}))
""")
		rows = {r[0]: r[1:] for r in got["rows"]}
		check("PR: submitted, supplier, bill no", got["docstatus"] == 1 and got["supplier"] == SEL and got["dn"] == BILL_NO, got)
		check("PR: net rates, PO linked", rows.get("BK-PHY9") == [50, 484.4, PO] and rows.get("BK-CHE10") == [60, 350, PO]
			and rows.get("BK-MAT6") == [9, 240, PO] and rows.get("ST-REG") == [10, 40, ""], rows)
		check("PR: 4 rows, atlas left out", len(rows) == 4, rows)
		check("PR: in-state GST template, paper attached", got["tax"] == "Input GST In-state - KGS" and got["files"] >= 1, got)

		# ── 2. the Bill from the same reading ────────────────────────────────
		page.get_by_role("button", name="Make the bill now").click()
		ok("bill paper opens at the check screen (no second reading)", lambda: expect(page.get_by_text("Bill from paper", exact=True)).to_be_visible(timeout=20000))
		pi_paper = page.url.rsplit("/", 1)[1]
		check("bill is a new paper", pi_paper != pr_paper, pi_paper)
		ok("bill linked to the Receipt", lambda: expect(page.locator("section", has_text="Linked to").get_by_text(pr_doc)).to_be_visible())
		ok("bill: atlas still to decide (a bill must carry every line)", lambda: expect(page.get_by_role("alert")).to_contain_text("left out"))
		page.screenshot(path=S + "shot_pi_check.png", full_page=True)
		check("bill check screen: no sideways scroll", no_sideways(page))
		got_ai = bench_py(f"print(json.dumps(frappe.db.get_value('Order Paper', {pi_paper!r}, ['source_paper', 'ai_input_tokens'], as_dict=True)))")
		check("bill paper points at the Receipt paper, no AI call", (got_ai or {}).get("source_paper") == pr_paper and not (got_ai or {}).get("ai_input_tokens"), got_ai)
		check("no JS errors / failed requests so far", not [e for e in errors if "favicon" not in e], errors[:5])
		ctx.close()

		# ── 3. the owner's settings ──────────────────────────────────────────
		ctx = browser.new_context(**PHONE)
		page = ctx.new_page()
		errors = []
		page.on("pageerror", lambda e: errors.append(str(e)))
		page.on("response", lambda r: errors.append(f"{r.status} {r.url}") if r.status >= 400 else None)
		login(page, OWNER)
		page.get_by_role("navigation", name="Main").get_by_role("link", name="More").click()
		ok("owner: Settings row on More", lambda: expect(page.get_by_role("link", name=re.compile(r"^Settings"))).to_be_visible(timeout=15000))
		page.goto(f"{BASE}/staff/settings")
		ok("settings: Receipts and Bills section", lambda: expect(page.get_by_text("Receipts and Bills from paper")).to_be_visible(timeout=15000))
		ok("settings: Dolly on the list", lambda: expect(page.get_by_text(DOLLY)).to_be_visible())
		ok("settings: freight account chosen", lambda: expect(page.locator("select", has=page.locator(f"option[value='{FREIGHT}']"))).to_have_value(FREIGHT))
		page.fill("input[aria-label='Add a person']", "pp_other")
		hit = page.get_by_role("button", name=re.compile("pp_other@example.com"))
		ok("settings: search a Purchase User to add", lambda: expect(hit).to_be_visible(timeout=10000))
		page.screenshot(path=S + "shot_pp_settings.png", full_page=True)
		check("settings: no sideways scroll", no_sideways(page))
		check("no JS errors / failed requests (owner)", not [e for e in errors if "favicon" not in e], errors[:5])
		ctx.close()
		browser.close()
finally:
	bench_py("""
from frappe.installer import update_site_config
update_site_config("kgs_paper_ai_fake", "None")
import json as j
c = j.load(open(frappe.get_site_path("site_config.json")))
c.pop("kgs_paper_ai_fake", None)
open(frappe.get_site_path("site_config.json"), "w").write(j.dumps(c, indent=1, sort_keys=True))
print(1)
""")
	if os.path.exists(SPEC):
		os.remove(SPEC)

n_ok = sum(1 for _, x in RESULTS if x)
print(f"\n{n_ok}/{len(RESULTS)} passed")
raise SystemExit(0 if n_ok == len(RESULTS) else 1)
