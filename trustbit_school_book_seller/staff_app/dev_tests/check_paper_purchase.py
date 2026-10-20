"""Receipts and Bills from paper (staff_app/paper_purchase.py + paper.py) on a
THROWAWAY site with India Compliance (made by setup_paper_purchase_site.py).
Run from frappe-bench/sites:
    ../env/bin/python ../apps/trustbit_school_book_seller/trustbit_school_book_seller/staff_app/dev_tests/check_paper_purchase.py paper.local
No AI is called (fake provider, in-process site_config); read jobs run in this
process. Creates test items / users / POs and real PRs + PIs on that site."""
import base64
import io
import json
import sys
import uuid

import frappe
from frappe.utils import add_days, flt, nowdate

SITE = sys.argv[1] if len(sys.argv) > 1 else "paper.local"
if SITE in ("splashbox.in", "site1.local"):
	raise SystemExit("refusing: this script is for a throwaway site only")
frappe.init(site=SITE, sites_path=".")
frappe.connect()

from trustbit_school_book_seller.staff_app import paper  # noqa: E402
from trustbit_school_book_seller.staff_app import paper_match as pm  # noqa: E402
from trustbit_school_book_seller.staff_app import paper_purchase as pp  # noqa: E402
from trustbit_school_book_seller.staff_app import paper_read as pr  # noqa: E402

RESULTS = []
C, ABBR = "KGS Test Stores", "KGS"
WH = f"Stores - {ABBR}"
SEL, OUT, UNREG = "Selina Test Publishers", "Out State Books Pvt Ltd", "Unregistered Paper Mart"
DOLLY, OTHER, OWNER = "pp_dolly@example.com", "pp_other@example.com", "pp_owner@example.com"
FREIGHT = f"Freight & Forwarding Charges - {ABBR}"
RUN = uuid.uuid4().hex[:6].upper()


def check(name, cond, detail=""):
	RESULTS.append((name, bool(cond), detail))
	print(("PASS " if cond else "FAIL ") + name + (f" — {detail}" if detail and not cond else ""))


def raises(fn):
	try:
		fn()
	except Exception as e:
		frappe.db.rollback()
		return str(e) or type(e).__name__
	return None


def as_user(u):
	import time

	frappe.set_user(u)
	frappe.local.request_ip = "127.0.0.1"
	w = int(time.time() // 60)
	for x in (w, w - 1):
		frappe.cache.delete(frappe.cache.make_key(f"kgs_staff_rl:{u}:{x}"))


def jpeg():
	from PIL import Image

	b = io.BytesIO()
	Image.new("RGB", (1200, 1600), "white").save(b, "JPEG")
	return base64.b64encode(b.getvalue()).decode()


# ── masters ──────────────────────────────────────────────────────────────────
frappe.set_user("Administrator")
for h in ("49011010", "48201010"):
	if not frappe.db.exists("GST HSN Code", h):
		frappe.get_doc({"doctype": "GST HSN Code", "hsn_code": h, "description": h}).insert()
group = "Products" if frappe.db.exists("Item Group", "Products") else frappe.db.get_value("Item Group", {"is_group": 0}, "name")
ITEMS = {
	"BK-PHY9": ("Selina Concise Physics 9", "49011010", "Nil-Rated - KGS", 650),
	"BK-PHY9-OLD": ("Selina Concise Physics 9", "49011010", "Nil-Rated - KGS", 0),  # a dead twin
	"BK-CHE10": ("Selina Concise Chemistry 10", "49011010", "Nil-Rated - KGS", 500),
	"BK-MAT6": ("Selina Mathematics 6", "49011010", "Nil-Rated - KGS", 340),
	"ST-REG": ("Classmate Register 200 Pages", "48201010", "GST 18% - KGS", 60),
}
for code, (name, hsn, tmpl, mrp) in ITEMS.items():
	if not frappe.db.exists("Item", code):
		frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": name, "item_group": group, "stock_uom": "Nos",
			"is_stock_item": 1, "gst_hsn_code": hsn, "taxes": [{"item_tax_template": tmpl}]}).insert()
	if mrp and not frappe.db.exists("Item Price", {"item_code": code, "price_list": "Standard Selling"}):
		frappe.get_doc({"doctype": "Item Price", "item_code": code, "price_list": "Standard Selling", "price_list_rate": mrp}).insert()
for u, roles in ((DOLLY, ["Purchase User", "Stock User", "Accounts User"]), (OTHER, ["Purchase User"]),
		(OWNER, ["Purchase User", "Purchase Manager", "Shop Owner", "Accounts User", "Stock User"])):
	if not frappe.db.exists("User", u):
		d = frappe.get_doc({"doctype": "User", "email": u, "first_name": u.split("@")[0], "send_welcome_email": 0, "user_type": "System User"})
		d.insert(ignore_permissions=True)
	d = frappe.get_doc("User", u)
	have = {r.role for r in d.roles}
	for r in roles:
		if r not in have:
			d.append("roles", {"role": r})
	d.save(ignore_permissions=True)
	frappe.defaults.set_user_default("Company", C, u)
frappe.db.set_single_value("Stock Settings", "default_warehouse", WH)
s = frappe.get_doc("Order Paper Settings")
s.enabled, s.so_enabled, s.pr_pi_enabled, s.rerank, s.auto_fallback = 1, 0, 1, 0, 0
s.freight_account = FREIGHT
s.set("receivers", [{"user": DOLLY}])
s.save(ignore_permissions=True)
frappe.clear_document_cache("Order Paper Settings", "Order Paper Settings")
frappe.db.sql("update `tabOrder Paper` set status = 'Discarded' where status not in ('Saved', 'Discarded')")
frappe.db.delete("Party Item Alias", {"party": ["in", [SEL, OUT, UNREG]]})
frappe.db.commit()

ENQ = []
paper._enqueue_read = lambda name, model, reason: ENQ.append((name, model, reason))
CONF = frappe.local.conf
CONF.pop("kgs_paper_ai_key", None)


def fake(reading):
	CONF["kgs_paper_ai_fake"] = {"reading": reading, "rerank": {"choices": []}}


def upload(purpose):
	r_ = paper.upload_paper(purpose, json.dumps([{"name": "p.jpg", "data": jpeg()}]), str(uuid.uuid4()))
	frappe.db.commit()
	return r_["name"]


def read(name, reason="first"):
	paper.run_read_job(name, None, reason)
	return paper.get_paper(name)


def ln(p, idx):
	return next(x for x in p["lines"] if x["idx"] == idx)


def approved_po(supplier, rows):
	as_user(OWNER)
	from frappe.model.workflow import apply_workflow

	po = frappe.get_doc({"doctype": "Purchase Order", "company": C, "supplier": supplier, "transaction_date": nowdate(),
		"schedule_date": add_days(nowdate(), 7), "set_warehouse": WH,
		"items": [{"item_code": c, "qty": q, "rate": r, "schedule_date": add_days(nowdate(), 7), "warehouse": WH} for c, q, r in rows]})
	po.insert()
	apply_workflow(po, "Send for Approval")
	po.reload()
	apply_workflow(po, "Approve")
	po.reload()
	frappe.db.commit()
	return po


PO = approved_po(SEL, [("BK-PHY9", 50, 455), ("BK-CHE10", 40, 350), ("BK-MAT6", 9, 240), ("BK-PHY9-OLD", 0.0001, 1)][:3])
check("setup: PO approved + submitted", PO.docstatus == 1, f"{PO.name} {PO.docstatus} {PO.get('workflow_state')}")

BILL_NO = f"25-26/{RUN}"
READ_PR = {
	"paper_kind": "bill", "party_name": "SELINA PUBLISHERS", "party_gstin": frappe.db.get_value("Supplier", SEL, "gstin"),
	"buyer_name": C, "paper_no": BILL_NO, "paper_date": "14-10-2026",
	"lines": [
		{"text": "Selina Concise Physics 9", "qty": 50, "mrp": 692, "discount_percent": 30, "rate": 692, "amount": 24220},
		{"text": "Selina Concise Chemistry 10", "qty": 60, "mrp": 500, "discount_percent": 30, "amount": 21000},
		{"text": "Selina Mathematics 6", "qty": 3, "rate": 240, "amount": 2160},
		{"text": "Classmate Register 200 Pages", "qty": 10, "rate": 40, "amount": 400},
		{"text": "Selina Atlas Junior zqx", "qty": 10, "rate": 50, "amount": 500},
	],
	"items_total": 48280, "tax_total": 72, "charges": [{"label": "Freight", "amount": 720}], "grand_total": 49072,
}

# ── unit ─────────────────────────────────────────────────────────────────────
check("line check: 50 × 692 less 30% = 24,220", pr.line_check(READ_PR["lines"][0]) is None)
c3 = pr.line_check(READ_PR["lines"][2])
check("line check: 3 × 240 ≠ 2,160 → make it 9", c3 and c3["fix_qty"] == 9 and c3["expected"] == 720, str(c3))
check("clean_reading keeps charges + tax + buyer GSTIN", (lambda d: d["charges"] == [{"label": "Freight", "amount": 720.0}]
	and d["tax_total"] == 72 and d["buyer_gstin"] == "")(pr.clean_reading(READ_PR)))
check("paper date parsed", str(pp.parse_paper_date("14-10-2026")) == "2026-10-14" and str(pp.parse_paper_date("14/10/26")) == "2026-10-14"
	and str(pp.parse_paper_date("2026-10-14")) == "2026-10-14" and str(pp.parse_paper_date("14 Oct 2026")) == "2026-10-14")
check("pct: preselect = 60, max fuzzy 89, exact 100", pm.pct(pm.PRESELECT) == 60 and pm.pct(1.3) == 89 and pm.pct(1, exact=True) == 100
	and pm.pct(0.3) < 60)
ours = pm.our_identity()
check("own identity has our GSTIN + name", frappe.db.get_value("Company", C, "gstin") in ours["gstins"] and C in ours["display"])
check("read prompt names the shop", C in pr.read_system(ours))
d_own = {"party_name": C, "party_gstin": "", "buyer_name": "Selina Publishers", "buyer_gstin": ""}
check("own paper: party swapped to the addressee", paper._swap_if_ours(d_own) and d_own["party_name"] == "Selina Publishers")

# ── access ───────────────────────────────────────────────────────────────────
as_user(OTHER)
b = paper.boot_info()
check("not on the list: no Receipt / Bill, PO still", b["pr"] == 0 and b["pi"] == 0 and b["po"] == 1, str(b))
check("not on the list: upload refused", raises(lambda: upload(pp.RECEIPT)) is not None)
as_user(DOLLY)
b = paper.boot_info()
check("Dolly: Receipt + Bill", b["pr"] == 1 and b["pi"] == 1, str(b))

# ── Receipt from the PO ──────────────────────────────────────────────────────
fake(READ_PR)
name = upload(pp.RECEIPT)
p = read(name)
check("PR paper ready, supplier by GSTIN", p["status"] == "Ready" and p["party"] == SEL and p["party_how"] == "gstin", f"{p['status']} {p.get('error')} {p['party']}")
check("links not chosen yet", p["links"] is None)
docs = {d["name"]: d for d in p["open_docs"]}
check("open PO listed with match %", PO.name in docs and docs[PO.name]["pct"] >= 60, str(docs.get(PO.name)))
check("charges + tax come through", p["charges"] and p["charges"][0]["amount"] == 720 and p["tax_total"] == 72)
r = paper.set_links(name, "docs", json.dumps([PO.name]), p["version"])
frappe.db.commit()
p = r
check("linked", p["links"]["docs"] == [PO.name] and p["links"]["doctype"] == "Purchase Order")
l1, l2, l3, l4, l5 = (ln(p, i) for i in range(1, 6))
check("line 1 on PO line 1, green, 100%", l1["doc_row"] and l1["doc_row"]["idx"] == 1 and l1["colour"] == "green" and l1["pct"] >= 90,
	f"{l1.get('doc_row')} {l1['colour']} {l1.get('pct')} {l1.get('how')} {l1.get('item_code')}")
check("line 1 picks the live twin, not the dead one", l1["item_code"] == "BK-PHY9", l1["item_code"])
check("line 1 net rate 484.40 (list 692 less 30%)", abs(flt(l1["buy_rate"]) - 484.4) < 0.001, str(l1.get("buy_rate")))
check("line 2: 60 against 40 due → amber over-delivery", l2["over"] and l2["colour"] == "amber" and l2["over"]["due"] == 40, f"{l2.get('over')} {l2['colour']}")
check("line 3: qty × rate ≠ amount → problem with fix 9", l3["check"] and l3["check"]["fix_qty"] == 9, str(l3.get("check")))
check("line 4: register not on the PO", l4["off_doc"] == 1 and not l4["doc_row"], f"{l4.get('off_doc')} {l4.get('note')}")
check("line 5: unknown item, red", l5["colour"] == "red")
check("totals not ok while line 3 is misread", p["totals"]["ok"] == 0, str(p["totals"]))
check("line problem listed for line 3", any(x["idx"] == 3 for x in p["problems"]))
check("last bought present (empty before any bill)", "last_bought" in p)

u = paper.update_lines(name, json.dumps([{"idx": 3, "fix": "qty"}]), p["version"])
frappe.db.commit()
l3 = next(x for x in u["lines"] if x["idx"] == 3)
check("fix qty: 9 × 240 = 2,160", l3["paper_qty"] == 9 and l3["qty"] == 9 and not l3["check"], f"{l3['paper_qty']} {l3['qty']} {l3['check']}")
ver = u["version"]
u = paper.update_lines(name, json.dumps([{"idx": 2, "decision": "ok"}, {"idx": 4, "decision": "ok"}]), ver)
frappe.db.commit()
check("Keep 60 + confirm register → totals add up (atlas counted as left out)", u["totals"]["ok"] == 1, json.dumps(u["totals"])[:400])
ver = u["version"]
check("rate 0 refused", raises(lambda: paper.update_lines(name, json.dumps([{"idx": 1, "rate": 0}]), ver)) is not None)
u = paper.update_lines(name, json.dumps([{"idx": 1, "rate": 500}]), ver)
frappe.db.commit()
check("a person's rate → totals no longer match", u["totals"]["ok"] == 0)
err = raises(lambda: paper.save_order(name, str(uuid.uuid4()), warehouse=WH, bill_no=BILL_NO, submit=0, version=u["version"]))
check("mismatch blocks Save draft too", err and "off the paper" in err, err)
u = paper.update_lines(name, json.dumps([{"idx": 1, "rate": 484.4}]), u["version"])
frappe.db.commit()
pv = paper.preview_purchase(name, warehouse=WH, bill_no=BILL_NO)
check("preview: ok, nothing draft-only", pv["numbers"]["ok"] == 1 and not pv["draft_only"], json.dumps(pv)[:500])
check("preview: GST 72 on the register only (books nil)", abs(pv["numbers"]["gst"] - 72) < 0.01, str(pv["numbers"]))
res = paper.save_order(name, str(uuid.uuid4()), warehouse=WH, bill_no=BILL_NO, submit=1, version=u["version"])
frappe.db.commit()
check("Receipt submitted", res.get("ok") == 1 and res.get("docstatus") == 1 and not res.get("submit_error"), json.dumps(res)[:400])
prd = frappe.get_doc("Purchase Receipt", res["doc"])
check("PR rows linked to PO rows", all(i.purchase_order == PO.name and i.purchase_order_item for i in prd.items if i.item_code != "ST-REG")
	and next(i for i in prd.items if i.item_code == "ST-REG").purchase_order in (None, ""))
check("PR rates are net, never list", abs(next(i for i in prd.items if i.item_code == "BK-PHY9").rate - 484.4) < 0.001)
check("PR: posting today, bill no as delivery note", str(prd.posting_date) == nowdate() and prd.supplier_delivery_note == BILL_NO)
check("PR: list price + discount kept for history", next(i for i in prd.items if i.item_code == "BK-PHY9").discount_percentage == 30)
check("PR: CGST/SGST from India Compliance", prd.taxes_and_charges == "Input GST In-state - KGS", prd.taxes_and_charges)
po_after = frappe.get_doc("Purchase Order", PO.name)
check("PO received (per_received > 0)", po_after.per_received > 0, str(po_after.per_received))
check("paper attached to the PR", frappe.db.count("File", {"attached_to_doctype": "Purchase Receipt", "attached_to_name": prd.name}) >= 1)
p = paper.get_paper(name)
check("saved screen: bill can be made", p["bill"] and p["bill"]["can"] == 1, str(p.get("bill")))

# repeat bill no. on a second Receipt → draft only
fake(dict(READ_PR, lines=READ_PR["lines"][:1], items_total=24220, tax_total=None, charges=[], grand_total=None))
name_r = upload(pp.RECEIPT)
p = read(name_r)
p = paper.set_links(name_r, "none", None, p["version"])
frappe.db.commit()
pv = paper.preview_purchase(name_r, warehouse=WH, bill_no=BILL_NO)
check("repeat bill no. → draft only", pv["draft_only"] and "already" in pv["draft_only"][0], str(pv["draft_only"]))
err = raises(lambda: paper.save_order(name_r, str(uuid.uuid4()), warehouse=WH, bill_no=BILL_NO, submit=1, version=p["version"]))
check("repeat bill no. → Submit refused", err and "draft" in err.lower(), err)
paper.discard_paper(name_r)
frappe.db.commit()

# ── the Bill from the same reading ───────────────────────────────────────────
mb = paper.make_bill(name)
frappe.db.commit()
bill_name = mb["name"]
p = paper.get_paper(bill_name)
check("bill paper ready, linked to the Receipt, no AI usage", p["status"] == "Ready" and p["links"]["docs"] == [prd.name]
	and p["purpose"] == pp.BILL and p["source_paper"] == name)
check("bill lines pinned to the PR rows", all(ln(p, i)["doc_row"] and ln(p, i)["doc_row"]["doctype"] == pp.RECEIPT for i in (1, 2, 3, 4)))
check("bill: atlas line missing → a bill must carry every line", p["totals"]["ok"] == 0 and p["totals"]["missing_bill_lines"])
err = raises(lambda: paper.save_order(bill_name, str(uuid.uuid4()), warehouse=WH, posting_date="2026-10-14", bill_no=BILL_NO,
	charges=json.dumps([0]), submit=0, version=p["version"]))
check("bill with a missing line: nothing saved", err and "every line" in err, err)
check("make_bill twice returns the same paper", paper.make_bill(name)["name"] == bill_name)

# ── Receipt then Bill, every line known: the Bill passes ─────────────────────
PO2 = approved_po(SEL, [("BK-PHY9", 20, 455), ("ST-REG", 10, 38)])
as_user(DOLLY)
BILL2 = f"S2-{RUN}"
READ_PR2 = {
	"paper_kind": "bill", "party_name": SEL, "party_gstin": frappe.db.get_value("Supplier", SEL, "gstin"),
	"paper_no": BILL2, "paper_date": "16-10-2026",
	"lines": [
		{"text": "Selina Concise Physics 9", "qty": 20, "mrp": 692, "discount_percent": 30, "amount": 9688},
		{"text": "Classmate Register 200 Pages", "qty": 10, "rate": 40, "amount": 400},
	],
	"items_total": 10088, "tax_total": 72, "charges": [{"label": "Packing", "amount": 50}], "grand_total": 10210,
}
fake(READ_PR2)
n2 = upload(pp.RECEIPT)
p = read(n2)
d2 = {d["name"]: d for d in p["open_docs"]}
check("2nd PR: its PO ranks first", p["open_docs"][0]["name"] == PO2.name and d2[PO2.name]["pct"] == 100, str([(d["name"], d.get("pct")) for d in p["open_docs"]]))
p = paper.set_links(n2, "docs", json.dumps([PO2.name]), p["version"])
frappe.db.commit()
check("2nd PR: both lines on the PO, green", all(x["doc_row"] and x["colour"] == "green" for x in p["lines"]), str([(x["idx"], x["colour"], x.get("note")) for x in p["lines"]]))
check("2nd PR: totals ok (packing not on a Receipt)", p["totals"]["ok"] == 1, json.dumps(p["totals"])[:300])
res = paper.save_order(n2, str(uuid.uuid4()), warehouse=WH, bill_no=BILL2, submit=1, version=p["version"])
frappe.db.commit()
check("2nd PR submitted", res.get("docstatus") == 1, json.dumps(res)[:300])
b2 = paper.make_bill(n2)["name"]
frappe.db.commit()
p = paper.get_paper(b2)
check("bill from PR: nothing to check, totals by lines ok", not any(x["colour"] != "green" for x in p["lines"] if x.get("decision") != "left") and p["totals"]["ok"] == 1,
	json.dumps(p["totals"])[:300])
check("bill from PR: posting date = bill date read", p["save"]["posting_date"] == "2026-10-16")
pv = paper.preview_purchase(b2, warehouse=WH, posting_date="2026-10-16", bill_no=BILL2)
check("bill from PR: ₹50 packing short until added", pv["numbers"]["ok"] == 0 and abs(pv["numbers"]["diff"] + 50) < 0.01 and pv["update_stock"] == 0,
	str(pv["numbers"]))
res = paper.save_order(b2, str(uuid.uuid4()), warehouse=WH, posting_date="2026-10-16", bill_no=BILL2, charges=json.dumps([0]),
	submit=1, version=p["version"])
frappe.db.commit()
check("bill from PR submitted", res.get("docstatus") == 1 and not res.get("submit_error"), json.dumps(res)[:400])
pi2 = frappe.get_doc("Purchase Invoice", res["doc"])
check("bill from PR: no stock again, rows on the PR + PO", pi2.update_stock == 0 and all(i.pr_detail and i.purchase_receipt and i.po_detail for i in pi2.items))
check("bill from PR: grand total = paper", abs((pi2.rounded_total or pi2.grand_total) - 10210) < 1, str(pi2.grand_total))
check("PR fully billed", flt(frappe.db.get_value("Purchase Receipt", frappe.db.get_value("Order Paper", n2, "created_doc"), "per_billed")) >= 99.9)
check("source paper knows its bill", frappe.db.get_value("Order Paper", n2, "bill_paper") == b2)

# ── a direct Bill that adds stock (out-state, IGST, freight) ─────────────────
OUT_BILL = f"OS-{RUN}"
READ_PI = {
	"paper_kind": "bill", "party_name": OUT, "party_gstin": frappe.db.get_value("Supplier", OUT, "gstin"),
	"paper_no": OUT_BILL, "paper_date": "15-10-2026",
	"lines": [
		{"text": "Selina Concise Physics 9", "qty": 10, "mrp": 692, "rate": 484.4, "amount": 4844},
		{"text": "Classmate Register 200 Pages", "qty": 5, "rate": 40, "amount": 200},
	],
	"items_total": 5044, "tax_total": 36, "charges": [{"label": "Freight", "amount": 120}], "grand_total": 5200,
}
fake(READ_PI)
pi_name = upload(pp.BILL)
p = read(pi_name)
check("direct bill ready, supplier by GSTIN", p["status"] == "Ready" and p["party"] == OUT, f"{p['status']} {p.get('error')}")
p = paper.set_links(pi_name, "none", None, p["version"])
frappe.db.commit()
for x in p["lines"]:
	if x["colour"] != "green":
		p2 = paper.update_lines(pi_name, json.dumps([{"idx": x["idx"], "decision": "ok"}]), p["version"])
		frappe.db.commit()
		p["version"] = p2["version"]
check("bill save info: posting = bill date", p["save"]["posting_date"] == "2026-10-15", str(p["save"]))
pv = paper.preview_purchase(pi_name, warehouse=WH, posting_date="2026-10-15", bill_no=OUT_BILL)
check("preview without freight: ₹120 short", pv["numbers"]["ok"] == 0 and abs(pv["numbers"]["diff"] + 120) < 0.01, str(pv["numbers"]))
check("preview: IGST 36", abs(pv["numbers"]["gst"] - 36) < 0.01 and pv["update_stock"] == 1, str(pv["numbers"]))
pv = paper.preview_purchase(pi_name, warehouse=WH, posting_date="2026-10-15", bill_no=OUT_BILL, charges=json.dumps([0]))
check("preview with freight: matches the bill", pv["numbers"]["ok"] == 1, str(pv["numbers"]))
# filed GST period → draft only
gstin = frappe.db.get_value("Company", C, "gstin")
log = frappe.get_doc({"doctype": "GST Return Log", "return_type": "GSTR3B", "return_period": "122026", "gstin": gstin,
	"company": C, "filing_status": "Filed"})
log.insert(ignore_permissions=True)
pv = paper.preview_purchase(pi_name, warehouse=WH, posting_date="2026-10-15", bill_no=OUT_BILL, charges=json.dumps([0]))
check("filed GSTR-3B for the quarter → draft only", any("GSTR-3B" in x for x in pv["draft_only"]), str(pv["draft_only"]))
frappe.delete_doc("GST Return Log", log.name, ignore_permissions=True, force=True)
frappe.db.commit()
res = paper.save_order(pi_name, str(uuid.uuid4()), warehouse=WH, posting_date="2026-10-15", bill_no=OUT_BILL,
	charges=json.dumps([0]), submit=1, version=p["version"])
frappe.db.commit()
check("Bill submitted", res.get("ok") == 1 and res.get("docstatus") == 1 and not res.get("submit_error"), json.dumps(res)[:400])
pid = frappe.get_doc("Purchase Invoice", res["doc"])
check("bill: update stock, bill no/date, posting = bill date", pid.update_stock == 1 and pid.bill_no == OUT_BILL
	and str(pid.bill_date) == "2026-10-15" and str(pid.posting_date) == "2026-10-15")
check("bill: freight row on the set account", any(t.account_head == FREIGHT and flt(t.tax_amount) == 120 for t in pid.taxes))
check("bill: total = paper", abs((pid.rounded_total or pid.grand_total) - 5200) < 1, str(pid.grand_total))

# ── last bought (now that a bill exists) ─────────────────────────────────────
lb = pm.last_bought(["BK-PHY9"])
check("last bought: submitted bills, newest first, per stock unit, discount kept", lb.get("BK-PHY9")
	and any(x["doc"] == pid.name for x in lb["BK-PHY9"]) and lb["BK-PHY9"][0]["date"] >= lb["BK-PHY9"][-1]["date"]
	and all(abs(x["rate"] - 484.4) < 0.01 for x in lb["BK-PHY9"]) and lb["BK-PHY9"][0]["discount"] == 30, str(lb))
check("usual discount needs 5+ lines", pm.supplier_usual_discount(SEL) is None or pm.supplier_usual_discount(SEL)["pct"] == 30)

# ── supplier changed on a Receipt → rematch in the background ────────────────
fake(dict(READ_PR, paper_no=f"RM-{RUN}"))
name_m = upload(pp.RECEIPT)
p = read(name_m)
ENQ.clear()
p = paper.set_party(name_m, UNREG, p["version"])
frappe.db.commit()
check("new supplier → re-matched in the background", p["status"] == "Reading" and ENQ and ENQ[-1][2] == "rematch", f"{p['status']} {ENQ}")
p = read(name_m, "rematch")
check("rematch: ready for the new supplier, links reset", p["status"] == "Ready" and p["party"] == UNREG and p["links"] is None,
	f"{p['status']} {p.get('error')} {p['party']}")
paper.discard_paper(name_m)
frappe.db.commit()

# ── ranking facts on candidates ──────────────────────────────────────────────
st = paper._state(frappe.get_doc("Order Paper", name))
cands = [c for x in st["lines"] for c in x.get("candidates") or []]
check("candidates carry pct + facts", cands and all("pct" in c and "facts" in c for c in cands), str(cands[:1]))

CONF.pop("kgs_paper_ai_fake", None)
frappe.set_user("Administrator")
bad = [r for r in RESULTS if not r[1]]
print(f"\n{len(RESULTS) - len(bad)}/{len(RESULTS)} passed")
if bad:
	sys.exit(1)
