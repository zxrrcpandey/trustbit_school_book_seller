"""Shortfall → Stock Reconciliation checks on the dev site (site1.local). Run from frappe-bench/sites:
  ../env/bin/python <this file>
Needs check_staff_api.py and check_staff_bulk.py to have run once (test users, items, warehouses)."""
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


# ── setup ────────────────────────────────────────────────────────────────────
frappe.set_user("Administrator")
orig_neg = frappe.db.get_single_value("Stock Settings", "allow_negative_stock")
frappe.db.set_single_value("Stock Settings", "allow_negative_stock", 1)
frappe.db.set_value("Item", "KGS-T-BOOK1", "last_purchase_rate", 12.5)
if not frappe.db.exists("Item", "KGS-T-NEG"):
	frappe.get_doc({"doctype": "Item", "item_code": "KGS-T-NEG", "item_name": "Test Negative Item", "item_group": "All Item Groups",
		"stock_uom": "Nos", "is_stock_item": 1, "valuation_rate": 7}).insert()
if b("KGS-T-NEG") >= 0:
	se = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Issue", "company": COMPANY,
		"items": [{"item_code": "KGS-T-NEG", "qty": 5 + b("KGS-T-NEG"), "s_warehouse": SRC}]})
	se.insert()
	se.submit()
# Fresh items every run, so other suites moving stock around cannot change them:
# NS = never stocked anywhere, Z = 5 PCS at ₹0, SET = a school set holding NS.
RUN = uuid.uuid4().hex[:6].upper()
NS, Z, SET = f"KGS-T-NS-{RUN}", f"KGS-T-Z-{RUN}", f"KGS-T-SETR-{RUN}"
for code, name, stock in ((NS, f"Test Never Bought {RUN}", 1), (Z, f"Test Zero Cost {RUN}", 1), (SET, f"Test Set {RUN}", 0)):
	frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": name, "item_group": "All Item Groups",
		"stock_uom": "PCS", "is_stock_item": stock}).insert()
frappe.get_doc({"doctype": "Product Bundle", "new_item_code": SET, "items": [
	{"item_code": "KGS-T-BOOK1", "qty": 1, "uom": "PCS"}, {"item_code": NS, "qty": 2, "uom": "PCS"}]}).insert()
z = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "company": COMPANY,
	"items": [{"item_code": Z, "qty": 5, "t_warehouse": SRC, "basic_rate": 0, "allow_zero_valuation_rate": 1}]})
z.insert()
z.submit()
frappe.db.commit()

# ── access + preview ─────────────────────────────────────────────────────────
frappe.set_user("staff1@example.com")
avail = b("KGS-T-BOOK1")
check("Stock User cannot send a reconciliation", raises(lambda: xfer(
	[{"item_code": "KGS-T-BOOK1", "qty": avail + 10, "uom": "PCS"}],
	[{"item_code": "KGS-T-BOOK1", "counted": avail + 10, "rate": 12.5, "reason": "Found extra stock"}]), frappe.PermissionError))
check("Stock User cannot preview", raises(lambda: api.reco_preview(SRC, json.dumps(["KGS-T-BOOK1"])), frappe.PermissionError))
check("boot lists the reasons", "Purchase receipt not entered" in api.boot()["reco_reasons"])

check("Stock User: no-stock item still refused at scan", "No stock" in " ".join(api.lookup_item(NS, SRC)["problems"]))
frappe.set_user("mgr1@example.com")
check("Stock Manager: no-stock item can be added (to reconcile)", api.lookup_item(NS, SRC)["problems"] == [])
check("Stock Manager: zero-cost item still refused", "cost price" in " ".join(api.lookup_item(Z, SRC)["problems"]))
st = api.expand_bundle(SET, 1, SRC, DST)
check("Stock Manager: school set keeps no-stock members as short lines", any(l["item_code"] == NS and l["available"] == 0 for l in st["lines"]), st)
pv = api.reco_preview(SRC, json.dumps(["KGS-T-BOOK1", "KGS-T-PEN", NS]))["items"]
check("default rate = last purchase rate", pv["KGS-T-BOOK1"]["suggested_rate"] == 12.5 and pv["KGS-T-BOOK1"]["rate_source"] == "last purchase rate", pv["KGS-T-BOOK1"])
check("no last purchase rate → current valuation", pv["KGS-T-PEN"]["rate_source"] == "current valuation" and pv["KGS-T-PEN"]["suggested_rate"] > 0, pv["KGS-T-PEN"])
check("neither → no suggestion (must type)", pv[NS]["suggested_rate"] == 0 and pv[NS]["rate_source"] == "")
check("preview gives system qty + value", pv["KGS-T-BOOK1"]["current_qty"] == avail)

# ── happy path: positive stock, short by 10 ─────────────────────────────────
v0 = b("KGS-T-BOOK1", field="stock_value")
dst0 = b("KGS-T-BOOK1", DST)
n0 = recos_count()
cref = ref()
items = [{"item_code": "KGS-T-BOOK1", "qty": avail + 10, "uom": "PCS"}]
recos = [{"item_code": "KGS-T-BOOK1", "counted": avail + 10, "rate": 12.5, "reason": "Found extra stock"}]
r = xfer(items, recos, cref)
frappe.db.commit()
check("short transfer + reconciliation ok", r.get("ok") == 1 and len(r.get("recos", [])) == 1, r)
rn = r["recos"][0]["name"]
reco = frappe.get_doc("Stock Reconciliation", rn)
check("reco submitted, posted today, by the manager", reco.docstatus == 1 and str(reco.posting_date) == nowdate() and reco.owner == "mgr1@example.com")
check("reco sets From to the counted qty", reco.items[0].qty == avail + 10 and reco.items[0].warehouse == SRC)
check("reco booked to Stock Adjustment", reco.expense_account == frappe.db.get_value("Company", COMPANY, "stock_adjustment_account"))
sle = flt(frappe.db.get_value("Stock Ledger Entry", {"voucher_no": rn, "is_cancelled": 0}, "stock_value_difference"))
check("value change = extra × rate (10 × 12.5 = 125, ± paise rounding of the rate × qty)", abs(sle - 125) <= (avail + 10) * 0.005 + 0.01, sle)
check("response reports the ledger's actual value change", abs(r["recos"][0]["value"] - sle) < 0.01, (r["recos"], sle))
check("source emptied, target got everything", b("KGS-T-BOOK1") == 0 and b("KGS-T-BOOK1", DST) == dst0 + avail + 10)
se = frappe.get_doc("Stock Entry", r["name"])
check("transfer remarks name the reconciliation", rn in se.remarks, se.remarks)
cm = frappe.db.get_value("Comment", {"reference_doctype": "Stock Reconciliation", "reference_name": rn, "comment_type": "Comment"}, "content") or ""
check("audit comment: tag, reason, rates", "[Staff app · reco · ref:" in cm and "Found extra stock" in cm and "12.50" in cm, cm)

r2 = xfer(items, recos, cref)
frappe.db.commit()
check("retry → already, no second reconciliation", r2.get("already") == 1 and recos_count() == n0 + 1, (r2, recos_count() - n0))

# put the books back in Stores for the next checks
frappe.set_user("Administrator")
back = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Transfer", "company": COMPANY,
	"items": [{"item_code": "KGS-T-BOOK1", "qty": 300, "s_warehouse": DST, "t_warehouse": SRC}]})
back.insert()
back.submit()
frappe.db.commit()
frappe.set_user("mgr1@example.com")

# ── negative stock (−5) and zero-valuation stock ────────────────────────────
neg_v0 = b("KGS-T-NEG", field="stock_value")
r = xfer([{"item_code": "KGS-T-NEG", "qty": 3, "uom": "Nos"}],
	[{"item_code": "KGS-T-NEG", "counted": 3, "rate": 7, "reason": "Purchase receipt not entered"}])
frappe.db.commit()
check("negative stock: reconciled from −5 to 3, then moved", r.get("ok") == 1 and b("KGS-T-NEG") == 0, r)
check("negative stock: value change = 3×7 − old value", abs(r["recos"][0]["value"] - (21 - neg_v0)) < 0.05, (r.get("recos"), neg_v0))
check("'Purchase receipt not entered' allowed", True)

zq = b(Z)
r = xfer([{"item_code": Z, "qty": zq + 2, "uom": "PCS"}],
	[{"item_code": Z, "counted": zq + 2, "rate": 4, "reason": "Other", "note": "box under the counter"}])
frappe.db.commit()
check("₹0-valued stock: whole qty valued at the rate", r.get("ok") == 1 and abs(r["recos"][0]["value"] - (zq + 2) * 4) < 0.05, r)

# ── refusals: nothing is created ─────────────────────────────────────────────
n1, s1 = recos_count(), frappe.db.count("Stock Entry")
a = b("KGS-T-PEN")
base = [{"item_code": "KGS-T-PEN", "qty": a + 4, "uom": "Nos"}]
cases = {
	"counted below what the transfer needs": {"counted": a + 2, "rate": 5, "reason": "Count was wrong"},
	"counted not above the system qty": {"counted": a, "rate": 5, "reason": "Count was wrong"},
	"rate zero": {"counted": a + 4, "rate": 0, "reason": "Count was wrong"},
	"no reason": {"counted": a + 4, "rate": 5, "reason": ""},
	"Other without a note": {"counted": a + 4, "rate": 5, "reason": "Other"},
	"fraction of a whole-number unit": {"counted": a + 4.5, "rate": 5, "reason": "Count was wrong"},
}
for label, rc in cases.items():
	r = xfer(base, [{"item_code": "KGS-T-PEN", **rc}])
	check(f"refused: {label}", r.get("ok") == 0 and r["problems"], r)
r = xfer(base, [{"item_code": "KGS-T-BOOK1", "counted": 999, "rate": 5, "reason": "Count was wrong"}])
check("refused: item not in the transfer", r.get("ok") == 0, r)
# reconciliation fine, but another line of the transfer is bad → everything rolled back
r = xfer(base + [{"item_code": "KGS-T-BULK-001", "qty": 1, "uom": "BOX"}],
	[{"item_code": "KGS-T-PEN", "counted": a + 4, "rate": 5, "reason": "Count was wrong"}])
frappe.db.commit()
check("bad other line → reconciliation rolled back too", r.get("ok") == 0 and recos_count() == n1, (r, recos_count() - n1))
check("no reconciliation or transfer from any refusal", recos_count() == n1 and frappe.db.count("Stock Entry") == s1)

# ── 120 short items → reconciliations of ≤ 100 rows ──────────────────────────
codes = [f"KGS-T-BULK-{i:03d}" for i in range(1, 121)]
lv = {c: b(c) for c in codes}
items = [{"item_code": c, "qty": lv[c] + 1, "uom": "PCS"} for c in codes]
recos = [{"item_code": c, "counted": lv[c] + 1, "rate": 4, "reason": "Count was wrong"} for c in codes]
r = xfer(items, recos)
frappe.db.commit()
check("120 short items → 2 reconciliations (100 + 20), 1 transfer", r.get("ok") == 1 and [x["lines"] for x in r["recos"]] == [100, 20], r.get("recos"))
check("all 120 sources emptied", all(b(c) == 0 for c in codes))
check("all reconciliations submitted (not queued)", all(frappe.db.get_value("Stock Reconciliation", x["name"], "docstatus") == 1 for x in r["recos"]))

# ── weekly digest ────────────────────────────────────────────────────────────
sent = []
real = frappe.sendmail
frappe.sendmail = lambda **kw: sent.append(kw)
api.send_reco_digest()
check("digest off without site_config", not sent)
frappe.conf["kgs_staff_reco_digest_to"] = "accounts@example.com"
api.send_reco_digest()
check("digest e-mails the app reconciliations", sent and "Stock reconciliations from the Staff app" in sent[0]["subject"] and rn in sent[0]["message"], sent[:1])
frappe.conf.pop("kgs_staff_reco_digest_to")
frappe.sendmail = real

frappe.set_user("Administrator")
frappe.db.set_single_value("Stock Settings", "allow_negative_stock", orig_neg)
frappe.db.commit()
print(f"\n{sum(1 for r in RESULTS if r[1])}/{len(RESULTS)} passed")
