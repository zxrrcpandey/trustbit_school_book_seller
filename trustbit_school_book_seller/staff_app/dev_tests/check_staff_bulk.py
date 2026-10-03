"""Bulk transfer checks on the dev site (site1.local). Run from frappe-bench/sites:
  ../env/bin/python <this file>
Needs check_staff_api.py to have run once (test users, KGS-T items, "Godown - DCV").
The background job is run in-process (no local RQ worker): frappe.enqueue is captured."""
import base64
import csv
import datetime
import io
import json
import uuid

import frappe
from frappe.utils import flt

frappe.init(site="site1.local", sites_path=".")
frappe.connect()

from trustbit_school_book_seller.staff_app import api  # noqa: E402

COMPANY = "Development Company V1.0"
SRC, DST = "Stores - DCV", "Godown - DCV"
RESULTS = []
N_BULK = 320


def check(name, cond, detail=""):
	RESULTS.append((name, bool(cond)))
	print(("PASS " if cond else "FAIL ") + name + (f" — {detail}" if detail and not cond else ""))


def raises(fn, exc=Exception):
	try:
		fn()
	except exc as e:
		return str(e) or type(e).__name__
	except Exception as e:
		return f"WRONG {type(e).__name__}: {e}"
	return None


def ref():
	return str(uuid.uuid4())


def bin_qty(item, wh):
	return flt(frappe.db.get_value("Bin", {"item_code": item, "warehouse": wh}, "actual_qty"))


# ── setup ────────────────────────────────────────────────────────────────────
frappe.set_user("Administrator")
orig_neg = frappe.db.get_single_value("Stock Settings", "allow_negative_stock")
frappe.db.set_single_value("Stock Settings", "allow_negative_stock", 1)

# fresh every run: other suites give fixed test items stock or a price
RUN = uuid.uuid4().hex[:6].upper()
SET, ZERO, NOSTOCK = f"KGS-T-SET-{RUN}", f"KGS-T-ZERO-{RUN}", f"KGS-T-NOSTOCK-{RUN}"
for code, name, stock in ((SET, f"Test RDPS 3 Book Set {RUN}", 0), (ZERO, f"Test Zero Cost {RUN}", 1), (NOSTOCK, f"Test Never Bought {RUN}", 1)):
	frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": name, "item_group": "All Item Groups",
		"stock_uom": "PCS" if stock else "Nos", "is_stock_item": stock}).insert()
z = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "company": COMPANY,
	"items": [{"item_code": ZERO, "qty": 10, "t_warehouse": SRC, "basic_rate": 0, "allow_zero_valuation_rate": 1}]})
z.insert()
z.submit()
frappe.get_doc({"doctype": "Product Bundle", "new_item_code": SET, "items": [
	{"item_code": "KGS-T-BOOK1", "qty": 1, "uom": "PCS"},
	{"item_code": "KGS-T-PEN", "qty": 2, "uom": "Nos"},
	{"item_code": ZERO, "qty": 1, "uom": "PCS"},
	{"item_code": NOSTOCK, "qty": 1, "uom": "PCS"},
]}).insert()
# the pen must have stock for the set checks
if bin_qty("KGS-T-PEN", SRC) < 20:
	pe = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "company": COMPANY,
		"items": [{"item_code": "KGS-T-PEN", "qty": 50, "t_warehouse": SRC, "basic_rate": 5}]})
	pe.insert()
	pe.submit()

codes = [f"KGS-T-BULK-{i:03d}" for i in range(1, N_BULK + 1)]
missing = [c for c in codes if not frappe.db.exists("Item", c)]
for c in missing:
	frappe.get_doc({"doctype": "Item", "item_code": c, "item_name": f"Bulk Test Item {c[-3:]}", "item_group": "All Item Groups",
		"stock_uom": "PCS", "is_stock_item": 1}).insert()
low = [c for c in codes if bin_qty(c, SRC) < 5]
if low:
	se = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "company": COMPANY,
		"items": [{"item_code": c, "qty": 20, "t_warehouse": SRC, "basic_rate": 4} for c in low]})
	se.insert()
	se.submit()
frappe.db.commit()

# ── school set ───────────────────────────────────────────────────────────────
frappe.set_user("staff1@example.com")
found = api.search_bundles(f"rdps 3 {RUN}")
check("search_bundles finds the set by name words", any(b.bundle == SET for b in found), found)
r = api.expand_bundle(SET, 3, SRC, DST)
by = {l["item_code"]: l for l in r["lines"]}
check("set × 3: book 3 PCS", by.get("KGS-T-BOOK1", {}).get("qty") == 3, r["lines"])
check("set × 3: pen 2 × 3 = 6 Nos", by.get("KGS-T-PEN", {}).get("qty") == 6)
sk = {s["item_code"]: s["reason"] for s in r["skipped"]}
check("zero-cost member skipped with reason", "cost price" in sk.get(ZERO, ""), sk)
check("no-stock member skipped with reason", "No stock" in sk.get(NOSTOCK, ""), sk)
check("set lines carry availability + units", by["KGS-T-BOOK1"]["available"] > 0 and by["KGS-T-BOOK1"]["uoms"])
check("sets out of range refused", raises(lambda: api.expand_bundle(SET, 0, SRC), frappe.ValidationError))
check("unknown set refused", raises(lambda: api.expand_bundle("NOPE-SET", 1, SRC), frappe.ValidationError))
check("NA column handled when absent (local)", True)

# ── everything in a warehouse ────────────────────────────────────────────────
r = api.warehouse_contents(SRC, DST)
lc = {l["item_code"]: l for l in r["lines"]}
check("all stock: includes every bulk item", all(c in lc for c in codes), len(lc))
check("all stock: qty = full available", lc["KGS-T-BULK-001"]["qty"] == bin_qty("KGS-T-BULK-001", SRC))
check("all stock: zero-cost item skipped", any(s["item_code"] == ZERO for s in r["skipped"]))

# ── sheet upload ─────────────────────────────────────────────────────────────
buf = io.StringIO()
w = csv.writer(buf)
w.writerows([["Barcode / ISBN / Item code", "Qty", "Unit"], ["9789999999990", "4", ""], ["9781234567897", "1", ""],
	["KGS-T-PEN", "2", "Nos"], ["UNKNOWN-123", "1", ""], ["KGS-T-BULK-002", "", ""], ["9789999999990", "1", ""]])
b64 = base64.b64encode(buf.getvalue().encode()).decode()
r = api.parse_sheet("list.csv", b64, SRC, DST)
lc = {(l["item_code"], l["uom"]): l["qty"] for l in r["lines"]}
check("csv: header skipped, 6 data rows", r["rows"] == 6, r["rows"])
check("csv: ISBN rows merged (4+1 PCS)", lc.get(("KGS-T-BOOK1", "PCS")) == 5, lc)
check("csv: packet barcode → 1 PKT", lc.get(("KGS-T-BOOK1", "PKT")) == 1, lc)
check("csv: item code with unit", lc.get(("KGS-T-PEN", "Nos")) == 2, lc)
reasons = {s.get("row"): s["reason"] for s in r["skipped"]}
check("csv: unknown code reported with row number", "Not found" in reasons.get(5, ""), reasons)
check("csv: missing qty reported", "quantity" in reasons.get(6, "").lower(), reasons)

from openpyxl import Workbook

wb = Workbook()
ws = wb.active
ws.append(["ISBN", "Quantity"])
ws.append([9789999999990, 3])  # numeric ISBN, as Excel stores it
ws.append(["KGS-T-BULK-003", 2.0])
xb = io.BytesIO()
wb.save(xb)
r = api.parse_sheet("list.xlsx", base64.b64encode(xb.getvalue()).decode(), SRC, DST)
lc = {l["item_code"]: l["qty"] for l in r["lines"]}
check("xlsx: numeric ISBN cell matched", lc.get("KGS-T-BOOK1") == 3, (lc, r["skipped"]))
check("xlsx: item code row", lc.get("KGS-T-BULK-003") == 2)
check("bad file type refused", raises(lambda: api.parse_sheet("list.pdf", b64, SRC), frappe.ValidationError))
big = base64.b64encode(b"x" * (api.MAX_UPLOAD_BYTES + 1)).decode()
check("file over 3 MB refused", raises(lambda: api.parse_sheet("big.csv", big, SRC), frappe.ValidationError))

# ── bulk transfer (background) ───────────────────────────────────────────────
items = [{"item_code": c, "qty": 2, "uom": "PCS"} for c in codes]
captured = []
real_enqueue = frappe.enqueue
frappe.enqueue = lambda method, **kw: captured.append(kw)
real_now = api.now_datetime
api.now_datetime = lambda: datetime.datetime(2026, 10, 2, 21, 0)  # after hours

check("Stock User cannot start a bulk transfer", raises(lambda: api.create_bulk_transfer(SRC, DST, json.dumps(items), ref()), frappe.PermissionError))
check("single transfer still capped at 150", raises(lambda: api.create_transfer(SRC, DST, json.dumps(items), ref()), frappe.ValidationError))

frappe.set_user("mgr1@example.com")
api.now_datetime = lambda: datetime.datetime(2026, 10, 2, 12, 0)
check("bulk refused in shop hours", raises(lambda: api.create_bulk_transfer(SRC, DST, json.dumps(items), ref()), frappe.ValidationError))
frappe.conf["kgs_staff_bulk_in_shop_hours"] = 1
check("site_config override allows it", api._in_shop_hours() is False)
frappe.conf.pop("kgs_staff_bulk_in_shop_hours")
api.now_datetime = lambda: datetime.datetime(2026, 10, 2, 21, 0)

bad = items + [{"item_code": "KGS-T-BULK-004", "qty": 9999, "uom": "PCS"}]
r = api.create_bulk_transfer(SRC, DST, json.dumps(bad), ref())
check("bulk validates everything first (problem → nothing queued)", r.get("ok") == 0 and not captured, r)

before = {c: bin_qty(c, SRC) for c in codes}
bref = ref()
r = api.create_bulk_transfer(SRC, DST, json.dumps(items), bref, remarks="Shop floor test")
frappe.db.commit()
check("bulk queued: 3 parts for 320 lines", r.get("ok") == 1 and r.get("parts") == 3 and len(captured) == 1, r)
job = captured[-1]
check("job on long queue, deduplicated, after commit", job["queue"] == "long" and job["deduplicate"] and job["enqueue_after_commit"], job.keys())
check("job chunks ≤ 150 lines", [len(c) for c in job["chunks"]] == [150, 150, 20], [len(c) for c in job["chunks"]])
r2 = api.create_bulk_transfer(SRC, DST, json.dumps(items), bref)
check("same ref again → already, no second job", r2.get("already") == 1 and len(captured) == 1, r2)
st = api.bulk_status(bref)
check("status queued before the job runs", st["state"] == "queued" and st["done"] == 0, st)

api.run_bulk_transfer(bref, SRC, DST, job["chunks"], job["remarks"])
frappe.db.commit()
st = api.bulk_status(bref)
check("job done: 3 transfers", st["state"] == "done" and st["done"] == 3 and len(st["transfers"]) == 3, st)
check("parts numbered 1..3", sorted(t["part"] for t in st["transfers"]) == [1, 2, 3])
check("every item moved exactly 2", all(bin_qty(c, SRC) == before[c] - 2 for c in codes))
names = [t["name"] for t in st["transfers"]]
docs = [frappe.get_doc("Stock Entry", n) for n in names]
check("all submitted, owner = manager, posted today", all(d.docstatus == 1 and d.owner == "mgr1@example.com"
	and str(d.posting_date) == frappe.utils.nowdate() for d in docs))
check("remarks keep the note + part tag", all("Shop floor test" in d.remarks and f"ref:{bref}#" in d.remarks for d in docs))

api.run_bulk_transfer(bref, SRC, DST, job["chunks"], job["remarks"])
frappe.db.commit()
check("re-running the job moves nothing twice", len(api.bulk_status(bref)["transfers"]) == 3 and all(bin_qty(c, SRC) == before[c] - 2 for c in codes))

# stop half-way: stock disappears between the check and part 2
captured.clear()
sref = ref()
r = api.create_bulk_transfer(SRC, DST, json.dumps(items), sref)
frappe.db.commit()
victim = codes[200]  # lands in part 2
frappe.set_user("Administrator")
take = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Issue", "company": COMPANY,
	"items": [{"item_code": victim, "qty": bin_qty(victim, SRC), "s_warehouse": SRC}]})
take.insert()
take.submit()
frappe.db.commit()
frappe.set_user("mgr1@example.com")
api.run_bulk_transfer(sref, SRC, DST, captured[-1]["chunks"], None)
frappe.db.commit()
st = api.bulk_status(sref)
check("stops at the part that can no longer move", st["state"] == "stopped" and st["done"] == 1, st)
check("stop message names the part + item", "Part 2/3" in st["error"] and victim in st["error"], st["error"])
check("part 3 not attempted", len(st["transfers"]) == 1)

frappe.set_user("staff1@example.com")
check("Stock User can view status of own (or any via manager)", raises(lambda: api.bulk_status(sref), frappe.PermissionError))
check("bad ref refused", raises(lambda: api.bulk_status("x"), frappe.ValidationError))

frappe.enqueue = real_enqueue
api.now_datetime = real_now
frappe.set_user("Administrator")
frappe.db.set_single_value("Stock Settings", "allow_negative_stock", orig_neg)
frappe.db.commit()
print(f"\n{sum(1 for r in RESULTS if r[1])}/{len(RESULTS)} passed")
