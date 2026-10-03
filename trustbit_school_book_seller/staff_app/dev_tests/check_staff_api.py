"""Server-side tests for trustbit_school_book_seller.staff_app.api on site1.local.
Run from frappe-bench/sites:  ../env/bin/python <this file>
Creates test masters (prefixed KGS-T / "Godown - DCV"), mirrors production's
allow_negative_stock=1 for the run, restores it at the end."""
import os
import json
import uuid

import frappe
from frappe.utils import flt, nowdate

frappe.init(site="site1.local", sites_path=".")
frappe.connect()

from trustbit_school_book_seller.staff_app import api  # noqa: E402

COMPANY = "Development Company V1.0"
SRC, DST = "Stores - DCV", "Godown - DCV"
RESULTS = []


def check(name, cond, detail=""):
	RESULTS.append((name, bool(cond), detail))
	print(("PASS " if cond else "FAIL ") + name + (f" — {detail}" if detail and not cond else ""))


def raises(fn, exc=Exception):
	try:
		fn()
	except exc as e:
		return str(e) or type(e).__name__
	except Exception as e:  # wrong type
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

for uom, whole in (("PCS", 0), ("PKT", 0), ("Nos", 1)):
	if not frappe.db.exists("UOM", uom):
		frappe.get_doc({"doctype": "UOM", "uom_name": uom, "must_be_whole_number": whole}).insert()
if not frappe.db.exists("Warehouse", DST):
	frappe.get_doc({"doctype": "Warehouse", "warehouse_name": "Godown", "company": COMPANY,
		"parent_warehouse": "All Warehouses - DCV"}).insert()


def make_item(code, name, stock_uom="PCS", uoms=(), barcodes=(), isbn=None):
	if frappe.db.exists("Item", code):
		return
	d = frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": name, "item_group": "All Item Groups",
		"stock_uom": stock_uom, "is_stock_item": 1,
		"uoms": [{"uom": stock_uom, "conversion_factor": 1}] + [{"uom": u, "conversion_factor": f} for u, f in uoms],
		"barcodes": [{"barcode": b, "uom": u} for b, u in barcodes]})
	if isbn:
		d.custom_isbn_barcode = isbn
	d.insert()


make_item("KGS-T-BOOK1", "Test Viva Maths 3", uoms=[("PKT", 100)], barcodes=[("9780000000011", "PKT"), ("9780000000028", None)], isbn="9789999999990")
make_item("KGS-T-PEN", "Test Blue Pen", stock_uom="Nos")
# fresh every run: other suites give the old fixed ones stock or a price
RUN = uuid.uuid4().hex[:6].upper()
ZERO, NOSTOCK = f"KGS-T-ZERO-{RUN}", f"KGS-T-NOSTOCK-{RUN}"
make_item(ZERO, f"Test Zero Cost Item {RUN}")
make_item(NOSTOCK, f"Test Never Bought {RUN}")
make_item("KGS-T-DISABLED", "Test Disabled Item")
frappe.db.set_value("Item", "KGS-T-DISABLED", "disabled", 0)


def receipt(item, qty, rate, zero=False):
	se = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "company": COMPANY,
		"items": [{"item_code": item, "qty": qty, "t_warehouse": SRC, "basic_rate": rate,
			"allow_zero_valuation_rate": 1 if zero else 0}]})
	se.insert()
	se.submit()


if bin_qty("KGS-T-BOOK1", SRC) < 500:
	receipt("KGS-T-BOOK1", 1000, 12)
if bin_qty("KGS-T-PEN", SRC) < 50:
	receipt("KGS-T-PEN", 100, 5)
receipt(ZERO, 10, 0, zero=True)
if bin_qty("KGS-T-DISABLED", SRC) < 5:
	receipt("KGS-T-DISABLED", 10, 3)
frappe.db.set_value("Item", "KGS-T-DISABLED", "disabled", 1)

for email, roles in (("staff1@example.com", ["Stock User"]), ("mgr1@example.com", ["Stock Manager", "Stock User"]),
		("nostock@example.com", ["Sales User"])):
	if not frappe.db.exists("User", email):
		u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0,
			"new_password": "Kgs-Test-2026!x"})
		u.insert()
		u.add_roles(*roles)
frappe.db.commit()

# ── access ───────────────────────────────────────────────────────────────────
frappe.set_user("Guest")
check("guest is refused", raises(api.boot, frappe.PermissionError))
frappe.set_user("nostock@example.com")
check("user without Stock role is refused", raises(api.boot, frappe.PermissionError))
frappe.set_user("staff1@example.com")
frappe.conf["kgs_staff_app_disabled"] = 1
check("kill switch refuses", raises(api.boot, frappe.PermissionError))
frappe.conf.pop("kgs_staff_app_disabled")

b = api.boot()
names = [w["name"] for w in b["warehouses"]]
check("boot lists leaf warehouses", SRC in names and DST in names, names)
check("boot hides Transit + group warehouses", "Goods In Transit - DCV" not in names and "All Warehouses - DCV" not in names, names)
check("boot default_from = Stock Settings default", b["default_from"] == SRC, b["default_from"])
check("boot is_manager=0 for Stock User", b["is_manager"] == 0)

# ── lookup ───────────────────────────────────────────────────────────────────
r = api.lookup_item("9780000000011", SRC, DST)
check("packet barcode finds item", r["found"] and r["item_code"] == "KGS-T-BOOK1", r)
check("packet barcode defaults UOM to PKT", r["uom"] == "PKT", r.get("uom"))
check("payload has PKT factor 100", any(u["uom"] == "PKT" and u["factor"] == 100 for u in r["uoms"]), r["uoms"])
check("available is source Bin qty", r["available"] == bin_qty("KGS-T-BOOK1", SRC), r["available"])
r = api.lookup_item("9780000000028", SRC)
check("barcode without UOM defaults to stock UOM", r["uom"] == "PCS", r.get("uom"))
r = api.lookup_item("9789999999990", SRC)
check("ISBN (custom_isbn_barcode) finds item", r["found"] and r["item_code"] == "KGS-T-BOOK1", r)
r = api.lookup_item("KGS-T-PEN", SRC)
check("item code finds item", r["found"] and r["item_code"] == "KGS-T-PEN")
check("Nos UOM flagged whole", r["uoms"][0]["whole"] == 1, r["uoms"])
check("unknown code → found 0", api.lookup_item("0000000000000", SRC)["found"] == 0)
check("no-stock item has a problem", api.lookup_item(NOSTOCK, SRC)["problems"])
check("zero-cost item has a problem", "cost price" in " ".join(api.lookup_item(ZERO, SRC)["problems"]))
check("disabled item has a problem", "disabled" in " ".join(api.lookup_item("KGS-T-DISABLED", SRC)["problems"]))

# ── search / levels ──────────────────────────────────────────────────────────
s = api.search_items("viva maths", SRC)
check("multi-word search finds item", any(x.item_code == "KGS-T-BOOK1" for x in s), s)
check("search needs 2+ chars", api.search_items("v", SRC) == [])
check("search hides disabled items", not any(x.item_code == "KGS-T-DISABLED" for x in api.search_items("Test Disabled", SRC)))
lv = api.stock_levels(json.dumps(["KGS-T-BOOK1", ZERO]), SRC, DST)
check("stock_levels returns both", lv["KGS-T-BOOK1"]["available"] > 0 and lv[ZERO]["valuation_ok"] == 0, lv)

# ── create_transfer ──────────────────────────────────────────────────────────
src0, dst0 = bin_qty("KGS-T-BOOK1", SRC), bin_qty("KGS-T-BOOK1", DST)
pen0 = bin_qty("KGS-T-PEN", SRC)
cref = ref()
items = [{"item_code": "KGS-T-BOOK1", "qty": 2, "uom": "PKT"}, {"item_code": "KGS-T-BOOK1", "qty": 5, "uom": "PCS"},
	{"item_code": "KGS-T-PEN", "qty": 3, "uom": "Nos"}]
res = api.create_transfer(SRC, DST, json.dumps(items), cref, remarks="Van driver Ramesh")
frappe.db.commit()
check("transfer ok", res.get("ok") == 1 and res.get("docstatus") == 1, res)
name = res.get("name")
check("source moved 205 PCS", bin_qty("KGS-T-BOOK1", SRC) == src0 - 205, (src0, bin_qty("KGS-T-BOOK1", SRC)))
check("target got 205 PCS", bin_qty("KGS-T-BOOK1", DST) == dst0 + 205)
check("pens moved 3", bin_qty("KGS-T-PEN", SRC) == pen0 - 3)
se = frappe.get_doc("Stock Entry", name)
check("purpose Material Transfer", se.purpose == "Material Transfer" and se.stock_entry_type == "Material Transfer")
check("posted today, not back-dated", str(se.posting_date) == nowdate(), se.posting_date)
check("owner is the staff user", se.owner == "staff1@example.com", se.owner)
check("remarks keep note + ref tag", "Van driver Ramesh" in se.remarks and cref in se.remarks, se.remarks)
check("PKT line transfer_qty 200", any(d.uom == "PKT" and d.transfer_qty == 200 for d in se.items))
check("pdf url uses slip or Standard", "download_pdf" in res["pdf_url"])

res2 = api.create_transfer(SRC, DST, json.dumps(items), cref)
frappe.db.commit()
check("retry with same ref → already, same name", res2.get("already") == 1 and res2.get("name") == name, res2)
check("retry moved nothing", bin_qty("KGS-T-BOOK1", SRC) == src0 - 205)

# ── refusals ─────────────────────────────────────────────────────────────────
before = frappe.db.count("Stock Entry")
avail = bin_qty("KGS-T-BOOK1", SRC)
r = api.create_transfer(SRC, DST, json.dumps([{"item_code": "KGS-T-BOOK1", "qty": avail + 1, "uom": "PCS"}]), ref())
check("over-available → problem, not created", r.get("ok") == 0 and "Only" in r["problems"][0]["message"], r)
r = api.create_transfer(SRC, DST, json.dumps([{"item_code": "KGS-T-BOOK1", "qty": avail - 10, "uom": "PCS"},
	{"item_code": "KGS-T-BOOK1", "qty": 1, "uom": "PKT"}]), ref())
check("over-available across two lines of one item", r.get("ok") == 0, r)
r = api.create_transfer(SRC, DST, json.dumps([{"item_code": ZERO, "qty": 1, "uom": "PCS"}]), ref())
check("zero-cost item refused", r.get("ok") == 0 and "cost price" in r["problems"][0]["message"], r)
r = api.create_transfer(SRC, DST, json.dumps([{"item_code": NOSTOCK, "qty": 1}]), ref())
check("no-stock item refused", r.get("ok") == 0, r)
r = api.create_transfer(SRC, DST, json.dumps([{"item_code": "KGS-T-DISABLED", "qty": 1}]), ref())
check("disabled item refused", r.get("ok") == 0, r)
r = api.create_transfer(SRC, DST, json.dumps([{"item_code": "KGS-T-PEN", "qty": 1.5, "uom": "Nos"}]), ref())
check("fraction of a whole-number UOM refused", r.get("ok") == 0 and "whole" in r["problems"][0]["message"], r)
r = api.create_transfer(SRC, DST, json.dumps([{"item_code": "KGS-T-PEN", "qty": 1, "uom": "Box"}]), ref())
check("unit not on the item refused", r.get("ok") == 0, r)
r = api.create_transfer(SRC, DST, json.dumps([{"item_code": "KGS-T-PEN", "qty": 0}]), ref())
check("zero qty refused", r.get("ok") == 0, r)
r = api.create_transfer(SRC, DST, json.dumps([{"item_code": "NOPE-XYZ", "qty": 1}]), ref())
check("unknown item refused", r.get("ok") == 0, r)
check("same warehouse refused", raises(lambda: api.create_transfer(SRC, SRC, json.dumps(items), ref()), frappe.ValidationError))
check("transit warehouse refused", raises(lambda: api.create_transfer(SRC, "Goods In Transit - DCV", json.dumps(items), ref()), frappe.ValidationError))
check("group warehouse refused", raises(lambda: api.create_transfer(SRC, "All Warehouses - DCV", json.dumps(items), ref()), frappe.ValidationError))
check("bad client_ref refused", raises(lambda: api.create_transfer(SRC, DST, json.dumps(items), "x"), frappe.ValidationError))
check("empty list refused", raises(lambda: api.create_transfer(SRC, DST, "[]", ref()), frappe.ValidationError))
too_many = [{"item_code": "KGS-T-PEN", "qty": 1}] * (api.MAX_LINES + 1)
check("over MAX_LINES refused", raises(lambda: api.create_transfer(SRC, DST, json.dumps(too_many), ref()), frappe.ValidationError))
lock_ref = ref()
lk = frappe.cache.make_key(f"kgs_staff_xfer_lock:staff1@example.com:{lock_ref}")
frappe.cache.set(lk, 1, ex=30)
check("in-flight lock refuses a parallel save", raises(lambda: api.create_transfer(SRC, DST, json.dumps(items), lock_ref), frappe.ValidationError))
frappe.cache.delete(lk)
frappe.db.rollback()
check("no Stock Entry created by any refusal", frappe.db.count("Stock Entry") == before, (before, frappe.db.count("Stock Entry")))

# ── lists / detail ───────────────────────────────────────────────────────────
mine = api.my_transfers("mine", 30)
check("my_transfers lists it", any(t.name == name for t in mine))
check("staff cannot widen to all", all(t.owner == "staff1@example.com" for t in api.my_transfers("all", 30)))
d = api.get_transfer(name)
check("detail strips ref tag from remarks", d["remarks"] == "Van driver Ramesh", d["remarks"])
check("detail lines", len(d["items"]) == 3)
frappe.set_user("mgr1@example.com")
check("manager sees everyone", any(t.owner == "staff1@example.com" for t in api.my_transfers("all", 30)))
check("manager boot is_manager=1", api.boot()["is_manager"] == 1)

# ── rate limit ───────────────────────────────────────────────────────────────
frappe.set_user("staff1@example.com")
old = api.RATE_LIMIT_PER_MINUTE
api.RATE_LIMIT_PER_MINUTE = 3
import time
k = frappe.cache.make_key(f"kgs_staff_rl:staff1@example.com:{int(time.time() // 60)}")
frappe.cache.delete(k)
msg = None
for _ in range(5):
	try:
		api.boot()
	except frappe.TooManyRequestsError as e:
		msg = str(e)
check("per-user rate limit trips", msg is not None)
api.RATE_LIMIT_PER_MINUTE = old
frappe.cache.delete(k)

# ── print format ─────────────────────────────────────────────────────────────
frappe.set_user("Administrator")
from frappe.modules.import_file import import_file_by_path

import_file_by_path(frappe.get_app_path("trustbit_school_book_seller", "trustbit_school_book", "print_format",
	"kgs_transfer_slip", "kgs_transfer_slip.json"), force=True)
frappe.db.commit()
check("print format imported", frappe.db.get_value("Print Format", "KGS Transfer Slip", "standard") == "Yes")
html = frappe.get_print("Stock Entry", name, print_format="KGS Transfer Slip", no_letterhead=1)
check("slip renders route + lines", SRC in html and DST in html and "Test Viva Maths 3" in html and "200" in html, html[:300])
check("slip hides the ref tag", cref not in html and "Van driver Ramesh" in html)
check("slip shows signature boxes", "Received by" in html)
open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "slip_render.html"), "w").write(html)

frappe.db.set_single_value("Stock Settings", "allow_negative_stock", orig_neg)
frappe.db.commit()
print(f"\n{sum(1 for r in RESULTS if r[1])}/{len(RESULTS)} passed; transfer {name}")
