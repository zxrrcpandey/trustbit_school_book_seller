# Copyright (c) 2026, Trustbit Software and contributors
# Order from Paper — Purchase Receipts and Purchase Invoices from a supplier's
# bill or challan (staff_app/paper.py calls these). Mockup v4 + the owner's
# decisions of 2026-10-20:
#   - PO / Receipt / Bill is chosen before reading; Receipt and Bill only for the
#     people listed in Order Paper Settings (Dolly + Vishnu).
#   - A Receipt / Bill links its PO (or unbilled Receipt) first; the bill's lines
#     are matched against that document's items before all our items.
#   - Totals must match the paper within ₹1, or neither "Save draft" nor
#     "Submit now" works. A repeat bill no. or a filed GST period leaves draft only.
#   - The rate comes from the paper (net, never list price, never ₹0 — Rule 16).
#   - A bill from a Receipt never adds stock again; a bill that adds stock
#     ("Update Stock") never links a Receipt.
# Nothing here runs the AI. Index-based scoring (score_docs) runs only inside
# the background read job (DANGER 21).

import re

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, nowdate

from trustbit_school_book_seller.staff_app import paper_match as pm
from trustbit_school_book_seller.staff_app import paper_read as pr

RECEIPT, BILL, ORDER = "Purchase Receipt", "Purchase Invoice", "Purchase Order"
PURCHASE_DOCS = (RECEIPT, BILL)
LINK_GREEN, LINK_MARGIN, LINK_AMBER = 0.60, 0.12, 0.45
DOC_PRESELECT = 60  # % from which the best document is ticked for you
DOCS_SHOWN = 12
TOTAL_TOL = 1.0  # ₹: bills are rounded to the rupee
PENDING = "Pending Approval"


def is_purchase(purpose):
	return purpose in PURCHASE_DOCS


# ── documents a paper can link ───────────────────────────────────────────────


def open_docs(purpose, supplier, company):
	"""[{doctype, name, date, owner, owner_name, bill_no, status, linkable, why, rows: [...]}]
	Receipt: the supplier's approved POs with something still to receive, plus
	POs waiting for the owners (greyed: ERPNext receives only a submitted PO).
	Bill: unbilled Receipts first, then POs (for a bill that adds stock)."""
	if not supplier:
		return []
	out = []
	if purpose == BILL:
		out += _receipts(supplier, company)
	out += _orders(supplier, company)
	return out


def _orders(supplier, company):
	wf = frappe.db.has_column(ORDER, "workflow_state")
	rows = frappe.db.sql(
		f"""select name, transaction_date as date, owner, docstatus, status, per_received,
			{"workflow_state" if wf else "''"} as wf
		from `tabPurchase Order`
		where supplier = %s and company = %s and (
			(docstatus = 1 and status in ('To Receive and Bill', 'To Receive') and per_received < 100)
			or (docstatus = 0 and {"workflow_state" if wf else "''"} = %s))
		order by transaction_date desc, creation desc limit 30""",
		(supplier, company, PENDING),
		as_dict=True,
	)
	if not rows:
		return []
	items = frappe.db.sql(
		"""select parent, name, idx, item_code, item_name, qty, received_qty, uom, conversion_factor, rate, warehouse
		from `tabPurchase Order Item` where parent in %s order by parent, idx""",
		(tuple(r.name for r in rows),),
		as_dict=True,
	)
	by = {}
	for it in items:
		due = flt(it.qty) - flt(it.received_qty)
		by.setdefault(it.parent, []).append(_row(ORDER, it, due))
	out = []
	for r in rows:
		pending = r.docstatus == 0
		out.append({
			"doctype": ORDER, "name": r.name, "date": str(r.date), "owner": r.owner, "owner_name": frappe.utils.get_fullname(r.owner),
			"status": PENDING if pending else r.status, "linkable": 0 if pending else 1,
			"why": _("Waiting for a shop owner to approve it") if pending else "", "bill_no": "",
			"rows": by.get(r.name, []),
		})
	return out


def _receipts(supplier, company):
	rows = frappe.db.sql(
		"""select name, posting_date as date, owner, status, supplier_delivery_note as bill_no
		from `tabPurchase Receipt`
		where supplier = %s and company = %s and docstatus = 1 and is_return = 0 and per_billed < 100
			and status not in ('Closed', 'Completed', 'Return Issued')
		order by posting_date desc, creation desc limit 30""",
		(supplier, company),
		as_dict=True,
	)
	if not rows:
		return []
	names = tuple(r.name for r in rows)
	items = frappe.db.sql(
		"""select parent, name, idx, item_code, item_name, qty, uom, conversion_factor, rate, warehouse,
			purchase_order, purchase_order_item
		from `tabPurchase Receipt Item` where parent in %s order by parent, idx""",
		(names,),
		as_dict=True,
	)
	# billed so far, by receipt row: submitted bills AND drafts (a draft bill
	# already holding the row would make the second one over-bill)
	billed, drafts = {}, {}
	for b in frappe.db.sql(
		"""select pii.pr_detail, pii.qty, pi.docstatus, pi.name from `tabPurchase Invoice Item` pii
		join `tabPurchase Invoice` pi on pi.name = pii.parent
		where pii.purchase_receipt in %s and pi.docstatus < 2""",
		(names,),
		as_dict=True,
	):
		billed[b.pr_detail] = billed.get(b.pr_detail, 0) + flt(b.qty)
		if b.docstatus == 0:
			drafts.setdefault(b.pr_detail, set()).add(b.name)
	by = {}
	for it in items:
		row = _row(RECEIPT, it, flt(it.qty) - billed.get(it.name, 0))
		row["po"], row["po_detail"] = it.purchase_order, it.purchase_order_item
		if it.name in drafts:
			row["draft_bills"] = sorted(drafts[it.name])
		by.setdefault(it.parent, []).append(row)
	out = []
	for r in rows:
		rws = by.get(r.name, [])
		if not any(x["due"] > 0 for x in rws):
			continue
		draft_bills = sorted({b for x in rws for b in x.get("draft_bills") or []})
		out.append({
			"doctype": RECEIPT, "name": r.name, "date": str(r.date), "owner": r.owner, "owner_name": frappe.utils.get_fullname(r.owner),
			"status": r.status, "linkable": 1, "why": "", "bill_no": r.bill_no or "", "draft_bills": draft_bills,
			"rows": rws,
		})
	return out


def _row(doctype, it, due):
	return {
		"doctype": doctype, "parent": it.parent, "name": it.name, "idx": cint(it.idx), "item_code": it.item_code,
		"item_name": it.item_name, "qty": flt(it.qty), "due": max(0.0, round(due, 6)), "uom": it.uom,
		"factor": flt(it.conversion_factor) or 1.0, "rate": flt(it.rate), "warehouse": it.warehouse,
	}


def doc_item_codes(docs):
	return sorted({r["item_code"] for d in docs for r in d["rows"] if r["item_code"]})


def score_docs(index, lines, docs):
	"""In the read job: each line's score against every item on the supplier's
	open documents (line["doc_scores"]), so linking later needs no index."""
	codes = doc_item_codes(docs)
	for ln in lines:
		if not codes:
			ln["doc_scores"] = {}
			continue
		cls = pm.class_of(ln.get("class_hint")) or pm.class_of(ln.get("text"))
		got = index.score_items(ln.get("text"), codes, line_class=cls, mrp=ln.get("mrp"))
		ln["doc_scores"] = {c: v for c, v in got.items() if v["score"] >= pm.SUGGEST}


def best_on_docs(ln, hit, codes):
	"""(item_code, score, sure) — the item of the linked documents this line is,
	or None. Exact layers and a person's choice are sure; a fuzzy one is sure
	only when clearly ahead of the other rows AND of our other items."""
	if ln.get("by_person") and ln.get("item_code"):
		return (ln["item_code"], 1.0, True) if ln["item_code"] in codes else None
	if hit and hit.get("item_code") in codes:
		return hit["item_code"], 1.0, True
	scores = ln.get("doc_scores") or {}
	ranked = sorted(((c, v) for c, v in scores.items() if c in codes and not v.get("class_mismatch")), key=lambda x: -x[1]["score"])
	if not ranked:
		return None
	code, best = ranked[0]
	s = best["score"]
	second = ranked[1][1]["score"] if len(ranked) > 1 else 0.0
	off = max((flt(c.get("score")) for c in ln.get("candidates") or [] if c["item_code"] not in codes and not c.get("class_mismatch")), default=0.0)
	if s >= LINK_GREEN and s - second >= LINK_MARGIN and s >= off - 0.02:
		return code, s, True
	if s >= LINK_AMBER and s >= off - 0.10:
		return code, s, False
	return None


def doc_pcts(state, exact):
	"""Match % per open document: the paper's lines whose item is on it."""
	lines = state.get("lines") or []
	n = len(lines) or 1
	for d in state.get("open_docs") or []:
		codes = {r["item_code"] for r in d["rows"]}
		hits = sum(1 for ln in lines if best_on_docs(ln, exact.get(ln["idx"]), codes))
		d["hits"], d["pct"] = hits, int(round(100 * hits / n))
		d["due_lines"] = sum(1 for r in d["rows"] if r["due"] > 0)
	docs = state.get("open_docs") or []
	docs.sort(key=lambda d: (-d["linkable"], -d.get("pct", 0)))  # stable: newest first among equals
	linked = set((state.get("links") or {}).get("docs") or [])
	state["open_docs"] = [d for i, d in enumerate(docs) if i < DOCS_SHOWN or d["name"] in linked]


def linked_rows(state):
	links = state.get("links") or {}
	if links.get("mode") != "docs":
		return []
	names = set(links.get("docs") or [])
	return [r for d in state.get("open_docs") or [] if d["name"] in names for r in d["rows"]]


def apply_links(state, info, exact, purpose):
	"""Put each line on a row of the linked document(s), or mark it "not on the
	PO". Unit and default quantity follow the row (ERPNext compares the unit
	with the PO / Receipt row). Then rates, the line check and over-delivery."""
	rows = linked_rows(state)
	codes = {r["item_code"] for r in rows}
	used = {}  # row name → stock qty already put on it
	docs_label = _docs_label(state)
	for ln in state["lines"]:
		ln["doc_row"], ln["link_how"], ln["link_pct"], ln["off_doc"], ln["over"], ln["paper_qty_doc"] = None, None, None, 0, None, None
		if ln.get("decision") == "left":
			_rates(ln, purpose)
			continue
		pinned = next((r for r in rows if r["name"] == ln.get("pin_row")), None)
		got = (pinned["item_code"], 1.0, True) if pinned else best_on_docs(ln, exact.get(ln["idx"]), codes) if rows else None
		if got:
			code, score, sure = got
			cands = [r for r in rows if r["item_code"] == code]
			row = pinned or max(cands, key=lambda r: r["due"] * r["factor"] - used.get(r["name"], 0))
			it = info.get(code)
			if it and ln.get("item_code") != code:
				_take_item(ln, it)
			ln["doc_row"] = {k: row[k] for k in ("doctype", "parent", "name", "idx", "qty", "due", "uom", "factor", "rate")}
			for k in ("po", "po_detail"):
				if row.get(k):
					ln["doc_row"][k] = row[k]
			ln["link_how"] = "exact" if score >= 1.0 else ("sure" if sure else "probably")
			# among the few items of the linked PO a clear lead is sure (90–99)
			ln["link_pct"] = 100 if score >= 1.0 else (int(min(99, 90 + round((score - LINK_GREEN) * 20))) if sure else pm.pct(score))
			if not ln.get("by_person"):
				ln["pct"] = ln["link_pct"]
			_unit_from_row(ln, row)
			if not ln.get("by_person") and ln.get("decision") != "ok":
				if sure:
					if ln.get("colour") != "green" or ln.get("how") in ("fuzzy", "none", "other_party"):
						ln["colour"], ln["how"], ln["note"] = "green", "on_doc", ""
				else:
					ln["colour"], ln["how"] = "amber", "on_doc_maybe"
					ln["note"] = _("Probably {0} line {1}").format(row["parent"], row["idx"])
		elif rows:
			ln["off_doc"] = 1
			if ln.get("colour") == "amber" and not ln.get("by_person"):
				ln["note"] = _("Not on {0}").format(docs_label) + (" · " + ln["note"] if ln.get("note") else "")
		_rates(ln, purpose)
		if ln.get("doc_row") and ln.get("qty"):
			used[ln["doc_row"]["name"]] = used.get(ln["doc_row"]["name"], 0) + flt(ln["qty"]) * flt(ln.get("conversion_factor") or 1)
	# over-delivery: more on the paper than is still due on the row
	for ln in state["lines"]:
		row = ln.get("doc_row")
		if not row or ln.get("decision") == "left":
			continue
		due_stock = flt(row["due"]) * flt(row["factor"])
		if flt(used.get(row["name"])) > due_stock + 1e-6:
			ln["over"] = {"due": round(flt(row["due"]), 3), "total": round(flt(used[row["name"]]) / flt(row["factor"]), 3)}
			if not ln.get("by_person") and ln.get("decision") != "ok" and ln.get("colour") == "green":
				ln["colour"] = "amber"
				ln["note"] = _("{0} on the paper, {1} still due on {2}").format(
					_q(ln["over"]["total"]), _q(row["due"]), row["parent"])


def _q(v):
	return f"{flt(v):g}"


def _docs_label(state):
	links = state.get("links") or {}
	docs = links.get("docs") or []
	if not docs:
		return _("the PO")
	return docs[0] if len(docs) == 1 else _("the linked documents")


def _take_item(ln, it):
	from trustbit_school_book_seller.staff_app.paper import _set_item

	_set_item(ln, it)


def _unit_from_row(ln, row):
	"""The row's unit, with the paper's quantity converted when the paper's own
	unit is known and different (2 PKT of 10 → 20 Nos)."""
	if ln.get("uom") == row["uom"]:
		ln["conversion_factor"] = row["factor"]
		ratio = flt(ln.get("unit_ratio")) or 1.0  # a person's line converted earlier
		ln["paper_qty_doc"] = round(flt(ln["paper_qty"]) * ratio, 6) if ln.get("paper_qty") else None
		return
	line_factor = flt(ln.get("conversion_factor")) or 1.0
	known = cint(ln.get("unit_known")) and ln.get("unit")
	ratio = line_factor / flt(row["factor"]) if known else 1.0
	ln["uom"], ln["conversion_factor"], ln["unit_known"] = row["uom"], row["factor"], 1
	ln["unit_ratio"] = ratio
	ln["paper_qty_doc"] = round(flt(ln.get("paper_qty")) * ratio, 6) if ln.get("paper_qty") else None
	if not ln.get("qty_by_person") and ln.get("paper_qty"):
		ln["qty"] = ln["paper_qty_doc"]


def _rates(ln, purpose):
	"""buy_rate = the rate that goes on the Receipt / Bill, per OUR unit of the
	line: the paper's net rate; else the linked row's rate; else none (to enter).
	A person's rate is kept. Also the qty × rate = amount check of the line."""
	ratio = flt(ln.get("unit_ratio")) or 1.0
	if ln.get("paper_qty_doc") is None and ln.get("paper_qty"):
		ln["paper_qty_doc"] = round(flt(ln["paper_qty"]) * ratio, 6)
	if not ln.get("rate_by_person"):
		pr_rate = pr.paper_rate(ln)
		row = ln.get("doc_row")
		if pr_rate:
			ln["buy_rate"], ln["rate_src"] = round(pr_rate / ratio, 4), "paper"
		elif row and flt(row.get("rate")) > 0:
			ln["buy_rate"], ln["rate_src"] = flt(row["rate"]), "po" if row["doctype"] == ORDER else "pr"
		else:
			ln["buy_rate"], ln["rate_src"] = None, None
	ln["check"] = pr.line_check(_as_read(ln))


def _as_read(ln):
	"""The line as printed (the person may have corrected a misread number)."""
	return {"qty": ln.get("paper_qty"), "rate": ln.get("rate"), "mrp": ln.get("mrp"), "amount": ln.get("amount"),
		"discount_percent": ln.get("discount_percent")}


# ── what still stops the save ────────────────────────────────────────────────


def line_problem(ln, purpose):
	"""Why this kept line cannot go on the Receipt / Bill yet, or ""."""
	if ln.get("check"):
		c = ln["check"]
		return _("qty × rate is ₹{0}, the paper's amount is ₹{1}").format(_m(c["expected"]), _m(c["amount"]))
	if not flt(ln.get("buy_rate")):
		return _("enter the rate (₹0 is not allowed)")
	return ""


def _m(v):
	v = flt(v)
	return f"{v:,.2f}".rstrip("0").rstrip(".") if v % 1 else f"{v:,.0f}"


def totals(state, data, purpose, keep, left, charges_added=()):
	"""The money check of the check screen (and of the save). Net = before tax.
	{"lines_net", "explained", "targets", "ok", "diff", "against", "left_amounts",
	 "missing_bill_lines", "charges", "gross_needed"}"""
	data = data or {}
	net = round(sum(flt(ln.get("buy_rate")) * flt(ln.get("qty")) for ln in keep), 2)
	explained, notes = 0.0, []
	left_amt = [(ln, flt(ln.get("paper_amount"))) for ln in left if flt(ln.get("paper_amount"))]
	missing = []
	if purpose == RECEIPT:
		for ln, a in left_amt:
			explained += a
			notes.append({"idx": ln["idx"], "kind": "left", "amount": a, "text": ln.get("text")})
		for ln in keep:
			short = flt(ln.get("paper_qty_doc")) - flt(ln.get("qty"))
			if short > 1e-6 and flt(ln.get("buy_rate")):
				a = round(short * flt(ln["buy_rate"]), 2)
				explained += a
				notes.append({"idx": ln["idx"], "kind": "short", "amount": a, "qty": round(short, 3), "text": ln.get("text")})
	else:
		missing = [{"idx": ln["idx"], "amount": a, "text": ln.get("text")} for ln, a in left_amt]
	charges = [dict(c, i=i, added=1 if i in charges_added else 0) for i, c in enumerate(data.get("charges") or [])]
	added = sum(flt(c["amount"]) for c in charges if c["added"])
	targets = []
	if data.get("items_total"):
		targets.append({"kind": "items", "amount": flt(data["items_total"])})
	if data.get("grand_total"):
		g = flt(data["grand_total"]) - sum(flt(c["amount"]) for c in charges) - flt(data.get("tax_total"))
		if g > 0 and not any(abs(g - t["amount"]) < 0.005 for t in targets):
			targets.append({"kind": "grand_less", "amount": round(g, 2), "tax_known": 1 if data.get("tax_total") is not None else 0})
	mine = round(net + explained, 2)
	best = min(targets, key=lambda t: abs(mine - t["amount"])) if targets else None
	ok = bool(best and abs(mine - best["amount"]) <= TOTAL_TOL)
	# a Bill is finally checked against the grand total with GST (preview); a
	# paper whose GST was not read can only be checked there
	gross_needed = purpose == BILL and bool(data.get("grand_total"))
	if not targets:
		ok = True  # nothing printed to check against: each line was checked on its own
	return {
		"lines_net": net, "explained": round(explained, 2), "mine": mine, "notes": notes, "targets": targets,
		"against": best, "diff": round(mine - best["amount"], 2) if best else 0.0, "ok": 1 if ok and not missing else 0,
		"missing_bill_lines": missing, "charges": charges, "charges_added": round(added, 2), "gross_needed": 1 if gross_needed else 0,
		"has_total": 1 if targets else 0,
	}


# ── checks that leave "Save draft" only ──────────────────────────────────────


def repeat_bill(purpose, supplier, bill_no, exclude=None):
	"""The Receipt / Bill already made with this supplier + bill no. (ERPNext's
	"Check supplier invoice uniqueness" is off here, so nothing else catches it)."""
	bill_no = (bill_no or "").strip()
	if not (supplier and bill_no):
		return None
	if purpose == BILL:
		row = frappe.db.sql(
			"""select name, docstatus from `tabPurchase Invoice` where supplier = %s and bill_no = %s and docstatus < 2
			and is_return = 0 and name != %s order by creation desc limit 1""",
			(supplier, bill_no, exclude or ""),
			as_dict=True,
		)
	else:
		row = frappe.db.sql(
			"""select name, docstatus from `tabPurchase Receipt` where supplier = %s and supplier_delivery_note = %s
			and docstatus < 2 and is_return = 0 and name != %s order by creation desc limit 1""",
			(supplier, bill_no, exclude or ""),
			as_dict=True,
		)
	return {"doctype": purpose, "name": row[0].name, "docstatus": row[0].docstatus} if row else None


def filed_period(company, posting_date):
	"""The filed GSTR-3B period the date falls in (monthly, or its quarter's for
	QRMP), or None. CLAUDE.md Rule 8 / 14: such a bill goes to the accountant."""
	if not frappe.db.table_exists("GST Return Log"):
		return None
	d = getdate(posting_date)
	q_end = ((d.month - 1) // 3) * 3 + 3
	periods = {f"{d.month:02d}{d.year}", f"{q_end:02d}{d.year}"}
	gstins = set()
	if frappe.db.has_column("Company", "gstin"):
		g = frappe.db.get_value("Company", company, "gstin")
		if g:
			gstins.add(g)
	for g in frappe.db.sql_list(
		"""select a.gstin from `tabAddress` a join `tabDynamic Link` l on l.parent = a.name and l.parenttype = 'Address'
		where l.link_doctype = 'Company' and l.link_name = %s and ifnull(a.gstin, '') != ''""",
		company,
	) if frappe.db.has_column("Address", "gstin") else []:
		gstins.add(g)
	cond = " and gstin in %(g)s" if gstins else ""
	row = frappe.db.sql(
		f"""select return_period from `tabGST Return Log` where return_type = 'GSTR3B' and filing_status = 'Filed'
		and return_period in %(p)s{cond} limit 1""",
		{"p": tuple(periods), "g": tuple(gstins) or ("",)},
	)
	return row[0][0] if row else None


def parse_paper_date(text):
	"""The paper's printed date → a date, or None: 14-10-2026, 14/10/26,
	14.10.2026, 2026-10-14, 14 Oct 2026."""
	s = str(text or "").strip()
	if not s:
		return None
	m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
	try:
		if m:
			return getdate(f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}")
		m = re.search(r"(\d{1,2})[./\-](\d{1,2})[./\-](\d{2,4})", s)
		if m:
			y = int(m.group(3))
			y = y + 2000 if y < 100 else y
			return getdate(f"{y}-{int(m.group(2)):02d}-{int(m.group(1)):02d}")
		m = re.search(r"(\d{1,2})\s*[- ]?\s*([A-Za-z]{3,9})\s*[-, ]?\s*(\d{2,4})", s)
		if m:
			import datetime

			mon = datetime.datetime.strptime(m.group(2)[:3].title(), "%b").month
			y = int(m.group(3))
			y = y + 2000 if y < 100 else y
			return getdate(f"{y}-{mon:02d}-{int(m.group(1)):02d}")
	except Exception:
		return None
	return None


# ── the document ─────────────────────────────────────────────────────────────


def build_doc(paper, state, data, purpose, party, keep, left, warehouse, posting_date, bill_no, charges_added, freight_account):
	"""The unsaved Receipt / Bill, taxes as India Compliance sets them for the
	supplier (in-state / out-state / unregistered), freight as an Actual charge."""
	from erpnext.accounts.party import get_party_details

	links = state.get("links") or {}
	doc = frappe.new_doc(purpose)
	doc.company = paper.company
	doc.supplier = party
	doc.set_warehouse = warehouse
	if purpose == RECEIPT:
		doc.posting_date = nowdate()  # never back-dated
		doc.supplier_delivery_note = (bill_no or "")[:140] or None
		update_stock = 1
	else:
		doc.posting_date = posting_date
		doc.set_posting_time = 1
		doc.bill_no = (bill_no or "")[:140] or None
		doc.bill_date = posting_date
		update_stock = 0 if links.get("doctype") == RECEIPT and links.get("mode") == "docs" else 1
		doc.update_stock = update_stock
	pd = get_party_details(party=party, party_type="Supplier", company=paper.company, doctype=purpose,
		posting_date=doc.posting_date, bill_date=doc.get("bill_date"))
	for k in ("supplier_address", "address_display", "supplier_gstin", "gst_category", "place_of_supply", "taxes_and_charges",
			"company_address", "company_address_display", "company_gstin", "tax_category", "shipping_address",
			"shipping_address_display", "billing_address", "billing_address_display", "contact_person", "currency",
			"buying_price_list", "price_list_currency", "credit_to", "payment_terms_template"):
		if pd.get(k) not in (None, "") and doc.meta.has_field(k):
			doc.set(k, pd.get(k))
	for t in pd.get("taxes") or []:
		doc.append("taxes", t)
	pack_mrp = frappe.get_meta(f"{purpose} Item").has_field("custom_pack_mrp")
	for ln in keep:
		row = ln.get("doc_row") or {}
		item = {
			"item_code": ln["item_code"], "qty": flt(ln["qty"]), "uom": ln["uom"],
			"conversion_factor": flt(ln.get("conversion_factor")) or 1, "rate": flt(ln["buy_rate"]),
		}
		if update_stock:
			item["warehouse"] = warehouse
		gross, disc = _list_price(ln)
		if gross:
			item["price_list_rate"], item["discount_percentage"] = gross, disc
		if row.get("doctype") == ORDER:
			if purpose == RECEIPT:
				item["purchase_order"], item["purchase_order_item"] = row["parent"], row["name"]
			else:
				item["purchase_order"], item["po_detail"] = row["parent"], row["name"]
		elif row.get("doctype") == RECEIPT:
			item["purchase_receipt"], item["pr_detail"] = row["parent"], row["name"]
			if row.get("po"):
				item["purchase_order"], item["po_detail"] = row["po"], row.get("po_detail")
		# a new printed MRP (shelf prices, trustbit_barcode): per stock unit only,
		# and only on a document that adds stock
		if pack_mrp and update_stock and _new_mrp(ln):
			item["custom_pack_mrp"] = flt(ln["mrp"])
		doc.append("items", item)
	if purpose == BILL:
		for i in charges_added or ():
			cs = data.get("charges") or []
			if 0 <= i < len(cs):
				doc.append("taxes", {
					"charge_type": "Actual", "category": "Total", "add_deduct_tax": "Add", "account_head": freight_account,
					"description": (cs[i].get("label") or "Freight")[:140], "tax_amount": flt(cs[i]["amount"]),
				})
	remark = _("From paper {0}").format(paper.name) + (f" ({paper.paper_no})" if paper.paper_no else "")
	if left:
		remark += ". " + _("Left out: {0}").format("; ".join(
			f"{ln['text']}" + (f" × {_m(ln.get('paper_qty'))}" if ln.get("paper_qty") else "") for ln in left[:30]))
	doc.remarks = remark[:1000]
	doc.set_missing_values()
	doc.calculate_taxes_and_totals()
	return doc


def _list_price(ln):
	"""(list price per our unit, discount %) as printed, so the bill keeps the
	discount the "Last bought" history reads; (None, None) when not printed."""
	disc = flt(ln.get("discount_percent"))
	if not disc or not flt(ln.get("buy_rate")):
		return None, None
	ratio = flt(ln.get("unit_ratio")) or 1.0
	gross = flt(ln.get("mrp")) or flt(ln.get("rate"))
	if not gross:
		return None, None
	gross = round(gross / ratio, 4)
	if abs(gross * (1 - disc / 100) - flt(ln["buy_rate"])) > max(0.01, 0.005 * gross):
		return None, None  # the rate is not that list price less that discount: keep the rate alone
	return gross, disc


def _new_mrp(ln):
	return bool(flt(ln.get("mrp")) and flt(ln.get("conversion_factor")) == 1 and flt(ln.get("unit_ratio") or 1) == 1
		and not ln.get("check") and not pm.same_money(ln["mrp"], ln.get("item_mrp")))


def preview_numbers(doc, data, tot):
	"""What the save screen shows from ERPNext's own calculation."""
	gst = round(sum(flt(t.tax_amount) for t in doc.taxes if t.charge_type != "Actual"), 2)
	charges = round(sum(flt(t.tax_amount) for t in doc.taxes if t.charge_type == "Actual"), 2)
	ours = flt(doc.rounded_total) or flt(doc.grand_total)
	out = {
		"items": flt(doc.net_total), "gst": gst, "charges": charges, "grand_total": flt(doc.grand_total),
		"rounded_total": ours, "rounding": flt(doc.get("rounding_adjustment")), "taxes_and_charges": doc.get("taxes_and_charges") or "",
		"paper_grand": flt(data.get("grand_total")) or None,
	}
	if data.get("grand_total") and doc.doctype == BILL:
		out["diff"] = round(ours - flt(data["grand_total"]), 2)
		out["ok"] = 1 if abs(out["diff"]) <= TOTAL_TOL and not tot["missing_bill_lines"] else 0
	elif data.get("grand_total") and doc.doctype == RECEIPT:
		# a Receipt carries no freight: compare without the charges printed on the paper
		want = flt(data["grand_total"]) - sum(flt(c["amount"]) for c in tot["charges"])
		have = flt(doc.grand_total) + flt(tot["explained"])
		out["diff"] = round(have - want, 2)
		out["ok"] = 1 if tot["ok"] or abs(out["diff"]) <= TOTAL_TOL else 0
	else:
		out["diff"] = tot["diff"]
		out["ok"] = tot["ok"]
	return out
