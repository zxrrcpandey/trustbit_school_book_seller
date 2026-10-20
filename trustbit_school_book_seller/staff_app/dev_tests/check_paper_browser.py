"""Headless phone-size test of Order from Paper in the /staff PWA (http://127.0.0.1:8001, site1.local).
Needs: `bench --site site1.local serve --port 8001` and `bench worker --queue default,short`, and
check_paper_api.py run once before (it makes the KGS-PT-* items, "Paper Test Agency", "PT RDPS 3"
and the paper_* users). Run with a Python that has playwright:
    <venv>/bin/python check_paper_browser.py
The AI is the fake provider: this script points site_config "kgs_paper_ai_fake" at a JSON file it
writes, and removes the key again at the end (also on failure)."""
import json
import os
import re
import subprocess
import time

from playwright.sync_api import expect, sync_playwright

S = os.path.dirname(os.path.abspath(__file__)) + "/"
BENCH = os.path.abspath(S + "../../../../..") + "/"  # frappe-bench/
BASE = "http://127.0.0.1:8001"
EXE = "/Users/warroom/Library/Caches/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-mac-arm64/chrome-headless-shell"
PW = "Kgs-Test-2026!x"
SUP, CUST = "Paper Test Agency", "PT RDPS 3"
PRINTED = "PAPER TEST AGENCY, BETUL (M.P.)"
SPEC = S + "paper_fake_reading.json"
SAMPLE = S + "paper_sample.jpg"
PHONE = dict(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
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
	"""Run code in the bench's Python with frappe connected to site1.local; returns stdout's last line as JSON."""
	pre = "import frappe, json\nfrappe.init(site='site1.local', sites_path='.')\nfrappe.connect()\n"
	r = subprocess.run([BENCH + "env/bin/python", "-c", pre + code], cwd=BENCH + "sites", capture_output=True, text=True, timeout=120)
	if r.returncode:
		raise RuntimeError(r.stderr[-800:])
	out = [ln for ln in r.stdout.splitlines() if ln.strip()]
	return json.loads(out[-1]) if out else None


def write_spec(reading):
	with open(SPEC, "w") as f:
		json.dump({"reading": reading, "rerank": {"choices": []}}, f)


PO_READING = {
	"paper_kind": "quotation", "party_name": PRINTED, "paper_no": "PT-B-" + time.strftime("%H%M%S"),
	"discount_note": "25% on MRP",
	"lines": [
		{"text": "Sunshine Eng. Reader Class III", "qty": 12, "mrp": 250, "discount_percent": 25},
		{"text": "Maths Maniya Golden Maple-3", "qty": 8, "mrp": 275, "discount_percent": 25},
		{"text": "Reynolds pen blue", "code": "KGS-PT-PEN", "qty": 3, "unit": "Pkt", "rate": 80},
		{"text": "Koncept Intellect G.K. book five", "qty": 4},
		{"text": "Mystery gadget qqx", "qty": 2, "rate": 40},
	],
}
# the same paper again, now with list rates and a final total that is lower (a
# discount the AI did not put in the rates) → the save screen must warn
PO_READING2 = dict(PO_READING, grand_total=4800, lines=[
	{"text": "Sunshine Eng. Reader Class III", "qty": 12, "rate": 250},
	{"text": "Maths Maniya Golden Maple-3", "qty": 8, "rate": 275},
	{"text": "Reynolds pen blue", "code": "KGS-PT-PEN", "qty": 3, "unit": "Pkt", "rate": 80},
	{"text": "Koncept Intellect G.K. book five", "qty": 4, "rate": 199},
	{"text": "Mystery gadget qqx", "qty": 2, "rate": 40},
])
SO_READING = {"paper_kind": "school_book_list", "school_or_class": "R.D. Public School — Class III",
	"lines": [{"text": "Sunshine English Reader 3"}, {"text": "Golden Maple Maths Maniya 3"}]}

# ── setup (bench side) ───────────────────────────────────────────────────────
bench_py(f"""
from PIL import Image, ImageDraw
img = Image.new("RGB", (1240, 1754), "white")
d = ImageDraw.Draw(img)
for i, t in enumerate(["QUOTATION", {PRINTED!r}] + [ln["text"] for ln in {PO_READING["lines"]!r}]):
	d.text((80, 80 + i * 60), t, fill="black")
img.save({SAMPLE!r}, "JPEG", quality=85)
s = frappe.get_doc("Order Paper Settings")
s.enabled, s.so_enabled, s.ai_model, s.rerank, s.auto_fallback, s.month_page_limit, s.peak_month_page_limit = 1, 1, "claude-haiku-5-5", 1, 1, 0, 0
s.save(ignore_permissions=True)
frappe.db.delete("Party Item Alias", {{"party": ["in", [{SUP!r}, {CUST!r}]]}})
frappe.db.sql("update `tabOrder Paper` set status = 'Discarded' where status not in ('Saved', 'Discarded')")
frappe.db.sql("update `tabOrder Paper` set paper_party_text = concat('old-', name) where paper_party_text = %s", {PRINTED!r})
frappe.cache.delete_keys("kgs_staff_rl:")
frappe.db.commit()
from frappe.installer import update_site_config
update_site_config("kgs_paper_ai_fake", {SPEC!r})
print(json.dumps(1))
""")
write_spec(PO_READING)


def login(page, email):
	page.goto(f"{BASE}/staff/login")
	page.fill("input[type=email]", email)
	page.fill("input[type=password]", PW)
	page.click("button[type=submit]")


def no_sideways(page):
	return page.evaluate("document.documentElement.scrollWidth") <= 390


def line_card(page, text):
	return page.locator("article", has_text=text)


try:
	with sync_playwright() as p:
		browser = p.chromium.launch(executable_path=EXE)

		# ── 1. Purchase User: paper → PO sent for approval ───────────────────
		ctx = browser.new_context(**PHONE)
		page = ctx.new_page()
		errors = []
		page.on("pageerror", lambda e: errors.append(str(e)))
		page.on("response", lambda r: errors.append(f"{r.status} {r.url}") if r.status >= 400 else None)
		page.on("dialog", lambda d: d.accept())

		boots = []
		page.on("response", lambda r: boots.append(r) if r.url.endswith(".staff_app.api.boot") else None)
		login(page, "paper_po@example.com")
		ok("purchase user lands on home with the PO tile", lambda: expect(page.get_by_text("Purchase Order from paper")).to_be_visible(timeout=15000))
		ready = boots[-1].json()["message"]["paper"]["ready"] if boots else None
		check("boot: AI ready (fake reading in test mode)", ready == 1, f"ready={ready}, boots={len(boots)}")
		check("no transfer tile for a purchase-only user", page.get_by_text("New transfer").count() == 0 and page.get_by_text("Recent transfers").count() == 0)
		check("no Settings link for a purchase user", page.get_by_role("link", name="Settings").count() == 0)
		page.screenshot(path=S + "shot_paper_home.png")

		page.get_by_text("Purchase Order from paper").click()
		ok("new paper screen", lambda: expect(page.get_by_text("Purchase Order from a paper")).to_be_visible())
		page.locator("input[type=file][multiple]").set_input_files(SAMPLE)
		ok("photo added as page 1", lambda: expect(page.get_by_text("Pages added (1)")).to_be_visible(timeout=10000))
		check("new paper: no sideways scroll", no_sideways(page))
		page.screenshot(path=S + "shot_paper_new.png")
		page.get_by_role("button", name="Read the paper (1 page)").click()
		ok("upload → paper page", lambda: expect(page).to_have_url(re.compile(r"/staff/paper/OP-\d{4}-\d+$"), timeout=20000))
		po_paper = page.url.rsplit("/", 1)[1]
		ok("read by the worker → check screen", lambda: expect(page.get_by_text("Check the lines")).to_be_visible(timeout=60000))
		ok("supplier not sure → 'Choose the supplier'", lambda: expect(page.get_by_text("Choose the supplier", exact=True)).to_be_visible())
		ok("'Next' blocked until the supplier is chosen", lambda: expect(page.get_by_text("Choose the supplier first")).to_be_visible())
		page.screenshot(path=S + "shot_paper_check.png", full_page=True)
		check("check screen: no sideways scroll", no_sideways(page))

		page.get_by_role("button", name="Choose", exact=True).click()
		ok("party sheet shows the printed name", lambda: expect(page.get_by_text(PRINTED, exact=True)).to_be_visible())
		page.get_by_role("button", name=re.compile(r"^" + SUP)).first.click()
		ok("supplier chosen", lambda: expect(page.get_by_text("Chosen by you")).to_be_visible(timeout=10000))

		ok("our code on the paper → Sure", lambda: expect(line_card(page, "Reynolds pen blue").get_by_text("Sure")).to_be_visible())
		ok("pen: unit PKT from the paper", lambda: expect(line_card(page, "Reynolds pen blue").locator("select")).to_have_value("PKT"))
		ok("unknown gadget → Not found", lambda: expect(line_card(page, "Mystery gadget").get_by_text("Not found")).to_be_visible())
		eng = line_card(page, "Sunshine Eng. Reader")
		ok("fuzzy line → To check, class 3 item offered", lambda: (expect(eng.get_by_text("To check")).to_be_visible(),
			expect(eng.get_by_text("KGS-PT-ENG3")).to_be_visible()))
		eng.get_by_role("button", name="Correct").click()
		ok("Correct → Confirmed", lambda: expect(eng.get_by_text("Confirmed")).to_be_visible(timeout=10000))

		mm = line_card(page, "Maths Maniya Golden Maple-3")
		ok("twin by MRP: the 275 edition offered", lambda: expect(mm.get_by_text("KGS-PT-MM3-NEW")).to_be_visible())
		mm.get_by_role("button", name="Change").click()
		ok("choose sheet lists both editions", lambda: (expect(page.get_by_text("Best matches")).to_be_visible(),
			expect(page.get_by_text("KGS-PT-MM3-OLD")).to_be_visible()))
		page.screenshot(path=S + "shot_paper_choose.png")
		page.get_by_role("button", name=re.compile("Maniya 3 240")).click()
		page.get_by_role("button", name="Use this item").click()
		ok("changed to the 240 edition, confirmed", lambda: (expect(mm.get_by_text("KGS-PT-MM3-OLD")).to_be_visible(timeout=10000),
			expect(mm.get_by_text("Confirmed")).to_be_visible()))

		gk = line_card(page, "Koncept Intellect")
		if gk.get_by_role("button", name="Correct").count():
			gk.get_by_role("button", name="Change").click()
		else:
			gk.get_by_role("button", name=re.compile("Choose the item|Search items")).click()
		page.fill("#item-search", "koncept intellect")
		found = page.locator("section", has=page.locator("#item-search")).get_by_role("button", name=re.compile("Koncept Global Intellect GK 5"))
		ok("search finds the GK book", lambda: expect(found).to_be_visible(timeout=10000))
		found.click()
		page.get_by_role("button", name="Use this item").click()
		ok("searched item set", lambda: expect(gk.get_by_text("KGS-PT-GK5")).to_be_visible(timeout=10000))

		q = page.locator("#q1")
		q.fill("15")
		q.dispatch_event("change")
		page.wait_for_timeout(1200)
		nxt = page.get_by_role("button", name="Next: make the Purchase Order")
		ok("all checked → Next enabled", lambda: expect(nxt).to_be_enabled(timeout=10000))
		nxt.click()
		ok("save screen: deliver to + rates", lambda: (expect(page.get_by_text("Deliver to")).to_be_visible(),
			expect(page.get_by_text("The paper's rates (25% on MRP)")).to_be_visible()))
		ok("save screen lists the left-out line", lambda: expect(page.get_by_text(re.compile(r"Left out \(1\)"))).to_be_visible())
		page.screenshot(path=S + "shot_paper_save.png", full_page=True)
		page.get_by_role("button", name="Save and send for approval").click()
		ok("PO sent for approval", lambda: expect(page.get_by_text("Purchase Order sent for approval")).to_be_visible(timeout=60000))
		ok("done screen: approvers e-mailed, never 'It is a draft'", lambda: (expect(page.get_by_text(re.compile("got the approval email"))).to_be_visible(),
			expect(page.get_by_text(re.compile("It is a draft"))).to_have_count(0)))
		po = page.locator("dd", has_text=re.compile(r"^PUR-ORD-")).inner_text().strip()
		ok("done screen: still-to-do for the left-out line", lambda: expect(page.get_by_text(re.compile("1 line was left out"))).to_be_visible())
		page.screenshot(path=S + "shot_paper_done.png", full_page=True)
		check("done screen: no sideways scroll", no_sideways(page))

		got = None
		for _ in range(30):
			got = bench_py(f"""
po = frappe.get_doc("Purchase Order", {po!r})
mails = frappe.get_all("Email Queue", filters={{"reference_doctype": "Purchase Order", "reference_name": {po!r}}}, pluck="name")
rcpt = frappe.get_all("Email Queue Recipient", filters={{"parent": ["in", mails or [""]]}}, pluck="recipient")
print(json.dumps({{"state": po.workflow_state, "owner": po.owner, "remark": po.custom_remark or "",
	"lines": sorted([i.item_code, i.qty, i.uom, i.rate] for i in po.items), "rcpt": rcpt,
	"files": frappe.db.count("File", {{"attached_to_doctype": "Purchase Order", "attached_to_name": {po!r}}}),
	"aliases": frappe.db.count("Party Item Alias", {{"party": {SUP!r}}}),
	"pdf_tool_broken": frappe.db.count("Error Log", {{"method": ["like", "%send_workflow_action_email"],
		"error": ["like", "%wkhtmltopdf%"], "creation": [">=", po.creation]}})}}))
""")
			if got["rcpt"] or got["pdf_tool_broken"]:
				break
			time.sleep(1)
		check("PO pending approval, made by the clerk", got["state"] == "Pending Approval" and got["owner"] == "paper_po@example.com", got)
		ln = {r[0]: r[1:] for r in got["lines"]}
		check("PO lines: 4, gadget left out", sorted(ln) == ["KGS-PT-ENG3", "KGS-PT-GK5", "KGS-PT-MM3-OLD", "KGS-PT-PEN"], got["lines"])
		check("PO: person's qty 15, paper rate MRP − 25%", ln.get("KGS-PT-ENG3") == [15, "PCS", 187.5], ln)
		check("PO: changed to the 240 edition at the paper's rate", ln.get("KGS-PT-MM3-OLD") == [8, "PCS", 206.25], ln)
		check("PO: pen 3 PKT at the printed 80", ln.get("KGS-PT-PEN") == [3, "PKT", 80], ln)
		check("PO: searched GK book, qty 4", (ln.get("KGS-PT-GK5") or [0])[0] == 4, ln)
		check("remark names the left-out gadget", "Mystery gadget qqx" in got["remark"], got["remark"])
		check("photo attached to the PO", got["files"] == 1)
		if got["rcpt"] or not got["pdf_tool_broken"]:
			check("the owner got the approval e-mail (worker ran it)", "paper_owner@example.com" in got["rcpt"], got)
		else:  # frappe attaches the PO PDF; this Mac's wkhtmltopdf cannot run (Bad CPU type) — production's can
			print("NOTE approval e-mail job ran but stopped at wkhtmltopdf on this machine — e-mail not provable here", flush=True)
			check("approval e-mail job ran on the worker (stopped at this machine's wkhtmltopdf)", True)
		check("4 names remembered for the supplier", got["aliases"] >= 4, got["aliases"])

		# ── 2. same paper again: remembered → Sure, supplier same as last time ─
		write_spec(PO_READING2)
		page.get_by_role("link", name="Read another paper").click()
		page.locator("input[type=file][multiple]").set_input_files(SAMPLE)
		page.get_by_role("button", name="Read the paper (1 page)").click()
		ok("2nd paper read", lambda: expect(page.get_by_text("Check the lines")).to_be_visible(timeout=60000))
		ok("2nd paper: supplier same as last time", lambda: expect(page.get_by_text(re.compile("Same as last time for"))).to_be_visible())
		ok("2nd paper: remembered lines Sure", lambda: (expect(line_card(page, "Sunshine Eng. Reader").get_by_text("Remembered from an earlier paper")).to_be_visible(),
			expect(line_card(page, "Maths Maniya Golden Maple-3").get_by_text("KGS-PT-MM3-OLD")).to_be_visible()))
		ok("2nd paper: duplicate paper number warned", lambda: expect(page.get_by_text("Already used?")).to_be_visible())
		page.screenshot(path=S + "shot_paper_second.png", full_page=True)
		page.get_by_role("button", name="Next: make the Purchase Order").click()
		ok("2nd paper: save screen warns the rates miss the paper's final total", lambda: expect(
			page.get_by_text(re.compile(r"come to ₹6,316\.00, but the paper's final total is only ₹4,800\.00 \(it says \"25% on MRP\"\)"))).to_be_visible(timeout=10000))
		page.screenshot(path=S + "shot_paper_rate_warning.png", full_page=True)
		page.get_by_text("Back", exact=True).click()
		page.get_by_role("button", name="Discard this paper").click()
		ok("discarded", lambda: expect(page.get_by_text("This paper was discarded")).to_be_visible(timeout=10000))

		page.goto(f"{BASE}/staff/papers")
		ok("papers list shows the saved paper and its PO", lambda: expect(page.locator("a", has_text=po_paper).get_by_text(po)).to_be_visible(timeout=10000))
		check("no JS errors / failed requests (purchase user)", not [e for e in errors if "favicon" not in e], errors[:5])
		ctx.close()

		# ── 3. Sales Order from a school list (copies) ──────────────────────
		write_spec(SO_READING)
		ctx = browser.new_context(**PHONE)
		page = ctx.new_page()
		errors = []
		page.on("pageerror", lambda e: errors.append(str(e)))
		page.on("response", lambda r: errors.append(f"{r.status} {r.url}") if r.status >= 400 else None)
		page.on("dialog", lambda d: d.accept())
		login(page, "paper_so@example.com")
		ok("sales user: SO tile", lambda: expect(page.get_by_text("Sales Order from paper")).to_be_visible(timeout=15000))
		page.get_by_text("Sales Order from paper").click()
		page.fill("#copies", "30")
		page.locator("input[type=file][multiple]").set_input_files(SAMPLE)
		page.get_by_role("button", name="Read the paper (1 page)").click()
		ok("SO paper read", lambda: expect(page.get_by_text("Check the lines · Sales Order")).to_be_visible(timeout=60000))
		ok("SO: every line 30 copies", lambda: (expect(page.locator("#q1")).to_have_value("30"), expect(page.locator("#q2")).to_have_value("30")))
		page.get_by_role("button", name="Choose", exact=True).click()
		page.get_by_role("searchbox").fill("PT RDPS")
		page.get_by_role("button", name=re.compile(r"^" + CUST)).first.click()
		ok("customer chosen", lambda: expect(page.get_by_text("Chosen by you")).to_be_visible(timeout=10000))
		for _ in range(10):
			if not page.get_by_role("button", name="Correct").count():
				break
			page.get_by_role("button", name="Correct").first.click()
			page.wait_for_timeout(700)
		page.get_by_role("button", name="One copy more").click()
		ok("copies + 1 → 31 on every line", lambda: (expect(page.locator("#q1")).to_have_value("31", timeout=10000),
			expect(page.locator("#q2")).to_have_value("31")))
		page.screenshot(path=S + "shot_paper_so_check.png", full_page=True)
		page.get_by_role("button", name="Next: make the Sales Order").click()
		page.get_by_role("button", name="Save the Sales Order (draft)").click()
		ok("SO saved as a draft", lambda: expect(page.get_by_text("Sales Order saved as a draft")).to_be_visible(timeout=60000))
		so = page.locator("dd", has_text=re.compile(r"^SAL-ORD-")).inner_text().strip()
		got = bench_py(f"""
so = frappe.get_doc("Sales Order", {so!r})
print(json.dumps({{"customer": so.customer, "docstatus": so.docstatus, "lines": sorted([i.item_code, i.qty, i.rate] for i in so.items)}}))
""")
		price = {"KGS-PT-ENG3": 250, "KGS-PT-MM3-OLD": 240, "KGS-PT-MM3-NEW": 275}
		check("SO: customer, draft, 2 lines × 31 at our selling price", got["customer"] == CUST and got["docstatus"] == 0
			and len(got["lines"]) == 2 and got["lines"][0][0] == "KGS-PT-ENG3"
			and all(q == 31 and r == price.get(c) for c, q, r in got["lines"]), got)
		check("no JS errors / failed requests (sales user)", not [e for e in errors if "favicon" not in e], errors[:5])
		ctx.close()

		# ── 4. Shop Owner: settings + remembered names ───────────────────────
		ctx = browser.new_context(**PHONE)
		page = ctx.new_page()
		errors = []
		page.on("pageerror", lambda e: errors.append(str(e)))
		page.on("response", lambda r: errors.append(f"{r.status} {r.url}") if r.status >= 400 else None)
		login(page, "paper_owner@example.com")
		ok("owner: Settings link", lambda: expect(page.get_by_role("link", name="Settings")).to_be_visible(timeout=15000))
		page.get_by_role("link", name="Settings").click()
		ok("settings: OpenAI + Gemini 'Coming soon'", lambda: (expect(page.get_by_text("OpenAI (ChatGPT)")).to_be_visible(),
			expect(page.get_by_text("Coming soon")).to_have_count(2)))
		ok("settings: test-mode note (no key)", lambda: expect(page.get_by_text(re.compile("Test mode"))).to_be_visible())
		ok("settings: Haiku in use", lambda: expect(page.get_by_role("button", name=re.compile("Claude Haiku 5.5"))).to_have_attribute("aria-pressed", "true"))
		page.screenshot(path=S + "shot_paper_settings.png", full_page=True)
		check("settings: no sideways scroll", no_sideways(page))
		page.get_by_role("button", name=re.compile("Claude Sonnet 5.5")).click()
		page.get_by_role("button", name="Save settings").click()
		ok("settings saved", lambda: expect(page.get_by_text("Saved. The next paper uses these settings.")).to_be_visible(timeout=10000))
		page.reload()
		ok("after reload: Sonnet in use", lambda: expect(page.get_by_role("button", name=re.compile("Claude Sonnet 5.5"))).to_have_attribute("aria-pressed", "true", timeout=10000))
		check("server has Sonnet", bench_py('print(json.dumps(frappe.db.get_single_value("Order Paper Settings", "ai_model")))') == "claude-sonnet-5-5")
		page.get_by_role("button", name=re.compile("Claude Haiku 5.5")).click()
		page.get_by_role("button", name="Save settings").click()
		ok("back to Haiku", lambda: expect(page.get_by_text("Saved. The next paper uses these settings.")).to_be_visible(timeout=10000))

		page.goto(f"{BASE}/staff/names")
		ok("names: the supplier is listed", lambda: expect(page.get_by_role("button", name=re.compile(SUP))).to_be_visible(timeout=10000))
		page.get_by_role("button", name=re.compile(SUP)).click()
		ok("names: wording → item shown", lambda: expect(page.get_by_text("Sunshine Eng. Reader Class III")).to_be_visible(timeout=10000))
		check("owner (no Purchase Manager role) cannot delete names", page.get_by_role("button", name="Delete").count() == 0)
		page.screenshot(path=S + "shot_paper_names.png", full_page=True)
		check("no JS errors / failed requests (owner)", not [e for e in errors if "favicon" not in e], errors[:5])
		ctx.close()
		browser.close()
finally:
	bench_py("""
from frappe.installer import update_site_config
update_site_config("kgs_paper_ai_fake", "None")
s = frappe.get_doc("Order Paper Settings")
s.ai_model, s.so_enabled = "claude-haiku-5-5", 0
s.save(ignore_permissions=True)
frappe.db.commit()
print(json.dumps(1))
""")
	for f in (SPEC,):
		if os.path.exists(f):
			os.remove(f)

passed = sum(1 for _n, r in RESULTS if r)
print(f"\n{passed}/{len(RESULTS)} passed")
