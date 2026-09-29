# Copyright (c) 2026, Trustbit and contributors
# For license information, please see license.txt

"""Data for the School Book Dashboard page (/app/school-book-dashboard).

One call returns everything the page draws, for one school (a Customer Group such as
"School Debtors (RDPS)", sub-groups included) or for all schools, over a date range and
an Item Group (default "Books"), optionally narrowed to one Product Bundle.

Same sources as the School Book Sales Report: submitted Sales Invoices incl. POS bills,
Purchase Invoices and their debit notes, stock from Bin / the stock ledger. Quantities are
in stock UOM (returns are negative stock_qty rows, so SUM(stock_qty) is the nett qty);
money is Sales Invoice Item base_net_amount (after discount, before GST).
"""

import hashlib
import json
import time
from collections import defaultdict
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, nowdate

from trustbit_school_book_seller.trustbit_school_book.report.school_book_sales_report.school_book_sales_report import (
	natural_key,
)

ALLOWED_ROLES = [
	"System Manager",
	"Accounts Manager",
	"Accounts User",
	"Sales Manager",
	"Purchase Manager",
	"Purchase User",
	"Stock Manager",
	"Stock User",
]
CACHE_SECONDS = 600
LINES = "tmp_school_book_dashboard_lines"  # per-connection temporary table
TOP_BOOKS = 60
TOP_GROUPS = 12
TOP_SUBJECTS = 10
ALERT_ROWS = 5


@frappe.whitelist()
def get_dashboard_data(
	company=None, from_date=None, to_date=None, school=None, item_group=None, product_bundle=None, refresh=0
):
	frappe.only_for(ALLOWED_ROLES)

	f = frappe._dict(
		company=company or frappe.defaults.get_user_default("Company"),
		from_date=str(getdate(from_date or nowdate()[:4] + "-01-01")),
		to_date=str(getdate(to_date or nowdate())),
		school=school or None,
		item_group=item_group or None,
		product_bundle=product_bundle or None,
	)
	if not f.company:
		frappe.throw(_("Please select a Company"))
	if f.from_date > f.to_date:
		frappe.throw(_("From Date cannot be after To Date"))

	key = "school_book_dashboard:" + hashlib.md5(json.dumps(f, sort_keys=True).encode()).hexdigest()
	if not cint(refresh):
		cached = frappe.cache.get_value(key)
		if cached:
			return cached

	data = build_dashboard(f)
	frappe.cache.set_value(key, data, expires_in_sec=CACHE_SECONDS)
	return data


def build_dashboard(f):
	values = {"company": f.company, "from_date": f.from_date, "to_date": f.to_date}
	item_cond = get_item_condition(f, values)

	school_cond = ""
	if f.school:
		values["school_customers"] = tuple(get_school_customers(f.school)) or ("",)
		school_cond = "AND si.customer IN %(school_customers)s"

	sales_where = f"""
		si.docstatus = 1
		AND si.company = %(company)s
		AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
		{item_cond}
	"""

	timings = {}
	lap = Stopwatch(timings)
	# one pass over the invoices; books, breakdown and trend then read the small temp table
	lap("scope_lines", make_scope_lines, sales_where + school_cond, values)
	try:
		books = lap("books", get_book_sales)
		breakdown, mix = lap("breakdown", get_breakdown, f)
		trend = lap("trend", get_trend, f)
	finally:
		frappe.db.sql(f"DROP TEMPORARY TABLE IF EXISTS `{LINES}`")

	if f.school:
		# a school's books are also bought by shops and walk-ins outside the school's group
		values["book_items"] = tuple(books) or ("",)
		scope_items_cond = "AND {alias}.item_code IN %(book_items)s"
		nett_all = lap("nett_all", get_nett_all_buyers, values)
	else:
		scope_items_cond = item_cond.replace("sii.", "{alias}.")
		nett_all = {code: b["nett"] for code, b in books.items()}

	purchases = lap("purchases", get_purchases, f, values, scope_items_cond)
	stock = lap("stock", get_stock, f, values, scope_items_cond)

	rows = []
	for code, b in books.items():
		p = purchases.get(code, {})
		purchased = flt(p.get("purchased")) - flt(p.get("purchase_returned"))
		b.update(
			nett_all=flt(nett_all.get(code, b["nett"])),
			purchased=purchased,
			stock=flt(stock.get(code)),
		)
		b["sell_through"] = b["nett_all"] / purchased if purchased > 0 else None
		b["status"] = book_status(b)
		rows.append(b)
	rows.sort(key=lambda r: (-r["nett"], r["item_name"] or ""))

	totals = {
		"sold": sum(r["sold"] for r in rows),
		"returned": sum(r["returned"] for r in rows),
		"value": sum(r["value"] for r in rows),
		"counter_bills": sum(b["counter_bills"] for b in breakdown),
		"titles": len(rows),
	}
	totals["nett"] = totals["sold"] - totals["returned"]
	totals["return_rate"] = totals["returned"] / totals["sold"] if totals["sold"] else None

	# purchases and stock cover the scope's books: the school's books, or every book in the group
	purchased_total = sum(flt(p.get("purchased")) - flt(p.get("purchase_returned")) for p in purchases.values())
	nett_all_total = sum(flt(v) for v in nett_all.values())
	totals.update(
		purchased=purchased_total,
		nett_all=nett_all_total,
		sell_through=nett_all_total / purchased_total if purchased_total > 0 else None,
		stock=sum(flt(v) for v in stock.values()),
		negative_titles=sum(1 for v in stock.values() if flt(v) < 0),
	)

	return {
		"filters": f,
		"school_label": school_label(f.school),
		"totals": totals,
		"breakdown": breakdown,
		"trend": trend,
		"mix": get_mix(f, mix, totals, nett_all_total),
		"subjects": get_subjects(rows),
		"books": rows[:TOP_BOOKS],
		"alerts": get_alerts(rows, purchases, stock),
		"generated_at": frappe.utils.now(),
		"timings": {k: round(v, 2) for k, v in timings.items()},
	}


class Stopwatch:
	"""lap(name, fn, *args) runs fn and records its seconds under name."""

	def __init__(self, timings):
		self.timings = timings

	def __call__(self, name, fn, *args):
		start = time.monotonic()
		result = fn(*args)
		self.timings[name] = time.monotonic() - start
		return result


def get_item_condition(f, values):
	"""SQL on the sales item alias `sii` for the Item Group (with sub-groups) and Product Bundle."""
	cond = ""
	if f.item_group:
		values["item_groups"] = tuple(get_descendant_groups(f.item_group))
		cond += " AND sii.item_code IN (SELECT name FROM `tabItem` WHERE item_group IN %(item_groups)s)"
	if f.product_bundle:
		values["product_bundle"] = f.product_bundle
		cond += """ AND sii.item_code IN (
			SELECT item_code FROM `tabProduct Bundle Item`
			WHERE parenttype = 'Product Bundle' AND parent = %(product_bundle)s)"""
	return cond


def get_descendant_groups(item_group):
	return frappe.db.sql_list(
		"""
		SELECT child.name FROM `tabItem Group` child
		INNER JOIN `tabItem Group` selected ON child.lft >= selected.lft AND child.rgt <= selected.rgt
		WHERE selected.name = %s
		""",
		item_group,
	) or [item_group]


def get_school_customers(school):
	return frappe.db.sql_list(
		"""
		SELECT c.name FROM `tabCustomer` c
		INNER JOIN `tabCustomer Group` cg ON cg.name = c.customer_group
		INNER JOIN `tabCustomer Group` school ON cg.lft >= school.lft AND cg.rgt <= school.rgt
		WHERE school.name = %s
		""",
		school,
	)


def school_label(school):
	"""'School Debtors (RDPS)' -> 'RDPS'; anything else as is."""
	if not school:
		return _("All schools")
	if "(" in school and ")" in school:
		return school[school.index("(") + 1 : school.index(")")]
	return school


def make_scope_lines(where, values):
	"""Temporary table of the sales lines in scope. It lives only on this request's DB
	connection, so concurrent requests never see each other's rows."""
	if frappe.db.transaction_writes:
		# frappe refuses CREATE/DROP after an INSERT/UPDATE/DELETE in the same transaction
		# (implicit-commit guard); this call only reads, so close the transaction first
		frappe.db.commit()
	frappe.db.sql(f"DROP TEMPORARY TABLE IF EXISTS `{LINES}`")
	frappe.db.sql(
		f"""
		CREATE TEMPORARY TABLE `{LINES}` AS
		SELECT sii.item_code, si.name AS invoice, si.customer, IFNULL(c.customer_group, '') AS customer_group,
			si.posting_date, si.is_pos, si.is_return, sii.stock_qty, sii.base_net_amount AS value
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		LEFT JOIN `tabCustomer` c ON c.name = si.customer
		WHERE {where}
		""",
		values,
	)


def get_book_sales():
	"""{item_code: {...}} sold / returned / nett / value for the scope."""
	books = {}
	for d in frappe.db.sql(
		f"""
		SELECT l.item_code, i.item_name, i.custom_class AS book_class, i.custom_subject AS subject,
			l.sold, l.returned, l.value
		FROM (
			SELECT item_code,
				SUM(IF(is_return = 1, 0, stock_qty)) AS sold,
				SUM(IF(is_return = 1, -stock_qty, 0)) AS returned,
				SUM(value) AS value
			FROM `{LINES}`
			GROUP BY item_code
		) l
		INNER JOIN `tabItem` i ON i.name = l.item_code
		""",
		as_dict=True,
	):
		books[d.item_code] = {
			"item_code": d.item_code,
			"item_name": d.item_name,
			"book_class": d.book_class,
			"subject": d.subject,
			"sold": flt(d.sold),
			"returned": flt(d.returned),
			"nett": flt(d.sold) - flt(d.returned),
			"value": flt(d.value),
		}
	return books


def get_breakdown(f):
	"""Return (rows, mix) for the bar list and the buyer-mix bar.

	School chosen: one row per customer; class accounts (most books billed at the counter,
	one POS bill per student) first in class order, then shops and bulk buyers by qty.
	All schools: one row per customer group by qty, the tail folded into one row."""
	group_by = "customer" if f.school else "customer_group"
	rows = frappe.db.sql(
		f"""
		SELECT {group_by} AS label,
			SUM(IF(is_return = 1, 0, stock_qty)) AS sold,
			SUM(IF(is_return = 1, -stock_qty, 0)) AS returned,
			SUM(IF(is_pos = 1 AND is_return = 0, stock_qty, 0)) AS counter_sold,
			SUM(IF(is_pos = 1, stock_qty, 0)) AS counter_nett,
			SUM(value) AS value,
			COUNT(DISTINCT IF(is_pos = 1 AND is_return = 0, invoice, NULL)) AS counter_bills
		FROM `{LINES}`
		GROUP BY label
		""",
		as_dict=True,
	)
	for r in rows:
		for k in ("sold", "returned", "counter_sold", "counter_nett", "value"):
			r[k] = flt(r[k])
		r["counter_bills"] = cint(r.counter_bills)
		r["nett"] = r["sold"] - r["returned"]

	if f.school:
		counter = sum(r.counter_nett for r in rows)
		mix = {"counter": counter, "bulk": sum(r.nett for r in rows) - counter}
		classes = [r for r in rows if r.sold and r.counter_sold >= 0.5 * r.sold]
		others = [r for r in rows if not (r.sold and r.counter_sold >= 0.5 * r.sold)]
		classes.sort(key=lambda r: natural_key(r.label))
		others.sort(key=lambda r: -r.nett)
		for r in classes:
			r["kind"] = "class"
		for r in others:
			r["kind"] = "bulk"
		return classes + others, mix

	is_school_group = lambda label: label.lower().startswith("school debtors")
	mix = {
		"school": sum(r.nett for r in rows if is_school_group(r.label)),
		"other": sum(r.nett for r in rows if r.label and not is_school_group(r.label)),
		"none": sum(r.nett for r in rows if not r.label),
	}
	rows.sort(key=lambda r: -r.nett)
	for r in rows:
		r["kind"] = "group"
		r["drill"] = bool(r.label)
		r["muted"] = not r.label
		r["label"] = r.label or _("No customer group")
	if len(rows) > TOP_GROUPS:
		tail = rows[TOP_GROUPS:]
		rows = rows[:TOP_GROUPS] + [
			{
				"label": _("{0} other groups").format(len(tail)),
				"kind": "other",
				"drill": False,
				"muted": True,
				**{k: sum(t[k] for t in tail) for k in ("sold", "returned", "nett", "value", "counter_bills")},
			}
		]
	return rows, mix


def get_trend(f):
	"""Sold and returned qty per day, or per week (Monday) when the range is over 62 days."""
	daily = frappe.db.sql(
		f"""
		SELECT posting_date AS day,
			SUM(IF(is_return = 1, 0, stock_qty)) AS sold,
			SUM(IF(is_return = 1, -stock_qty, 0)) AS returned
		FROM `{LINES}`
		GROUP BY posting_date
		""",
		as_dict=True,
	)
	start, end = getdate(f.from_date), getdate(f.to_date)
	weekly = (end - start).days > 62

	def bucket(day):
		return day - timedelta(days=day.weekday()) if weekly else day

	sold, returned = defaultdict(float), defaultdict(float)
	for d in daily:
		sold[bucket(d.day)] += flt(d.sold)
		returned[bucket(d.day)] += flt(d.returned)

	labels, cursor, step = [], bucket(start), timedelta(days=7 if weekly else 1)
	while cursor <= end:
		labels.append(cursor)
		cursor += step
	return {
		"granularity": "week" if weekly else "day",
		"labels": [str(d) for d in labels],
		"sold": [sold[d] for d in labels],
		"returned": [returned[d] for d in labels],
	}


def get_nett_all_buyers(values):
	return dict(
		frappe.db.sql(
			"""
			SELECT sii.item_code, SUM(sii.stock_qty)
			FROM `tabSales Invoice Item` sii
			INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
			WHERE si.docstatus = 1
				AND si.company = %(company)s
				AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
				AND sii.item_code IN %(book_items)s
			GROUP BY sii.item_code
			""",
			values,
		)
	)


def get_mix(f, mix, totals, nett_all_total):
	"""Who bought the books (nett qty), three parts.
	School: its POS counter bills (students) / its other bills (shops, bulk) / buyers outside
	the school's customer group. All schools: "School Debtors" groups / other groups / none."""
	if f.school:
		label = school_label(f.school)
		parts = [
			(_("{0} counter (students)").format(label), mix["counter"]),
			(_("{0} shops & bulk").format(label), mix["bulk"]),
			(_("Buyers outside {0}").format(label), nett_all_total - totals["nett"]),
		]
	else:
		parts = [
			(_("School accounts"), mix["school"]),
			(_("Other customer groups"), mix["other"]),
			(_("No customer group"), mix["none"]),
		]
	return [{"label": label, "qty": max(flt(qty), 0)} for label, qty in parts]


def get_purchases(f, values, scope_items_cond):
	"""{item_code: {purchased, purchase_returned}} from Purchase Invoices and debit notes."""
	purchases = {}
	for d in frappe.db.sql(
		f"""
		SELECT pii.item_code,
			SUM(IF(pi.is_return = 1, 0, pii.stock_qty)) AS purchased,
			SUM(IF(pi.is_return = 1, -pii.stock_qty, 0)) AS purchase_returned
		FROM `tabPurchase Invoice Item` pii
		INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
		WHERE pi.docstatus = 1
			AND pi.company = %(company)s
			AND pi.posting_date BETWEEN %(from_date)s AND %(to_date)s
			{scope_items_cond.format(alias="pii")}
		GROUP BY pii.item_code
		""",
		values,
		as_dict=True,
	):
		purchases[d.item_code] = d
	return purchases


def get_stock(f, values, scope_items_cond):
	"""{item_code: qty} across the company's warehouses: Bin when To Date is today or later,
	otherwise the balance after each warehouse's last ledger entry up to To Date (a Stock
	Reconciliation entry has actual_qty 0, so the ledger is never summed)."""
	if getdate(f.to_date) >= getdate(nowdate()):
		return dict(
			frappe.db.sql(
				f"""
				SELECT b.item_code, SUM(b.actual_qty)
				FROM `tabBin` b
				INNER JOIN `tabWarehouse` w ON w.name = b.warehouse
				WHERE w.company = %(company)s {scope_items_cond.format(alias="b")}
				GROUP BY b.item_code
				""",
				values,
			)
		)
	return dict(
		frappe.db.sql(
			f"""
			SELECT item_code, SUM(qty_after_transaction)
			FROM (
				SELECT sle.item_code, sle.qty_after_transaction,
					ROW_NUMBER() OVER (
						PARTITION BY sle.item_code, sle.warehouse
						ORDER BY sle.posting_date DESC, sle.posting_time DESC, sle.creation DESC
					) AS entry_no
				FROM `tabStock Ledger Entry` sle
				WHERE sle.is_cancelled = 0
					AND sle.company = %(company)s
					AND sle.posting_date <= %(to_date)s
					{scope_items_cond.format(alias="sle")}
			) last_entry
			WHERE entry_no = 1
			GROUP BY item_code
			""",
			values,
		)
	)


def book_status(b):
	"""critical: negative stock; serious: sold but not bought in the period; warning: a lot
	left over (at least 10 books and 20% of what was bought); good otherwise."""
	if b["stock"] < 0:
		return "negative"
	if b["purchased"] <= 0 and b["nett_all"] > 0:
		return "not_bought"
	if b["purchased"] > 0 and b["stock"] >= max(10, 0.2 * b["purchased"]):
		return "excess"
	return "ok"


def get_subjects(rows):
	"""Nett qty per subject, case-insensitive ("HINDI" = "Hindi"); the top ones, then one
	"Other subjects" row. "No subject" and "Other" are flagged muted for the grey bar."""
	by_subject, spelling = defaultdict(float), {}
	for r in rows:
		# "." and "-" are used as placeholders on many book items
		subject = (r["subject"] or "").strip()
		key = subject.lower() if subject.strip(" .-_/") else ""
		spelling.setdefault(key, subject)
		by_subject[key] += r["nett"]
	ranked = sorted(((k, v) for k, v in by_subject.items() if k), key=lambda kv: -kv[1])
	top = [{"label": spelling[k], "nett": v} for k, v in ranked[:TOP_SUBJECTS]]
	if len(ranked) > TOP_SUBJECTS:
		top.append({"label": _("Other subjects"), "nett": sum(v for k, v in ranked[TOP_SUBJECTS:]), "muted": 1})
	if by_subject.get(""):
		top.append({"label": _("No subject"), "nett": by_subject[""], "muted": 1})
	return top


def get_alerts(rows, purchases, stock):
	negative = sorted(((code, flt(q)) for code, q in stock.items() if flt(q) < 0), key=lambda x: x[1])
	excess = []
	for code, p in purchases.items():
		bought = flt(p.purchased) - flt(p.purchase_returned)
		left = flt(stock.get(code))
		if bought > 0 and left >= max(10, 0.2 * bought):
			excess.append((code, left, bought))
	excess.sort(key=lambda x: -x[1])
	returns = sorted(
		(r for r in rows if r["sold"] >= 20 and r["returned"] / r["sold"] >= 0.1),
		key=lambda r: -(r["returned"] / r["sold"]),
	)

	# names only for the rows shown; in "all schools" the stock map covers every book
	names = {r["item_code"]: r["item_name"] for r in rows}
	shown = [c for c, q in negative[:ALERT_ROWS]] + [c for c, left, bought in excess[:ALERT_ROWS]]
	missing = tuple(c for c in shown if c not in names)
	if missing:
		names.update(dict(frappe.db.sql("SELECT name, item_name FROM `tabItem` WHERE name IN %s", (missing,))))

	return {
		"negative": [{"item_code": c, "item_name": names.get(c) or c, "stock": q} for c, q in negative[:ALERT_ROWS]],
		"negative_count": len(negative),
		"excess": [
			{"item_code": c, "item_name": names.get(c) or c, "stock": left, "purchased": bought}
			for c, left, bought in excess[:ALERT_ROWS]
		],
		"excess_count": len(excess),
		"returns": [
			{"item_code": r["item_code"], "item_name": r["item_name"], "rate": r["returned"] / r["sold"], "returned": r["returned"]}
			for r in returns[:ALERT_ROWS]
		],
		"returns_count": len(returns),
	}
