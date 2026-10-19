"""Server-side tests for Order from Paper (staff_app/paper.py, paper_read.py,
paper_match.py) on site1.local. Run from frappe-bench/sites:
    ../env/bin/python ../apps/trustbit_school_book_seller/trustbit_school_book_seller/staff_app/dev_tests/check_paper_api.py
No AI is called: readings come from the fake provider (in-process site_config),
and the real Anthropic code path is driven against a local mock HTTP server.
Read jobs run synchronously in this process (the enqueue is captured).
Creates test masters prefixed KGS-PT / "Paper Test"; restores the settings it touches."""
import base64
import io
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

import frappe
from frappe.utils import add_days, flt, nowdate

frappe.init(site="site1.local", sites_path=".")
frappe.connect()

from trustbit_school_book_seller.staff_app import api, paper  # noqa: E402
from trustbit_school_book_seller.staff_app import paper_match as pm  # noqa: E402
from trustbit_school_book_seller.staff_app import paper_read as pr  # noqa: E402

RESULTS = []
COMPANY = "Development Company V1.0"
PW = "Kgs-Test-2026!x"


def check(name, cond, detail=""):
	RESULTS.append((name, bool(cond), detail))
	print(("PASS " if cond else "FAIL ") + name + (f" — {detail}" if detail and not cond else ""))


def raises(fn, exc=Exception):
	try:
		fn()
	except exc as e:
		frappe.db.rollback()
		return str(e) or type(e).__name__
	except Exception as e:
		frappe.db.rollback()
		return f"WRONG {type(e).__name__}: {e}"
	return None


def ref():
	return str(uuid.uuid4())


def rl_key(u, window=None):
	import time

	return frappe.cache.make_key(f"kgs_staff_rl:{u}:{window if window is not None else int(time.time() // 60)}")


def as_user(u):
	import time

	frappe.set_user(u)
	frappe.local.request_ip = "127.0.0.1"
	w = int(time.time() // 60)
	frappe.cache.delete(rl_key(u, w), rl_key(u, w - 1))  # back-to-back runs share the minute


# ── unit: normalising, classes, codes, units ─────────────────────────────────
check("class: CLASS III → 3", pm.class_of("MATHEMATICS CLASS III") == "3")
check("class: Std. 5th → 5", pm.class_of("G.K. Std. 5th") == "5")
check("class: trailing number (KGS names)", pm.class_of("Golden Maple Maths Maniya 4") == "4")
check("class: price not a class", pm.class_of("Oswaal Ques Bank History 11 249/-") == "11")
check("class: 6 Qr register is no class", pm.class_of("Sbs Poniya Register 6 Qr 150/-") is None)
check("class: PART II is no class", pm.class_of("Hindi Vyakaran Part-II") is None)
check("class: 4.0 version is no class", pm.class_of("Touch Pad Modular 4.0") is None)
check("class: Kg-II → UKG, Nursery → NUR", pm.class_of("Kg-II Writing book") == "UKG" and pm.class_of("Nursery rhymes") == "NUR")
check("item class: field '3', '.', range, semester", pm.item_class("3", "x") == "3" and pm.item_class(".", "Guide 9 140/-") == "9"
	and pm.item_class("11 & 12", "x 12") is None and pm.item_class("3-1", "") == "3")
check("key: short forms meet", pm.match_key("MATHS CLASS III") == pm.match_key("Mathematics Class 3"))
check("key: G.K. = GK, price dropped", pm.match_key("Koncept G.K. 6 250/-") == pm.match_key("KONCEPT GK 6"))
check("key: class 4 ≠ class 5", pm.match_key("Moral Value-4") != pm.match_key("Moral Value-5"))
check("code key: punctuation-blind", pm.code_key("ab-12/3") == pm.code_key("AB 123") == "AB123")
check("isbn: 10 → 13 and back", "9788174504944" in pm.isbn_variants("81-7450-494-X") and "817450494X" in pm.isbn_variants("978-81-7450-494-4"))
check("units: pkt/Boxes/doz/copies", [pm.canonical_unit(u) for u in ("Pkt.", "Boxes", "doz", "copies")] == ["PKT", "BOX", "DOZEN", "PCS"])
r = pr.clean_reading({"paper_kind": "weird", "party_gstin": "23aaaaa0000a1z5", "lines": [
	{"text": "  A   book ", "qty": "1,250.50", "mrp": "₹ 300", "discount_percent": 150, "unclear": "yes"},
	{"text": "", "code": ""}, "junk", {"text": "x" * 500, "qty": -3}]})
check("clean: kind, gstin, numbers, caps", r["paper_kind"] == "other" and r["party_gstin"] == "23AAAAA0000A1Z5"
	and r["lines"][0]["qty"] == 1250.5 and r["lines"][0]["mrp"] == 300 and r["lines"][0]["discount_percent"] is None
	and r["lines"][0]["unclear"] == 0 and len(r["lines"]) == 2 and len(r["lines"][1]["text"]) == 200 and r["lines"][1]["qty"] is None)
check("rate: printed / amount÷qty / MRP−discount", pr.paper_rate({"rate": 90}) == 90 and pr.paper_rate({"amount": 500, "qty": 4}) == 125
	and pr.paper_rate({"mrp": 200, "discount_percent": 25}) == 150 and pr.paper_rate({"mrp": 200}) is None)
check("looks wrong: total mismatch / 2 unclear / fine",
	"add up" in pr.looks_wrong({"items_total": 1000, "lines": [{"rate": 10, "qty": 5}]})
	and "hard to read" in pr.looks_wrong({"lines": [{"unclear": 1}, {"unclear": 1}]})
	and pr.looks_wrong({"items_total": 50, "lines": [{"rate": 10, "qty": 5}]}) == "")

# ── setup ────────────────────────────────────────────────────────────────────
frappe.set_user("Administrator")
SETTINGS_BEFORE = frappe.get_doc("Order Paper Settings").as_dict()


def settings(**kw):
	s = frappe.get_doc("Order Paper Settings")
	s.update(kw)
	s.save(ignore_permissions=True)
	frappe.db.commit()


settings(enabled=1, so_enabled=0, ai_model="claude-haiku-5-5", fallback_model="claude-sonnet-5-5", auto_fallback=1, rerank=1,
	month_page_limit=0, peak_month_page_limit=0)


def make_user(email, roles):
	if not frappe.db.exists("User", email):
		u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0,
			"new_password": PW})
		u.insert(ignore_permissions=True)
	u = frappe.get_doc("User", email)
	u.set("roles", [])
	for r_ in roles:
		u.append("roles", {"role": r_})
	u.save(ignore_permissions=True)


PO_USER, PO_MGR, SO_USER, STOCK_ONLY, OWNER = ("paper_po@example.com", "paper_pm@example.com", "paper_so@example.com",
	"paper_stock@example.com", "paper_owner@example.com")
make_user(PO_USER, ["Purchase User"])
make_user(PO_MGR, ["Purchase User", "Purchase Manager"])
make_user(SO_USER, ["Sales User", "Sales Manager"])
make_user(STOCK_ONLY, ["Stock User"])
make_user(OWNER, ["Shop Owner", "Purchase User"])
SM_ONLY = "paper_sm@example.com"
make_user(SM_ONLY, ["System Manager"])
for u in (PO_USER, PO_MGR, SO_USER, OWNER):
	frappe.defaults.set_user_default("Company", COMPANY, u)

for uom, whole in (("PCS", 0), ("PKT", 1)):
	if not frappe.db.exists("UOM", uom):
		frappe.get_doc({"doctype": "UOM", "uom_name": uom, "must_be_whole_number": whole}).insert()
PKT_WHOLE_BEFORE = frappe.db.get_value("UOM", "PKT", "must_be_whole_number")
frappe.db.set_value("UOM", "PKT", "must_be_whole_number", 1)


def make_item(code, name, cls=None, price=None, uoms=(), barcodes=(), isbn=None, disabled=0):
	if not frappe.db.exists("Item", code):
		d = frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": name, "item_group": "All Item Groups",
			"stock_uom": "PCS", "is_stock_item": 1,
			"uoms": [{"uom": "PCS", "conversion_factor": 1}] + [{"uom": u, "conversion_factor": f} for u, f in uoms],
			"barcodes": [{"barcode": b} for b in barcodes]})
		if isbn:
			d.custom_isbn_barcode = isbn
		if cls:
			d.custom_class = cls
		d.insert()
	frappe.db.set_value("Item", code, "disabled", disabled)
	if price and not frappe.db.exists("Item Price", {"item_code": code, "price_list": "Standard Selling"}):
		frappe.get_doc({"doctype": "Item Price", "item_code": code, "price_list": "Standard Selling", "price_list_rate": price}).insert()


make_item("KGS-PT-ENG3", "PTest Sunshine English Reader 3", cls="3", price=250)
make_item("KGS-PT-ENG4", "PTest Sunshine English Reader 4", cls="4", price=260)
make_item("KGS-PT-MM3-OLD", "PTest Golden Maple Maths Maniya 3 240/-", cls="3", price=240)
make_item("KGS-PT-MM3-NEW", "PTest Golden Maple Maths Maniya 3 275/-", cls="3", price=275)
make_item("KGS-PT-GK5", "PTest Koncept Global Intellect GK 5", cls="5", price=199, isbn="9789999000051")
make_item("KGS-PT-PEN", "PTest Reynolds Ball Pen Blue", uoms=[("PKT", 10)], price=10)
make_item("KGS-PT-DIS", "PTest Disabled Atlas", price=100, disabled=1)

SUP, SUP2 = "Paper Test Agency", "Paper Test Second Supplier"
for s in (SUP, SUP2):
	if not frappe.db.exists("Supplier", s):
		frappe.get_doc({"doctype": "Supplier", "supplier_name": s, "supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}, "name")}).insert()
CUST = "PT RDPS 3"
if not frappe.db.exists("Customer", CUST):
	frappe.get_doc({"doctype": "Customer", "customer_name": CUST, "customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
		"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name") or "All Territories"}).insert()
# fresh learning each run
frappe.db.delete("Party Item Alias", {"party": ["in", [SUP, SUP2, CUST]]})
frappe.db.sql("delete from `tabItem Supplier` where supplier in %s", ((SUP, SUP2),))
frappe.db.sql("update `tabOrder Paper` set status = 'Discarded' where status not in ('Saved', 'Discarded')")
frappe.db.sql("update `tabOrder Paper` set paper_no = concat('old-', name) where paper_no like 'PT-%%'")
frappe.db.sql("update `tabOrder Paper` set paper_party_text = concat('old-', name) where paper_party_text in %s", ((SUP, SUP2),))
frappe.db.commit()

ENQ = []
paper._enqueue_read = lambda name, model, reason: ENQ.append((name, model, reason))
CONF = frappe.local.conf
CONF.pop("kgs_paper_ai_key", None)
CONF.pop("kgs_paper_ai_url", None)


def fake(reading, rerank=None, by_model=None):
	spec = {"reading": reading, "rerank": rerank or {"choices": []}}
	if by_model:
		spec["by_model"] = by_model
	CONF["kgs_paper_ai_fake"] = spec


def jpeg(w=1200, h=1600, fmt="JPEG"):
	from PIL import Image

	b = io.BytesIO()
	Image.new("RGB", (w, h), "white").save(b, fmt)
	return base64.b64encode(b.getvalue()).decode()


def pdf(pages):
	from pypdf import PdfWriter

	w = PdfWriter()
	for _ in range(pages):
		w.add_blank_page(width=595, height=842)
	b = io.BytesIO()
	w.write(b)
	return base64.b64encode(b.getvalue()).decode()


def upload(purpose="Purchase Order", files=None, client_ref=None, copies=None):
	r_ = paper.upload_paper(purpose, json.dumps(files or [{"name": "p.jpg", "data": jpeg()}]), client_ref or ref(), copies)
	frappe.db.commit()
	return r_["name"]


def read(name, model=None, reason="first"):
	paper.run_read_job(name, model, reason)
	return paper.get_paper(name)


def line(p, idx):
	return next(ln for ln in p["lines"] if ln["idx"] == idx)


READING1 = {
	"paper_kind": "quotation", "party_name": SUP, "paper_no": "PT-Q-1", "paper_date": "01-01-2020",
	"discount_note": "Less 25% on MRP",
	"lines": [
		{"text": "SUNSHINE ENGLISH READER-3", "qty": 20, "unit": "PCS", "mrp": 250, "discount_percent": 25},
		{"text": "Golden Maple Maths Maniya 3", "qty": 10, "mrp": 275, "discount_percent": 25},
		{"text": "Koncept Global Intellect G.K.-5", "isbn": "978-9-99-900005-1", "qty": 5, "mrp": 199, "discount_percent": 25},
		{"text": "Reynolds pen blue", "code": "KGS-PT-PEN", "qty": 2, "unit": "Pkt", "rate": 80},
		{"text": "Totally unknown widget zzq", "qty": 3, "mrp": 50, "discount_percent": 25},
		{"text": "English Reader (Sunshine)", "class_hint": "4", "qty": 15, "mrp": 260, "discount_percent": 25, "code": "SUN-ENG-4"},
	],
	"items_total": 10475.0,
}

# ── access ───────────────────────────────────────────────────────────────────
fake(READING1)
as_user(STOCK_ONLY)
b = api.boot()
check("stock user: boot works, no paper tiles", b["can_transfer"] == 1 and b["paper"]["po"] == 0)
check("stock user cannot upload a PO paper", raises(lambda: upload(), frappe.PermissionError) is not None)
as_user(PO_USER)
b = api.boot()
check("purchase user: boot works, PO tile, no transfers", b["can_transfer"] == 0 and b["paper"]["po"] == 1 and b["paper"]["so"] == 0 and not b["warehouses"])
check("purchase user: transfers stay closed", raises(lambda: api.search_items("pen"), frappe.PermissionError) is not None)
check("purchase user cannot upload an SO paper", raises(lambda: upload("Sales Order"), frappe.PermissionError) is not None)
check("purchase user: no settings", raises(lambda: paper.get_paper_settings(), frappe.PermissionError) is not None)
check("app shell allowed for purchase user", api.app_user_allowed(PO_USER))
from trustbit_school_book_seller.staff_app import session_extend as se  # noqa: E402

check("long session: purchase user while paper is on", se._is_staff(PO_USER))
check("long session: never for the settings page alone", api.app_user_allowed(SM_ONLY) and not se._is_staff(SM_ONLY))
check("long session: sales user not while SO is off", not se._is_staff(SO_USER))
as_user("Administrator")
settings(enabled=0)
check("paper off: purchase user cannot open the app", not api.app_user_allowed(PO_USER))
check("paper off: no long session for a purchase user", not se._is_staff(PO_USER))
check("paper off: stock user keeps the long session", se._is_staff(STOCK_ONLY))
as_user(PO_USER)
check("paper off: upload refused", raises(lambda: upload(), frappe.PermissionError) is not None)
as_user("Administrator")
settings(enabled=1)
as_user(SO_USER)
check("SO off: sales user refused", raises(lambda: upload("Sales Order"), frappe.PermissionError) is not None)

# ── upload checks ────────────────────────────────────────────────────────────
as_user(PO_USER)
exe = base64.b64encode(b"MZ\x90\x00" + b"\x00" * 2000).decode()
check("renamed .exe refused", "Only photos" in (raises(lambda: upload(files=[{"name": "paper.jpg", "data": exe}])) or ""))
check("25-page PDF refused", "25 pages" in (raises(lambda: upload(files=[{"name": "a.pdf", "data": pdf(25)}])) or ""))
check("11 photos refused", raises(lambda: upload(files=[{"name": f"{i}.jpg", "data": jpeg(50, 50)} for i in range(11)])) is not None)
check("PDF + photo refused", raises(lambda: upload(files=[{"name": "a.pdf", "data": pdf(1)}, {"name": "b.jpg", "data": jpeg(50, 50)}])) is not None)
check("> 12 MB refused", "larger than" in (raises(lambda: upload(files=[{"name": "big.jpg", "data": "A" * (17 * 1024 * 1024)}])) or ""))
check("bad base64 refused", raises(lambda: upload(files=[{"name": "x.jpg", "data": "@@@not base64@@@"}])) is not None)
n_pdf = upload(files=[{"name": "q.pdf", "data": pdf(2)}])
check("2-page PDF accepted, 2 pages", frappe.db.get_value("Order Paper", n_pdf, "page_count") == 2
	and frappe.db.get_value("Order Paper", n_pdf, "file_kind") == "PDF")
n_png = upload(files=[{"name": "big.png", "data": jpeg(4000, 3000, "PNG")}])
from PIL import Image  # noqa: E402

f = frappe.get_all("File", filters={"attached_to_name": n_png}, fields=["name", "file_url", "is_private"])[0]
img = Image.open(io.BytesIO(frappe.get_doc("File", f.name).get_content()))
check("photo re-encoded: JPEG, long side 2000, private", img.format == "JPEG" and max(img.size) == 2000 and f.is_private == 1)
cr = ref()
a1 = upload(client_ref=cr)
a2 = paper.upload_paper("Purchase Order", json.dumps([{"name": "p.jpg", "data": jpeg()}]), cr)
check("same client_ref → same paper (no double read)", a2["name"] == a1 and a2.get("already") == 1)
check("read job queued on upload", any(e[0] == a1 for e in ENQ))
as_user("Administrator")
used = pr.month_usage()["pages"]
settings(month_page_limit=used + 1, peak_month_page_limit=used + 1)
as_user(PO_USER)
check("monthly page limit refuses a 2-page PDF", "limit" in (raises(lambda: upload(files=[{"name": "q.pdf", "data": pdf(2)}])) or ""))
as_user("Administrator")
settings(month_page_limit=0, peak_month_page_limit=0)
CONF.pop("kgs_paper_ai_fake")
as_user(PO_USER)
check("no AI key → upload refused with a clear message", "not set up" in (raises(lambda: upload()) or ""))
fake(READING1)

# ── read + match ─────────────────────────────────────────────────────────────
for n in (n_pdf, n_png, a1):
	paper.discard_paper(n)
frappe.db.commit()
by_model = {"claude-sonnet-5-5": dict(READING1, items_total=None, warnings=["page edge cut"])}
fake(dict(READING1, items_total=99999.0), rerank={"choices": [{"line": 5, "candidate": "c1"}, {"line": 1, "candidate": "zz"}]}, by_model=by_model)
p1 = upload()
p = read(p1)
check("read: Ready", p["status"] == "Ready", p.get("error"))
check("auto-fallback: total off → read again with Sonnet", p["model"] == "claude-sonnet-5-5" and p["notes"] and "Sonnet" in p["notes"][0], p["notes"])
calls = json.loads(frappe.db.get_value("Order Paper", p1, "usage_json"))
check("usage: first + fallback (+ double-check) recorded with cost", [c["purpose"] for c in calls][:2] == ["first", "fallback"]
	and all("usd" in c for c in calls) and frappe.db.get_value("Order Paper", p1, "pages_read") == 2)
check("party: printed name = ours → preselected", p["party"] == SUP and p["party_how"] == "name")
l1, l2, l3, l4, l5, l6 = (line(p, i) for i in range(1, 7))
check("line 1 fuzzy → amber, class 3 item (not 4)", l1["colour"] == "amber" and l1["item_code"] == "KGS-PT-ENG3", (l1["colour"], l1["item_code"]))
check("line 1 rate = MRP − 25%", l1["paper_rate"] == 187.5)
check("line 2 twin picked by printed MRP 275", l2["item_code"] == "KGS-PT-MM3-NEW", [c["item_code"] for c in l2["candidates"]])
check("line 3 ISBN → green", l3["colour"] == "green" and l3["how"] == "barcode" and l3["item_code"] == "KGS-PT-GK5", (l3["colour"], l3["how"]))
check("line 4 our code → green, PKT ×10", l4["colour"] == "green" and l4["how"] == "item_code" and l4["uom"] == "PKT" and l4["conversion_factor"] == 10)
check("line 5 unknown → red, not preselected", l5["colour"] == "red" and not l5["item_code"])
check("line 6 class hint 4 → ENG4", l6["item_code"] == "KGS-PT-ENG4", [c["item_code"] for c in l6["candidates"]])
check("AI choice outside the candidates ignored", l1["ai_note"] != "ai_pick" or l1["item_code"] in [c["item_code"] for c in l1["candidates"]])
check("nothing fuzzy is green", all(ln["colour"] != "green" for ln in p["lines"] if ln["how"] in ("fuzzy", "other_party", "none")))
check("AI warning shown", "page edge cut" in p["paper"]["warnings"])
check("save screen defaults", p["save"]["warehouse"] == "Stores - DCV" and p["save"]["needed_by"] == str(add_days(nowdate(), 7)))

# ── check-screen edits ───────────────────────────────────────────────────────
v = p["version"]
check("save blocked while amber lines wait", "Check" in (raises(lambda: paper.save_order(p1, ref(), version=v)) or ""))
check("qty 0 refused", raises(lambda: paper.update_lines(p1, json.dumps([{"idx": 1, "qty": 0}]), v)) is not None)
check("unknown unit refused", raises(lambda: paper.update_lines(p1, json.dumps([{"idx": 1, "uom": "BOX"}]), v)) is not None)
check("fraction of a whole-number unit refused", raises(lambda: paper.update_lines(p1, json.dumps([{"idx": 4, "qty": 1.5}]), v)) is not None)
check("disabled item cannot be picked", raises(lambda: paper.update_lines(p1, json.dumps([{"idx": 5, "item_code": "KGS-PT-DIS"}]), v)) is not None)
check("refused changes did not move the version", paper.get_paper(p1)["version"] == v)
v = paper.get_paper(p1)["version"]
r = paper.update_lines(p1, json.dumps([{"idx": 1, "decision": "ok"}, {"idx": 2, "decision": "ok"}, {"idx": 6, "decision": "ok"}]), v)
check("Correct → confirmed lines", all(ln["decision"] == "ok" and ln["by_person"] for ln in r["lines"]) and r["version"] == v + 1)
frappe.db.commit()
stale = paper.update_lines(p1, json.dumps([{"idx": 1, "qty": 5}]), v)
check("stale version → conflict + fresh paper", stale.get("conflict") == 1 and stale["paper"]["version"] == v + 1)
v = r["version"]
r = paper.update_lines(p1, json.dumps([{"idx": 2, "item_code": "KGS-PT-MM3-OLD"}]), v)
check("Change item → that item, confirmed", r["lines"][0]["item_code"] == "KGS-PT-MM3-OLD" and r["lines"][0]["decision"] == "ok")
v = r["version"]
r = paper.update_lines(p1, json.dumps([{"idx": 2, "item_code": "KGS-PT-MM3-NEW"}, {"idx": 1, "qty": 25}]), v)
v = r["version"]
check("qty change kept", next(ln for ln in r["lines"] if ln["idx"] == 1)["qty"] == 25)
r = paper.update_lines(p1, json.dumps([{"idx": 5, "decision": "left"}]), v)
v = r["version"]
r = paper.update_lines(p1, json.dumps([{"idx": 5, "decision": None}]), v)
check("undo → red again", r["lines"][0]["decision"] is None and r["lines"][0]["colour"] == "red")
v = r["version"]
sp = paper.set_party(p1, SUP2, v)
check("set_party keeps confirmed lines", line(sp, 1)["item_code"] == "KGS-PT-ENG3" and line(sp, 1)["decision"] == "ok" and sp["party"] == SUP2)
sp = paper.set_party(p1, SUP, sp["version"])
frappe.db.commit()
v = sp["version"]

# ── save PO ──────────────────────────────────────────────────────────────────
s = paper.save_order(p1, ref(), send_for_approval=1, version=v)
frappe.db.commit()
check("PO saved + sent for approval", s["ok"] == 1 and s["workflow_state"] == "Pending Approval", s)
po = frappe.get_doc("Purchase Order", s["doc"])
check("PO as the clerk, never back-dated, +7 days, SBGD-like default", po.owner == PO_USER and str(po.transaction_date) == nowdate()
	and str(po.schedule_date) == str(add_days(nowdate(), 7)) and po.set_warehouse == "Stores - DCV" and po.docstatus == 0)
rates = {i.item_code: (flt(i.qty), i.uom, flt(i.rate), i.supplier_part_no) for i in po.items}
check("PO lines: 5 saved, red line left out", len(po.items) == 5 and "KGS-PT-PEN" in rates and s["left_out"][0]["text"].startswith("Totally"))
check("PO rates from the paper (MRP − 25%, printed rate)", rates["KGS-PT-ENG3"][2] == 187.5 and rates["KGS-PT-PEN"][2] == 80
	and rates["KGS-PT-PEN"][1] == "PKT", rates)
check("PO qty: person's 25", rates["KGS-PT-ENG3"][0] == 25)
check("supplier code on the PO line", rates["KGS-PT-ENG4"][3] == "SUN-ENG-4")
check("remark: paper + left out", "From paper " + p1 in (po.custom_remark or "") and "Totally unknown" in po.custom_remark)
check("paper pages attached to the PO", frappe.db.count("File", {"attached_to_doctype": "Purchase Order", "attached_to_name": po.name}) == 1)
# the owners' e-mail itself is a short-queue job after commit (checked in the browser test, with a worker)
check("open Workflow Action for the owners", frappe.db.exists("Workflow Action", {"reference_doctype": "Purchase Order",
	"reference_name": po.name, "status": "Open"}))
check("paper marked Saved", frappe.db.get_value("Order Paper", p1, ["status", "created_doc", "saved_by"]) == ("Saved", po.name, PO_USER))
again = paper.save_order(p1, ref(), send_for_approval=1)
check("save again → same PO (idempotent)", again["already"] == 1 and again["doc"] == po.name)
aliases = frappe.get_all("Party Item Alias", filters={"party": SUP}, fields=["key_type", "match_key", "item_code", "times_used"])
check("aliases learned (text for 5, code for 2)", len([a for a in aliases if a.key_type == "Text"]) == 5 and len([a for a in aliases if a.key_type == "Code"]) == 2, aliases)
check("class hint carried into a classless wording", any(a.match_key.endswith(" C4") for a in aliases), [a.match_key for a in aliases])
check("ERPNext supplier part no filled", frappe.db.get_value("Item Supplier", {"parent": "KGS-PT-ENG4", "supplier": SUP}, "supplier_part_no") == "SUN-ENG-4")

# ── second paper from the same supplier: all green ───────────────────────────
READING2 = json.loads(json.dumps(READING1))
READING2["paper_no"] = "PT-Q-2"
READING2["items_total"] = None
READING2["lines"][2].pop("isbn")
READING2["lines"][1]["mrp"] = 300  # new MRP since it was learned
fake(READING2)
p2 = upload()
q = read(p2)
check("2nd paper: supplier = the one chosen last time", q["party"] == SUP and q["party_how"] == "last_time", (q["party"], q["party_how"]))
c = {ln["idx"]: (ln["colour"], ln["how"]) for ln in q["lines"]}
check("2nd paper: remembered lines green", c[1] == ("green", "alias_text") and c[3] == ("green", "alias_text") and c[6] == ("green", "alias_code"), c)
check("2nd paper: MRP changed → amber 'new edition?'", c[2][0] == "amber" and "MRP" in line(q, 2)["note"], line(q, 2)["note"])
check("2nd paper: never-matched line still red", c[5][0] == "red")
paper.discard_paper(p2)

# duplicate paper number
fake(dict(READING1, items_total=None))
p3 = upload()
q = read(p3)
check("duplicate paper no warned on the check screen", q["duplicate"] and q["duplicate"]["doc"] == po.name)
ch = [{"idx": ln["idx"], "decision": "ok"} for ln in q["lines"] if ln["colour"] == "amber"]
q2 = paper.update_lines(p3, json.dumps(ch), q["version"])
res = paper.save_order(p3, ref(), version=q2["version"], rate_mode="ours")
check("duplicate → save asks first", res.get("ok") == 0 and res["duplicate"]["doc"] == po.name)
res = paper.save_order(p3, ref(), version=q2["version"], rate_mode="ours", allow_duplicate=1)
frappe.db.commit()
po3 = frappe.get_doc("Purchase Order", res["doc"])
check("'our usual price' → no paper rates, draft only", res["workflow_state"] == "Draft"
	and all(flt(i.rate) != 187.5 for i in po3.items if i.item_code == "KGS-PT-ENG3"), [(i.item_code, i.rate) for i in po3.items])
times = frappe.db.get_value("Party Item Alias", {"party": SUP, "key_type": "Code", "match_key": pm.code_key("SUN-ENG-4")}, "times_used")
check("confirmed again → times_used 2", times == 2, times)

# ── remembered names ─────────────────────────────────────────────────────────
ap = paper.alias_parties("Supplier")
check("names: supplier listed with count", any(r_["party"] == SUP and r_["names"] >= 7 for r_ in ap["parties"]) and ap["can_edit"] == 0)
la = paper.list_aliases("Supplier", SUP)
target = next(r_ for r_ in la["rows"] if r_["item_code"] == "KGS-PT-ENG3")
check("purchase user cannot delete a name", raises(lambda: paper.delete_alias(target["name"]), frappe.PermissionError) is not None)
as_user(SO_USER)
as_user("Administrator")
settings(so_enabled=1)
as_user(SO_USER)
check("sales manager cannot change a supplier's name", raises(lambda: paper.change_alias(target["name"], "KGS-PT-ENG4"), frappe.PermissionError) is not None)
as_user(PO_MGR)
ch_ = paper.change_alias(target["name"], "KGS-PT-ENG4")
check("purchase manager changes the item", ch_["item_code"] == "KGS-PT-ENG4")
paper.delete_alias(target["name"])
frappe.db.commit()
check("purchase manager deletes it", not frappe.db.exists("Party Item Alias", target["name"]))

# ── Sales Order from a school list ───────────────────────────────────────────
as_user(SO_USER)
fake({"paper_kind": "school_book_list", "school_or_class": "R.D. Public School Class III", "lines": [
	{"text": "Sunshine English Reader 3"}, {"text": "Koncept Global Intellect GK 5"}]})
s1 = upload("Sales Order", copies=30)
q = read(s1)
check("SO list: no qty → copies of each (30)", all(ln["qty"] == 30 for ln in q["lines"]), [ln["qty"] for ln in q["lines"]])
check("SO: customer to choose (no name on paper)", not q["party"])
check("save without customer refused", "Choose the customer" in (raises(lambda: paper.save_order(s1, ref(), version=q["version"])) or ""))
q = paper.set_party(s1, CUST, q["version"])
u2 = paper.update_lines(s1, json.dumps([{"idx": ln["idx"], "decision": "ok"} for ln in q["lines"]]), q["version"], copies=40)
check("copies changed → 40 on every line", all(ln["qty"] == 40 for ln in u2["lines"]))
so = paper.save_order(s1, ref(), version=u2["version"])
frappe.db.commit()
sod = frappe.get_doc("Sales Order", so["doc"])
check("SO draft, prices from our selling list", sod.docstatus == 0 and sod.customer == CUST
	and {i.item_code: flt(i.rate) for i in sod.items}.get("KGS-PT-ENG3") == 250, [(i.item_code, i.rate) for i in sod.items])
as_user(PO_USER)
check("purchase user cannot open the SO paper", raises(lambda: paper.get_paper(s1), frappe.PermissionError) is not None)

# ── discard / reread rules ───────────────────────────────────────────────────
fake(READING1)
d1 = upload()
read(d1)
as_user(PO_MGR)
g = paper.get_paper(d1)
rs = paper.update_lines(d1, json.dumps([{"idx": 1, "decision": "ok"}]), g["version"])
frappe.db.commit()
check("another purchase user can continue the paper", g["status"] == "Ready" and rs["lines"][0]["decision"] == "ok")
d_other = upload()
as_user(PO_USER)
check("clerk cannot discard someone else's paper", raises(lambda: paper.discard_paper(d_other)) is not None)
as_user(PO_MGR)
paper.discard_paper(d_other)
as_user(PO_USER)
check("reread with a model not in the price table refused", raises(lambda: paper.reread(d1, "gpt-9")) is not None)
paper.reread(d1, "claude-opus-5-5")
check("reread queued with that model", ENQ[-1] == (d1, "claude-opus-5-5", "reread"))
frappe.db.commit()
q = read(d1, "claude-opus-5-5", "reread")
check("reread result uses Opus", q["model"] == "claude-opus-5-5" and q["status"] == "Ready")
paper.discard_paper(d1)
check("discarded paper cannot be re-read", raises(lambda: paper.reread(d1)) is not None)
frappe.db.commit()

# ── failure path ─────────────────────────────────────────────────────────────
fake({"_fail": "The AI service is busy. Please try again in a minute."})
f1 = upload()
q = read(f1)
check("AI failure → Failed with a plain message", q["status"] == "Failed" and "busy" in q["error"])
fake({"paper_kind": "other", "lines": []})
paper.reread(f1)
q = read(f1, None, "reread")
check("no lines read → Failed, asks for a clearer photo", q["status"] == "Failed" and "clearer" in q["error"])
paper.discard_paper(f1)
frappe.db.commit()

# ── settings ─────────────────────────────────────────────────────────────────
as_user(OWNER)
st = paper.get_paper_settings()
check("owner sees settings, providers incl. coming soon, no key value", [p_["active"] for p_ in st["providers"]] == [1, 0, 0]
	and "kgs_paper_ai_key" not in json.dumps(st) and st["key_set"] == 0)
check("estimated ₹ per page: Haiku ≈ 0.26, Sonnet ≈ 5.19", abs(next(m for m in st["models"] if m["model"] == "claude-haiku-5-5")["inr_per_page"] - 0.26) < 0.02
	and abs(next(m for m in st["models"] if m["model"] == "claude-sonnet-5-5")["inr_per_page"] - 5.19) < 0.05)
check("model without a price row refused", raises(lambda: paper.save_paper_settings(json.dumps({"ai_model": "claude-unknown-9"}))) is not None)
st = paper.save_paper_settings(json.dumps({"ai_model": "claude-sonnet-5-5", "models": st["models"] + [
	{"model": "claude-haiku-6-0", "label": "Claude Haiku 6", "input_per_mtok": 0.2, "output_per_mtok": 1}]}))
frappe.db.commit()
check("owner changes the model + adds a newer one", st["values"]["ai_model"] == "claude-sonnet-5-5" and any(m["model"] == "claude-haiku-6-0" for m in st["models"]))
check("next read uses the new model", pr.get_settings().ai_model == "claude-sonnet-5-5")
check("usage this month counted", st["usage"]["pages"] >= 5 and st["usage"]["inr_gst"] >= 0)

# ── the real Anthropic code path, against a local mock server ────────────────
SEEN = []
PLAN = []


class Mock(BaseHTTPRequestHandler):
	def log_message(self, *a):
		pass

	def do_POST(self):
		body = json.loads(self.rfile.read(int(self.headers["content-length"])))
		SEEN.append({"headers": dict(self.headers), "body": body})
		status, payload = PLAN.pop(0) if PLAN else (200, None)
		if payload is None:
			payload = {"id": "msg_1", "type": "message", "model": body["model"] + "-20261001", "stop_reason": "tool_use",
				"content": [{"type": "tool_use", "id": "t1", "name": body["tool_choice"]["name"], "input": READING1}],
				"usage": {"input_tokens": 6000, "output_tokens": 2500}}
		raw = json.dumps(payload).encode()
		self.send_response(status)
		self.send_header("content-type", "application/json")
		self.send_header("retry-after", "1")
		self.end_headers()
		self.wfile.write(raw)


srv = HTTPServer(("127.0.0.1", 0), Mock)
threading.Thread(target=srv.serve_forever, daemon=True).start()
SECRET = "sk-ant-TEST-" + uuid.uuid4().hex
CONF.pop("kgs_paper_ai_fake", None)
CONF["kgs_paper_ai_key"] = SECRET
CONF["kgs_paper_ai_url"] = f"http://127.0.0.1:{srv.server_port}/v1/messages"
as_user("Administrator")
settings(ai_model="claude-haiku-5-5", rerank=0, auto_fallback=0)
as_user(PO_USER)
check("provider is the real Anthropic class", isinstance(pr.get_provider(pr.get_settings()), pr.AnthropicProvider))
m1 = upload()
q = read(m1)
h = SEEN[-1]["headers"]
body = SEEN[-1]["body"]
check("anthropic: Ready from the mock", q["status"] == "Ready", q.get("error"))
check("anthropic: key + version headers", h.get("x-api-key") == SECRET and h.get("anthropic-version") == "2023-06-01")
check("anthropic: image block + forced tool", body["messages"][0]["content"][0]["type"] == "image"
	and body["messages"][0]["content"][0]["source"]["media_type"] == "image/jpeg"
	and body["tool_choice"] == {"type": "tool", "name": "record_paper"} and body["model"] == "claude-haiku-5-5")
u = json.loads(frappe.db.get_value("Order Paper", m1, "usage_json"))[0]
check("anthropic: tokens + cost priced on the requested id", u["input_tokens"] == 6000 and u["output_tokens"] == 2500
	and abs(u["usd"] - (6000 * 0.10 + 2500 * 0.50) / 1e6) < 1e-9 and u["served_model"].endswith("-20261001"))
PLAN[:] = [(529, {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}})]
m2 = upload(files=[{"name": "d.pdf", "data": pdf(1)}])
q = read(m2)
check("anthropic: one retry after 529, then Ready", q["status"] == "Ready" and SEEN[-1]["body"]["messages"][0]["content"][0]["type"] == "document")
PLAN[:] = [(401, {"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}})]
m3 = upload()
q = read(m3)
check("anthropic: 401 → 'key not accepted'", q["status"] == "Failed" and "key" in q["error"].lower())
PLAN[:] = [(400, {"type": "error", "error": {"type": "invalid_request_error", "message": "Your credit balance is too low"}})]
paper.reread(m3)
q = read(m3, None, "reread")
check("anthropic: credit used up → plain message", q["status"] == "Failed" and "credit" in q["error"].lower())
CONF["kgs_paper_ai_url"] = "https://evil.example.com/v1/messages"
check("URL override to a foreign host ignored", pr.AnthropicProvider()._url() == pr.ANTHROPIC_URL)
leaks = frappe.db.sql("select count(*) from `tabError Log` where error like %s", f"%{SECRET}%")[0][0]
leaks += frappe.db.sql("select count(*) from `tabOrder Paper` where concat_ws('|', usage_json, ai_json, lines_json, error) like %s", f"%{SECRET}%")[0][0]
check("the AI key is in no log and no document", leaks == 0)
srv.shutdown()
for n in (m1, m2, m3):
	paper.discard_paper(n)
CONF.pop("kgs_paper_ai_key", None)
CONF.pop("kgs_paper_ai_url", None)

# ── rate limit ───────────────────────────────────────────────────────────────
as_user(PO_MGR)
for _try in range(2):  # a minute boundary between set and call would reset the counter
	frappe.cache.set(rl_key(PO_MGR), api.RATE_LIMIT_PER_MINUTE)
	msg_ = raises(lambda: paper.my_papers("mine", 30), frappe.TooManyRequestsError)
	if msg_:
		break
check("121st request in a minute refused", msg_ and "Too many" in msg_, msg_)
as_user(PO_MGR)

# ── restore ──────────────────────────────────────────────────────────────────
frappe.set_user("Administrator")
s = frappe.get_doc("Order Paper Settings")
for k in ("enabled", "so_enabled", "ai_model", "fallback_model", "auto_fallback", "rerank", "month_page_limit", "peak_month_page_limit"):
	s.set(k, SETTINGS_BEFORE.get(k))
s.set("model_prices", [r_ for r_ in s.model_prices if r_.model != "claude-haiku-6-0"])
s.save(ignore_permissions=True)
frappe.db.set_value("UOM", "PKT", "must_be_whole_number", PKT_WHOLE_BEFORE)
frappe.db.commit()

passed = sum(1 for _n, ok, _d in RESULTS if ok)
print(f"\n{passed}/{len(RESULTS)} passed")
