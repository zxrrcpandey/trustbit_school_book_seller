"""Option B checks (short stock: transfer what the system has, add the extra in To) on the
dev site (site1.local). Run from frappe-bench/sites:  ../env/bin/python <this file>
Needs check_staff_api.py and check_staff_bulk.py to have run once (users, items, warehouses).
Makes fresh items every run, so other suites moving test stock cannot change the numbers."""
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
RUN = uuid.uuid4().hex[:6].upper()


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


def b(item, wh=SRC, field="actual_qty"):
	return flt(frappe.db.get_value("Bin", {"item_code": item, "warehouse": wh}, field))


def recos_count():
	return frappe.db.count("Stock Reconciliation")


def xfer(items, recos, cref=None):
	return api.create_transfer(SRC, DST, json.dumps(items), cref or ref(), recos=json.dumps(recos))


def item(suffix, uom="PCS", stock=1, lpr=0, valuation=0):
	code = f"KGS-T-{suffix}-{RUN}"
	frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": f"Test {suffix} {RUN}", "item_group": "All Item Groups",
		"stock_uom": uom, "is_stock_item": stock, "valuation_rate": valuation}).insert()
	if lpr:
		frappe.db.set_value("Item", code, "last_purchase_rate", lpr)
	return code


def entry(kind, code, qty, rate=10, wh=SRC, zero=False):
	row = {"item_code": code, "qty": qty, "basic_rate": rate, "allow_zero_valuation_rate": 1 if zero else 0}
	row["t_warehouse" if kind == "Material Receipt" else "s_warehouse"] = wh
	se = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": kind, "company": COMPANY, "items": [row]})
	se.insert()
	se.submit()


def reco_rows(name):
	return frappe.get_all("Stock Reconciliation Item", filters={"parent": name},
		fields=["item_code", "warehouse", "current_qty", "qty", "quantity_difference"])


# ── setup ────────────────────────────────────────────────────────────────────
frappe.set_user("Administrator")
orig_neg = frappe.db.get_single_value("Stock Settings", "allow_negative_stock")
frappe.db.set_single_value("Stock Settings", "allow_negative_stock", 1)
A = item("A", lpr=54)                       # Ex 1: system 5, count 8
entry("Material Receipt", A, 5, rate=54)
D = item("D", lpr=20)                       # Ex 2: destination already has 10
entry("Material Receipt", D, 5, rate=20)
entry("Material Receipt", D, 10, rate=20, wh=DST)
NS = item("NS")                             # Ex 3: never stocked, no price anywhere
NEG = item("NEG", uom="Nos", valuation=7)   # Ex 4: From in minus (−20)
entry("Material Issue", NEG, 20)
L = item("L", lpr=3)                        # Ex 5: system 5, count 6, move 8
entry("Material Receipt", L, 5, rate=3)
DM = item("DM", lpr=6, valuation=6)         # Ex 6: destination −4 (works)
entry("Material Receipt", DM, 5, rate=6)
entry("Material Issue", DM, 4, wh=DST)
DB = item("DB", lpr=6, valuation=6)         # Ex 6b: destination −20 (blocked)
entry("Material Receipt", DB, 5, rate=6)
entry("Material Issue", DB, 20, wh=DST)
MORE = item("MORE", lpr=2)                  # counted more than moving
entry("Material Receipt", MORE, 5, rate=2)
Z = item("Z")                               # 5 at ₹0 in From: refused for everyone
entry("Material Receipt", Z, 5, rate=0, zero=True)
SET = item("SET", stock=0)
frappe.get_doc({"doctype": "Product Bundle", "new_item_code": SET, "items": [
	{"item_code": A, "qty": 1, "uom": "PCS"}, {"item_code": NS, "qty": 2, "uom": "PCS"}]}).insert()
frappe.db.commit()

# ── access ───────────────────────────────────────────────────────────────────
frappe.set_user("staff1@example.com")
check("Stock User cannot add extra stock", raises(lambda: xfer([{"item_code": A, "qty": 8}],
	[{"item_code": A, "counted": 8, "rate": 54, "reason": "Found extra stock"}]), frappe.PermissionError))
check("Stock User cannot preview", raises(lambda: api.reco_preview(SRC, json.dumps([A]), DST), frappe.PermissionError))
check("Stock User: no-stock item refused at scan", "No stock" in " ".join(api.lookup_item(NS, SRC)["problems"]))
frappe.set_user("mgr1@example.com")
check("Manager: no-stock item can be added", api.lookup_item(NS, SRC)["problems"] == [])
check("Manager: zero-cost item still refused", "cost price" in " ".join(api.lookup_item(Z, SRC)["problems"]))
st = api.expand_bundle(SET, 1, SRC, DST)
check("Manager: school set keeps no-stock members as short lines", any(l["item_code"] == NS and l["available"] == 0 for l in st["lines"]))
pv = api.reco_preview(SRC, json.dumps([A, NS, D]), DST)["items"]
check("preview: last purchase rate first", pv[A]["suggested_rate"] == 54 and pv[A]["rate_source"] == "last purchase rate")
check("preview: no price anywhere → empty", pv[NS]["suggested_rate"] == 0 and pv[NS]["rate_source"] == "")
check("preview: destination qty", pv[D]["dest_qty"] == 10, pv[D])

# ── Example 1: system 5, count 8, move 8 ─────────────────────────────────────
n0 = recos_count()
cref = ref()
r = xfer([{"item_code": A, "qty": 8, "uom": "PCS"}], [{"item_code": A, "counted": 8, "rate": 54, "reason": "Found extra stock"}], cref)
frappe.db.commit()
check("Ex1 ok: one transfer + one reconciliation", r.get("ok") == 1 and r.get("name") and len(r["recos"]) == 1, r)
se = frappe.get_doc("Stock Entry", r["name"])
check("Ex1 transfer moved 5 (what the system had)", len(se.items) == 1 and se.items[0].transfer_qty == 5, [(d.item_code, d.transfer_qty) for d in se.items])
rr = reco_rows(r["recos"][0]["name"])
check("Ex1 reconciliation is in the DESTINATION, 5 → 8, difference 3", rr[0].warehouse == DST and rr[0].current_qty == 5
	and rr[0].qty == 8 and flt(rr[0].quantity_difference) == 3, rr)
check("Ex1 value change 3 × ₹54 = ₹162", abs(r["recos"][0]["value"] - 162) < 0.05, r["recos"])
check("Ex1 From 0, To 8", b(A) == 0 and b(A, DST) == 8)
check("Ex1 transfer remarks name the reconciliation", r["recos"][0]["name"] in se.remarks and "Extra added in" in se.remarks, se.remarks)
reco = frappe.get_doc("Stock Reconciliation", r["recos"][0]["name"])
check("Ex1 reconciliation posted today by the manager, Stock Adjustment", reco.docstatus == 1 and str(reco.posting_date) == nowdate()
	and reco.owner == "mgr1@example.com" and reco.expense_account == frappe.db.get_value("Company", COMPANY, "stock_adjustment_account"))
cm = frappe.db.get_value("Comment", {"reference_doctype": "Stock Reconciliation", "reference_name": reco.name, "comment_type": "Comment"}, "content") or ""
check("Ex1 audit comment", "[Staff app · reco · ref:" in cm and "transferred 5" in cm and "extra 3 added in" in cm and "Found extra stock" in cm, cm)
r2 = xfer([{"item_code": A, "qty": 8, "uom": "PCS"}], [{"item_code": A, "counted": 8, "rate": 54, "reason": "Found extra stock"}], cref)
frappe.db.commit()
check("Ex1 retry → already, nothing added twice", r2.get("already") == 1 and recos_count() == n0 + 1 and b(A, DST) == 8, r2)

# ── Example 2: destination already has 10 ────────────────────────────────────
r = xfer([{"item_code": D, "qty": 8}], [{"item_code": D, "counted": 8, "rate": 20, "reason": "Count was wrong"}])
frappe.db.commit()
rr = reco_rows(r["recos"][0]["name"])
check("Ex2 destination 15 → 18, difference 3", rr[0].current_qty == 15 and rr[0].qty == 18 and flt(rr[0].quantity_difference) == 3, rr)
check("Ex2 existing units keep value: change = 3 × ₹20 = ₹60", abs(r["recos"][0]["value"] - 60) < 0.05, r["recos"])

# ── Example 3: From has 0 → reconciliation only ──────────────────────────────
s0 = frappe.db.count("Stock Entry")
cref3 = ref()
r = xfer([{"item_code": NS, "qty": 8}], [{"item_code": NS, "counted": 8, "rate": 9, "reason": "Found extra stock"}], cref3)
frappe.db.commit()
check("Ex3 no transfer, only the reconciliation", r.get("ok") == 1 and r.get("name") is None and len(r["recos"]) == 1
	and frappe.db.count("Stock Entry") == s0, r)
check("Ex3 To 0 → 8, value ₹72", b(NS, DST) == 8 and abs(r["recos"][0]["value"] - 72) < 0.05)
r3 = xfer([{"item_code": NS, "qty": 8}], [{"item_code": NS, "counted": 8, "rate": 9, "reason": "Found extra stock"}], cref3)
frappe.db.commit()
check("Ex3 retry of a reconciliation-only request → already", r3.get("already") == 1 and b(NS, DST) == 8, r3)

# ── Example 4: From in minus (−20) ───────────────────────────────────────────
r = xfer([{"item_code": NEG, "qty": 8, "uom": "Nos"}], [{"item_code": NEG, "counted": 8, "rate": 7, "reason": "Purchase receipt not entered"}])
frappe.db.commit()
check("Ex4 no transfer (system has nothing to move)", r.get("ok") == 1 and r.get("name") is None, r)
check("Ex4 From stays −20 (not fixed by the app)", b(NEG) == -20)
check("Ex4 To +8, value change only 8 × ₹7 = ₹56", b(NEG, DST) == 8 and abs(r["recos"][0]["value"] - 56) < 0.05, r["recos"])
cm = frappe.db.get_value("Comment", {"reference_doctype": "Stock Reconciliation", "reference_name": r["recos"][0]["name"], "comment_type": "Comment"}, "content") or ""
check("Ex4 comment says From still shows the minus", "still shows -20" in cm, cm)

# ── Example 5: count 6, wanted 8 — the phone sends the reduced line (6) ─────
r = xfer([{"item_code": L, "qty": 6}], [{"item_code": L, "counted": 6, "rate": 3, "reason": "Count was wrong"}])
frappe.db.commit()
se = frappe.get_doc("Stock Entry", r["name"])
rr = reco_rows(r["recos"][0]["name"])
check("Ex5 transfer 5 + extra 1", se.items[0].transfer_qty == 5 and flt(rr[0].quantity_difference) == 1 and b(L, DST) == 6, (r, rr))

# ── Example 6: destination −4 works; −20 is refused, nothing saved ───────────
r = xfer([{"item_code": DM, "qty": 8}], [{"item_code": DM, "counted": 8, "rate": 6, "reason": "Found extra stock"}])
frappe.db.commit()
rr = reco_rows(r["recos"][0]["name"]) if r.get("ok") else []
check("Ex6 destination −4: transfer 5 → 1, then 1 → 4 (difference 3)", r.get("ok") == 1 and rr and rr[0].current_qty == 1 and rr[0].qty == 4, (r, rr))
n1, s1, src_db = recos_count(), frappe.db.count("Stock Entry"), b(DB)
r = xfer([{"item_code": DB, "qty": 8}], [{"item_code": DB, "counted": 8, "rate": 6, "reason": "Found extra stock"}])
frappe.db.commit()
check("Ex6b destination −20 refused in plain words", r.get("ok") == 0 and "is in minus" in r["problems"][0]["message"], r)
check("Ex6b nothing saved (transfer rolled back too)", recos_count() == n1 and frappe.db.count("Stock Entry") == s1 and b(DB) == src_db)

# ── counted more than moving: extra = what the move needs ───────────────────
r = xfer([{"item_code": MORE, "qty": 8}], [{"item_code": MORE, "counted": 10, "rate": 2, "reason": "Found extra stock"}])
frappe.db.commit()
rr = reco_rows(r["recos"][0]["name"])
check("count 10, move 8, system 5 → transfer 5 + extra 3 (not 5)", flt(rr[0].quantity_difference) == 3 and b(MORE, DST) == 8 and b(MORE) == 0, rr)

# ── refusals ─────────────────────────────────────────────────────────────────
frappe.set_user("Administrator")
P = item("P", uom="Nos", lpr=5)
entry("Material Receipt", P, 5, rate=5)
frappe.db.commit()
frappe.set_user("mgr1@example.com")
base = [{"item_code": P, "qty": 9}]
cases = {
	"count not more than the system": {"counted": 5, "rate": 5, "reason": "Count was wrong"},
	"price zero": {"counted": 9, "rate": 0, "reason": "Count was wrong"},
	"no reason": {"counted": 9, "rate": 5, "reason": ""},
	"Other without a note": {"counted": 9, "rate": 5, "reason": "Other"},
	"fraction of a whole-number unit": {"counted": 8.5, "rate": 5, "reason": "Count was wrong"},
}
n2, s2 = recos_count(), frappe.db.count("Stock Entry")
for label, rc in cases.items():
	r = xfer(base, [{"item_code": P, **rc}])
	check(f"refused: {label}", r.get("ok") == 0 and r["problems"], r)
check("refused: item not in the transfer", xfer(base, [{"item_code": A, "counted": 9, "rate": 5, "reason": "Count was wrong"}]).get("ok") == 0)
r = xfer(base + [{"item_code": "KGS-T-BULK-001", "qty": 1, "uom": "BOX"}], [{"item_code": P, "counted": 9, "rate": 5, "reason": "Count was wrong"}])
frappe.db.commit()
check("bad other line → nothing saved", r.get("ok") == 0 and recos_count() == n2 and frappe.db.count("Stock Entry") == s2, r)

# ── 120 short items → destination reconciliations of ≤ 100 rows ──────────────
codes = [f"KGS-T-BULK-{i:03d}" for i in range(1, 121)]
lv = {c: b(c) for c in codes}
dv = {c: b(c, DST) for c in codes}
r = xfer([{"item_code": c, "qty": max(lv[c], 0) + 1, "uom": "PCS"} for c in codes],
	[{"item_code": c, "counted": max(lv[c], 0) + 1, "rate": 4, "reason": "Count was wrong"} for c in codes])
frappe.db.commit()
check("120 short items → reconciliations 100 + 20", r.get("ok") == 1 and [x["lines"] for x in r["recos"]] == [100, 20], r.get("recos") or r)
check("each item: To + (system + 1)", all(b(c, DST) == dv[c] + max(lv[c], 0) + 1 for c in codes))

# ── weekly digest ────────────────────────────────────────────────────────────
sent = []
real = frappe.sendmail
frappe.sendmail = lambda **kw: sent.append(kw)
api.send_reco_digest()
check("digest off without site_config", not sent)
frappe.conf["kgs_staff_reco_digest_to"] = "accounts@example.com"
api.send_reco_digest()
check("digest e-mails the app reconciliations", sent and "Stock reconciliations from the Staff app" in sent[0]["subject"], sent[:1])
frappe.conf.pop("kgs_staff_reco_digest_to")
frappe.sendmail = real

frappe.set_user("Administrator")
frappe.db.set_single_value("Stock Settings", "allow_negative_stock", orig_neg)
frappe.db.commit()
print(f"\n{sum(1 for r in RESULTS if r[1])}/{len(RESULTS)} passed")
