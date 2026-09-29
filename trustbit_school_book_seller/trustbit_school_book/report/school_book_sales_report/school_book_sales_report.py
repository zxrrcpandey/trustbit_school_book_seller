# Copyright (c) 2026, Trustbit and contributors
# For license information, please see license.txt

"""Item-wise sale / return qty per customer (e.g. one column group per school class),
set against the purchases and stock of the same books.

All quantities are in stock UOM (a PKT of 10 counts as 10). Sales come from submitted
Sales Invoices, POS bills included; purchase returns are Purchase Invoice debit notes.
"""

import re

import frappe
from frappe import _
from frappe.utils import cint, flt, formatdate, getdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)

	if not filters.product_bundle and not filters.item_code:
		return get_columns(filters, [], False), [], _("Select a Product Bundle or an Item.")

	items = get_items(filters)
	if not items:
		return get_columns(filters, [], False), []

	item_codes = [d.item_code for d in items]
	sales = get_sales(filters, item_codes)
	customers, show_other = get_customer_columns(filters, sales)

	columns = get_columns(filters, customers, show_other)
	data = get_data(filters, items, sales, customers, show_other)
	return columns, data


def validate_filters(filters):
	for key in ("product_bundle", "item_code", "school", "customer"):
		filters[key] = as_list(filters.get(key))

	if not filters.company:
		frappe.throw(_("Please select a Company"))
	if not filters.from_date or not filters.to_date:
		frappe.throw(_("Please set From Date and To Date"))
	if getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be after To Date"))

	filters.show_other_customers = cint(filters.get("show_other_customers", 1))


def as_list(value):
	"""MultiSelectList filters arrive as a list, or as a JSON string through the API."""
	if not value:
		return []
	if isinstance(value, str):
		value = frappe.parse_json(value) if value.startswith("[") else [value]
	return [v for v in value if v]


def get_items(filters):
	"""Components of the selected Product Bundles plus the selected Items, by item code."""
	item_codes = set(filters.item_code)
	if filters.product_bundle:
		item_codes.update(
			frappe.db.sql_list(
				"""
				SELECT item_code FROM `tabProduct Bundle Item`
				WHERE parenttype = 'Product Bundle' AND parent IN %(bundles)s
				""",
				{"bundles": tuple(filters.product_bundle)},
			)
		)

	if not item_codes:
		return []

	return frappe.db.sql(
		"""
		SELECT name AS item_code, item_name, stock_uom
		FROM `tabItem`
		WHERE name IN %(items)s
		ORDER BY name
		""",
		{"items": tuple(item_codes)},
		as_dict=True,
	)


def get_sales(filters, item_codes):
	"""{(item_code, customer): (sale_qty, return_qty)}, return qty as a positive number."""
	rows = frappe.db.sql(
		"""
		SELECT sii.item_code, si.customer,
			SUM(IF(si.is_return = 1, 0, sii.stock_qty)) AS sale_qty,
			SUM(IF(si.is_return = 1, -sii.stock_qty, 0)) AS return_qty
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.docstatus = 1
			AND si.company = %(company)s
			AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
			AND sii.item_code IN %(items)s
		GROUP BY sii.item_code, si.customer
		""",
		get_query_values(filters, item_codes),
		as_dict=True,
	)
	return {(d.item_code, d.customer): (flt(d.sale_qty), flt(d.return_qty)) for d in rows}


def get_customer_columns(filters, sales):
	"""Return (customers that get their own columns, whether to add an "Other Customers" group).

	No customer or school chosen: every customer who bought or returned these books gets columns.
	Otherwise: the chosen customers (always), plus the chosen schools' customers who bought or
	returned these books; everyone else goes into "Other Customers" when that box is ticked.
	"""
	buyers = {customer for (item_code, customer), qty in sales.items() if qty[0] or qty[1]}

	if not filters.customer and not filters.school:
		return sorted(buyers, key=natural_key), False

	selected = set(filters.customer)
	if filters.school:
		school_customers = frappe.db.sql_list(
			"""
			SELECT c.name
			FROM `tabCustomer` c
			INNER JOIN `tabCustomer Group` cg ON cg.name = c.customer_group
			INNER JOIN `tabCustomer Group` school ON cg.lft >= school.lft AND cg.rgt <= school.rgt
			WHERE school.name IN %(schools)s
			""",
			{"schools": tuple(filters.school)},
		)
		selected.update(buyers.intersection(school_customers))

	return sorted(selected, key=natural_key), bool(filters.show_other_customers)


def natural_key(name):
	"""Sort "RDPS 2" before "RDPS 10"."""
	return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]


def get_columns(filters, customers, show_other):
	columns = [
		{
			"label": _("Item Code"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 140,
		},
		{
			"label": _("Item Name"),
			"fieldname": "item_name",
			"fieldtype": "Data",
			"width": 240,
		},
	]

	for prefix, label in get_sale_groups(customers, show_other) + [("total", _("Total"))]:
		columns += [
			qty_column(_("{0} Sale Qty").format(label), prefix + "_sale"),
			qty_column(_("{0} Return Qty").format(label), prefix + "_return"),
			qty_column(_("{0} Nett Sale Qty").format(label), prefix + "_nett"),
		]

	columns += [
		qty_column(_("Purchase Order Qty"), "po_qty"),
		qty_column(_("Purchase Receipt Qty"), "pr_qty"),
		qty_column(_("Purchase Qty"), "purchase_qty"),
		qty_column(_("Purchase Return Qty"), "purchase_return_qty"),
		qty_column(_("Nett Purchase Qty"), "nett_purchase_qty"),
		qty_column(_("Difference"), "difference"),
		qty_column(_("Stock on {0}").format(formatdate(filters.to_date)), "stock_qty"),
		{
			"label": _("MRP"),
			"fieldname": "mrp",
			"fieldtype": "Currency",
			"width": 100,
			"disable_total": 1,
		},
	]
	return columns


def get_sale_groups(customers, show_other):
	"""[(fieldname prefix, label)] for each customer column group, "Other Customers" last."""
	groups = [(f"c{i}", customer) for i, customer in enumerate(customers)]
	if show_other:
		groups.append(("other", _("Other Customers")))
	return groups


def qty_column(label, fieldname):
	# Int, not Float: report Float columns always show 3 decimals, and book qty in stock UOM is whole
	return {"label": label, "fieldname": fieldname, "fieldtype": "Int", "width": 120}


def get_data(filters, items, sales, customers, show_other):
	item_codes = [d.item_code for d in items]
	purchases = get_purchases(filters, item_codes)
	stock = get_stock(filters, item_codes)
	mrp = get_mrp(filters, items)

	sales_by_item = {}
	for (item_code, customer), qty in sales.items():
		sales_by_item.setdefault(item_code, {})[customer] = qty

	own_columns = set(customers)
	prefixes = [prefix for prefix, label in get_sale_groups(customers, show_other)]

	data = []
	for item in items:
		item_sales = sales_by_item.get(item.item_code, {})
		row = {"item_code": item.item_code, "item_name": item.item_name}

		for i, customer in enumerate(customers):
			set_sale_qty(row, f"c{i}", *item_sales.get(customer, (0, 0)))

		if show_other:
			others = [qty for customer, qty in item_sales.items() if customer not in own_columns]
			set_sale_qty(row, "other", sum(q[0] for q in others), sum(q[1] for q in others))

		set_sale_qty(
			row,
			"total",
			sum(row[p + "_sale"] for p in prefixes),
			sum(row[p + "_return"] for p in prefixes),
		)

		purchase = purchases.get(item.item_code, {})
		row.update(
			{
				"po_qty": flt(purchase.get("po_qty")),
				"pr_qty": flt(purchase.get("pr_qty")),
				"purchase_qty": flt(purchase.get("purchase_qty")),
				"purchase_return_qty": flt(purchase.get("purchase_return_qty")),
			}
		)
		row["nett_purchase_qty"] = row["purchase_qty"] - row["purchase_return_qty"]
		row["difference"] = row["nett_purchase_qty"] - row["total_nett"]
		row["stock_qty"] = flt(stock.get(item.item_code))
		row["mrp"] = mrp.get(item.item_code)
		data.append(row)

	return data


def set_sale_qty(row, prefix, sale_qty, return_qty):
	row[prefix + "_sale"] = sale_qty
	row[prefix + "_return"] = return_qty
	row[prefix + "_nett"] = sale_qty - return_qty


def get_purchases(filters, item_codes):
	"""{item_code: {po_qty, pr_qty, purchase_qty, purchase_return_qty}}.

	PO qty counts submitted POs dated in the period: with the PO approval workflow a PO is
	submitted only when approved (older POs were stamped Approved at go-live), and a cancelled
	PO is left out while its amended copy counts once.
	"""
	values = get_query_values(filters, item_codes)
	purchases = {item_code: {} for item_code in item_codes}

	queries = {
		"po_qty": """
			SELECT poi.item_code, SUM(poi.stock_qty) AS po_qty
			FROM `tabPurchase Order Item` poi
			INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
			WHERE po.docstatus = 1
				AND po.company = %(company)s
				AND po.transaction_date BETWEEN %(from_date)s AND %(to_date)s
				AND poi.item_code IN %(items)s
			GROUP BY poi.item_code
		""",
		"pr_qty": """
			SELECT pri.item_code, SUM(pri.stock_qty) AS pr_qty
			FROM `tabPurchase Receipt Item` pri
			INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
			WHERE pr.docstatus = 1
				AND pr.is_return = 0
				AND pr.company = %(company)s
				AND pr.posting_date BETWEEN %(from_date)s AND %(to_date)s
				AND pri.item_code IN %(items)s
			GROUP BY pri.item_code
		""",
		"purchase_qty": """
			SELECT pii.item_code,
				SUM(IF(pi.is_return = 1, 0, pii.stock_qty)) AS purchase_qty,
				SUM(IF(pi.is_return = 1, -pii.stock_qty, 0)) AS purchase_return_qty
			FROM `tabPurchase Invoice Item` pii
			INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
			WHERE pi.docstatus = 1
				AND pi.company = %(company)s
				AND pi.posting_date BETWEEN %(from_date)s AND %(to_date)s
				AND pii.item_code IN %(items)s
			GROUP BY pii.item_code
		""",
	}
	for query in queries.values():
		for d in frappe.db.sql(query, values, as_dict=True):
			item_code = d.pop("item_code")
			purchases[item_code].update(d)

	return purchases


def get_stock(filters, item_codes):
	"""{item_code: stock qty across the company's warehouses at the end of To Date}.

	Uses the balance after each warehouse's last entry, not SUM(actual_qty): a Stock
	Reconciliation entry carries actual_qty 0 and resets the balance to the counted qty.
	"""
	return dict(
		frappe.db.sql(
			"""
			SELECT item_code, SUM(qty_after_transaction)
			FROM (
				SELECT item_code, qty_after_transaction,
					ROW_NUMBER() OVER (
						PARTITION BY item_code, warehouse
						ORDER BY posting_date DESC, posting_time DESC, creation DESC
					) AS entry_no
				FROM `tabStock Ledger Entry`
				WHERE is_cancelled = 0
					AND company = %(company)s
					AND posting_date <= %(to_date)s
					AND item_code IN %(items)s
			) last_entry
			WHERE entry_no = 1
			GROUP BY item_code
			""",
			get_query_values(filters, item_codes),
		)
	)


def get_mrp(filters, items):
	"""{item_code: selling price on To Date} from the default selling price list.

	Picks the row ERPNext's get_item_price would: valid on the date, not tied to a customer,
	supplier or batch, for the stock UOM (or no UOM), latest valid_from first.
	"""
	price_list = frappe.db.get_single_value("Selling Settings", "selling_price_list") or "Standard Selling"
	stock_uom = {d.item_code: d.stock_uom for d in items}

	rows = frappe.db.sql(
		"""
		SELECT item_code, uom, price_list_rate
		FROM `tabItem Price`
		WHERE price_list = %(price_list)s
			AND item_code IN %(items)s
			AND IFNULL(customer, '') = ''
			AND IFNULL(supplier, '') = ''
			AND IFNULL(batch_no, '') = ''
			AND IFNULL(valid_from, '2000-01-01') <= %(to_date)s
			AND IFNULL(valid_upto, '2500-12-31') >= %(to_date)s
		ORDER BY valid_from DESC, uom DESC, modified DESC
		""",
		{"price_list": price_list, "items": tuple(stock_uom), "to_date": filters.to_date},
		as_dict=True,
	)

	mrp = {}
	for d in rows:
		if d.item_code not in mrp and (d.uom or "") in ("", stock_uom[d.item_code]):
			mrp[d.item_code] = flt(d.price_list_rate)
	return mrp


def get_query_values(filters, item_codes):
	return {
		"company": filters.company,
		"from_date": filters.from_date,
		"to_date": filters.to_date,
		"items": tuple(item_codes),
	}
