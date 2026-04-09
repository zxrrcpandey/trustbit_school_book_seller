import frappe
from frappe import _
from frappe.utils import flt, nowdate, getdate, add_days
import json


@frappe.whitelist()
def get_dashboard_kpis(from_date=None, to_date=None, user=None):
	"""Get key dashboard metrics: revenue, orders, bundles sold, loose sales."""
	if not from_date:
		from_date = nowdate()
	if not to_date:
		to_date = nowdate()

	filters = {"docstatus": 1, "posting_date": ["between", [from_date, to_date]]}
	if user:
		filters["owner"] = user

	# Revenue and order count
	data = frappe.db.sql("""
		SELECT
			COUNT(*) as order_count,
			COALESCE(SUM(grand_total), 0) as revenue,
			COALESCE(SUM(total_qty), 0) as total_qty
		FROM `tabSales Invoice`
		WHERE docstatus = 1
			AND posting_date BETWEEN %s AND %s
			{user_filter}
	""".format(user_filter="AND owner = %s" if user else ""),
		tuple([from_date, to_date] + ([user] if user else [])),
		as_dict=1
	)[0]

	# Bundle vs loose sales
	bundle_data = frappe.db.sql("""
		SELECT
			COUNT(DISTINCT si.name) as bundle_orders,
			COALESCE(SUM(CASE WHEN sii.custom_bundle_id IS NOT NULL AND sii.custom_bundle_id != '' THEN sii.amount ELSE 0 END), 0) as bundle_revenue,
			COALESCE(SUM(CASE WHEN sii.custom_bundle_id IS NULL OR sii.custom_bundle_id = '' THEN sii.amount ELSE 0 END), 0) as loose_revenue,
			COUNT(CASE WHEN sii.custom_bundle_id IS NOT NULL AND sii.custom_bundle_id != '' THEN 1 END) as bundle_items,
			COUNT(CASE WHEN sii.custom_bundle_id IS NULL OR sii.custom_bundle_id = '' THEN 1 END) as loose_items
		FROM `tabSales Invoice Item` sii
		JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.docstatus = 1
			AND si.posting_date BETWEEN %s AND %s
			{user_filter}
	""".format(user_filter="AND si.owner = %s" if user else ""),
		tuple([from_date, to_date] + ([user] if user else [])),
		as_dict=1
	)[0]

	# Distinct bundles sold
	bundles_sold = frappe.db.sql("""
		SELECT COUNT(DISTINCT sii.custom_bundle_id) as count
		FROM `tabSales Invoice Item` sii
		JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.docstatus = 1
			AND si.posting_date BETWEEN %s AND %s
			AND sii.custom_bundle_id IS NOT NULL AND sii.custom_bundle_id != ''
			{user_filter}
	""".format(user_filter="AND si.owner = %s" if user else ""),
		tuple([from_date, to_date] + ([user] if user else [])),
	)[0][0] or 0

	# Yesterday comparison
	yesterday = str(add_days(getdate(from_date), -1))
	yest_data = frappe.db.sql("""
		SELECT COUNT(*) as orders, COALESCE(SUM(grand_total), 0) as revenue
		FROM `tabSales Invoice`
		WHERE docstatus = 1 AND posting_date = %s
			{user_filter}
	""".format(user_filter="AND owner = %s" if user else ""),
		tuple([yesterday] + ([user] if user else [])),
		as_dict=1
	)[0]

	revenue_change = 0
	if yest_data.revenue > 0:
		revenue_change = round((flt(data.revenue) - flt(yest_data.revenue)) / flt(yest_data.revenue) * 100, 1)

	order_change = 0
	if yest_data.orders > 0:
		order_change = round((flt(data.order_count) - flt(yest_data.orders)) / flt(yest_data.orders) * 100, 1)

	return {
		"revenue": flt(data.revenue, 2),
		"order_count": data.order_count,
		"total_qty": flt(data.total_qty),
		"bundles_sold": bundles_sold,
		"bundle_revenue": flt(bundle_data.bundle_revenue, 2),
		"loose_revenue": flt(bundle_data.loose_revenue, 2),
		"bundle_items": bundle_data.bundle_items,
		"loose_items": bundle_data.loose_items,
		"revenue_change": revenue_change,
		"order_change": order_change,
	}


@frappe.whitelist()
def get_bundle_stock_report():
	"""Get sellable sets for each Product Bundle based on component stock.
	sellable_sets = min(actual_qty / bundle_item_qty) across all components."""

	default_warehouse = frappe.db.get_single_value("Stock Settings", "default_warehouse") or ""

	# Get all active bundles
	bundles = frappe.get_all("Product Bundle",
		filters={"disabled": 0},
		fields=["name", "new_item_code", "description", "custom_sell_goal"],
	)

	if not bundles:
		return []

	bundle_names = [b.name for b in bundles]

	# Batch fetch all bundle items
	all_items = frappe.get_all("Product Bundle Item",
		filters={"parent": ["in", bundle_names]},
		fields=["parent", "item_code", "qty", "custom_product_bundle_stock"],
	)

	# Batch fetch stock for all unique item codes
	item_codes = list(set(i.item_code for i in all_items))
	stock_data = {}
	if item_codes:
		bins = frappe.get_all("Bin",
			filters={"item_code": ["in", item_codes], "warehouse": default_warehouse},
			fields=["item_code", "actual_qty"],
		)
		stock_data = {b.item_code: flt(b.actual_qty) for b in bins}

	# Batch fetch sold count per bundle (current month)
	first_of_month = getdate(nowdate()).replace(day=1)
	sold_data = frappe.db.sql("""
		SELECT sii.custom_bundle_id as bundle, COUNT(DISTINCT si.name) as sold_count
		FROM `tabSales Invoice Item` sii
		JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.docstatus = 1
			AND si.posting_date >= %s
			AND sii.custom_bundle_id IS NOT NULL AND sii.custom_bundle_id != ''
		GROUP BY sii.custom_bundle_id
	""", (first_of_month,), as_dict=1)
	sold_map = {d.bundle: d.sold_count for d in sold_data}

	# Group items by bundle
	bundle_items_map = {}
	for item in all_items:
		bundle_items_map.setdefault(item.parent, []).append(item)

	result = []
	for bundle in bundles:
		items = bundle_items_map.get(bundle.name, [])
		if not items:
			continue

		# Filter available items
		available_items = [i for i in items if (i.custom_product_bundle_stock or "Available") != "Not Available"]
		na_count = len(items) - len(available_items)

		# Calculate sellable sets
		sellable_sets = float('inf')
		blocking_item = None
		blocking_stock = 0

		for item in available_items:
			qty_per_set = flt(item.qty) or 1
			stock = stock_data.get(item.item_code, 0)
			sets = int(stock / qty_per_set)

			if sets < sellable_sets:
				sellable_sets = sets
				blocking_item = item.item_code
				blocking_stock = stock

		if sellable_sets == float('inf'):
			sellable_sets = 0

		goal = flt(bundle.custom_sell_goal) or 0
		sold = sold_map.get(bundle.name, 0)
		gap = goal - sold - sellable_sets if goal else 0

		# Status
		if sellable_sets == 0:
			status = "out"
		elif sellable_sets < 5:
			status = "low"
		else:
			status = "ok"

		# Get blocking item name
		blocking_item_name = ""
		if blocking_item and sellable_sets < 10:
			blocking_item_name = frappe.db.get_value("Item", blocking_item, "item_name") or blocking_item

		result.append({
			"bundle": bundle.name,
			"description": bundle.description or bundle.name,
			"sellable_sets": sellable_sets,
			"goal": goal,
			"sold": sold,
			"gap": gap,
			"na_count": na_count,
			"total_items": len(items),
			"status": status,
			"blocking_item": blocking_item_name,
			"blocking_stock": blocking_stock,
		})

	# Sort: out first, then low, then ok
	status_order = {"out": 0, "low": 1, "ok": 2}
	result.sort(key=lambda x: (status_order.get(x["status"], 9), -x.get("goal", 0)))

	return result


@frappe.whitelist()
def get_short_items():
	"""Get items where stock is less than total demand across all bundles with goals."""

	default_warehouse = frappe.db.get_single_value("Stock Settings", "default_warehouse") or ""

	# Get demand: sum of (bundle_item.qty * bundle.custom_sell_goal) per item
	demand_data = frappe.db.sql("""
		SELECT
			pbi.item_code,
			SUM(pbi.qty * COALESCE(pb.custom_sell_goal, 0)) as total_demand
		FROM `tabProduct Bundle Item` pbi
		JOIN `tabProduct Bundle` pb ON pb.name = pbi.parent
		WHERE pb.disabled = 0
			AND pb.custom_sell_goal > 0
			AND (pbi.custom_product_bundle_stock IS NULL OR pbi.custom_product_bundle_stock != 'Not Available')
		GROUP BY pbi.item_code
		HAVING total_demand > 0
	""", as_dict=1)

	if not demand_data:
		return []

	item_codes = [d.item_code for d in demand_data]

	# Batch fetch stock
	bins = frappe.get_all("Bin",
		filters={"item_code": ["in", item_codes], "warehouse": default_warehouse},
		fields=["item_code", "actual_qty"],
	)
	stock_map = {b.item_code: flt(b.actual_qty) for b in bins}

	# Batch fetch item names
	items = frappe.get_all("Item",
		filters={"name": ["in", item_codes]},
		fields=["name", "item_name"],
	)
	name_map = {i.name: i.item_name for i in items}

	result = []
	for d in demand_data:
		stock = stock_map.get(d.item_code, 0)
		gap = stock - flt(d.total_demand)
		if gap < 0:
			result.append({
				"item_code": d.item_code,
				"item_name": name_map.get(d.item_code, d.item_code),
				"stock": flt(stock),
				"need": flt(d.total_demand),
				"gap": flt(gap),
			})

	result.sort(key=lambda x: x["gap"])
	return result


@frappe.whitelist()
def get_po_status():
	"""Get Purchase Order status breakdown: pending, stuck, on the way, received."""

	today = nowdate()
	week_ago = str(add_days(getdate(today), -7))

	# All open POs
	open_pos = frappe.get_all("Purchase Order",
		filters={"docstatus": 1, "status": ["not in", ["Completed", "Cancelled", "Closed"]]},
		fields=["name", "supplier_name", "transaction_date", "per_received",
				"custom_total_followups", "custom_last_followup_date",
				"custom_last_followup_status", "custom_next_followup_date"],
	)

	stuck = []
	need_followup = []
	on_the_way = []
	pending = []

	for po in open_pos:
		age_days = (getdate(today) - getdate(po.transaction_date)).days

		if po.custom_last_followup_status in ("Dispatched", "Partially Dispatched"):
			on_the_way.append({
				"name": po.name, "supplier": po.supplier_name,
				"age": age_days, "status": po.custom_last_followup_status,
				"followups": po.custom_total_followups,
			})
		elif age_days > 7 and (not po.custom_total_followups or po.custom_total_followups == 0):
			stuck.append({
				"name": po.name, "supplier": po.supplier_name,
				"age": age_days, "followups": 0,
			})
		elif po.custom_next_followup_date and getdate(po.custom_next_followup_date) <= getdate(today):
			need_followup.append({
				"name": po.name, "supplier": po.supplier_name,
				"age": age_days, "next_date": str(po.custom_next_followup_date),
				"followups": po.custom_total_followups,
			})
		else:
			pending.append({
				"name": po.name, "supplier": po.supplier_name,
				"age": age_days, "followups": po.custom_total_followups or 0,
			})

	# Received today
	received = frappe.db.sql("""
		SELECT pr.name, pr.supplier_name,
			COUNT(pri.item_code) as items_received,
			(SELECT COUNT(*) FROM `tabPurchase Receipt Item` WHERE parent = pr.name) as total_items
		FROM `tabPurchase Receipt` pr
		JOIN `tabPurchase Receipt Item` pri ON pri.parent = pr.name
		WHERE pr.docstatus = 1 AND pr.posting_date = %s
		GROUP BY pr.name
	""", (today,), as_dict=1)

	# Sort stuck by age descending
	stuck.sort(key=lambda x: -x["age"])
	need_followup.sort(key=lambda x: x.get("next_date", ""))

	return {
		"stuck": stuck,
		"need_followup": need_followup,
		"on_the_way": on_the_way,
		"pending": pending,
		"received_today": received,
		"summary": {
			"total": len(open_pos),
			"stuck": len(stuck),
			"need_followup": len(need_followup),
			"on_the_way": len(on_the_way),
			"pending": len(pending),
			"received_today": len(received),
		}
	}


@frappe.whitelist()
def get_employee_performance(date=None):
	"""Get per-employee sales performance for a given date."""

	if not date:
		date = nowdate()

	data = frappe.db.sql("""
		SELECT
			si.owner as user,
			COUNT(*) as orders,
			COALESCE(SUM(si.grand_total), 0) as revenue,
			COALESCE(SUM(si.total_qty), 0) as total_qty,
			MIN(si.posting_time) as first_sale,
			MAX(si.posting_time) as last_sale
		FROM `tabSales Invoice` si
		WHERE si.docstatus = 1 AND si.posting_date = %s
		GROUP BY si.owner
		ORDER BY revenue DESC
	""", (date,), as_dict=1)

	# Get POS shift info
	shifts = frappe.get_all("POS Opening Shift",
		filters={"posting_date": date, "status": ["in", ["Open", "Closed"]]},
		fields=["user", "pos_profile", "period_start_date"],
	)
	shift_map = {s.user: {"profile": s.pos_profile, "start": str(s.period_start_date)} for s in shifts}

	# Get full names
	users = list(set(d.user for d in data))
	user_names = {}
	if users:
		for u in frappe.get_all("User", filters={"name": ["in", users]}, fields=["name", "full_name"]):
			user_names[u.name] = u.full_name

	result = []
	for d in data:
		shift = shift_map.get(d.user, {})
		result.append({
			"user": d.user,
			"full_name": user_names.get(d.user, d.user),
			"orders": d.orders,
			"revenue": flt(d.revenue, 2),
			"total_qty": flt(d.total_qty),
			"first_sale": str(d.first_sale)[:5] if d.first_sale else "",
			"last_sale": str(d.last_sale)[:5] if d.last_sale else "",
			"pos_profile": shift.get("profile", ""),
			"shift_start": shift.get("start", ""),
		})

	return result


@frappe.whitelist()
def get_loose_sales(date=None):
	"""Get items sold outside bundles (loose sales) for a given date."""

	if not date:
		date = nowdate()

	data = frappe.db.sql("""
		SELECT
			sii.item_code,
			sii.item_name,
			SUM(sii.qty) as qty,
			SUM(sii.amount) as amount,
			sii.item_group
		FROM `tabSales Invoice Item` sii
		JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.docstatus = 1
			AND si.posting_date = %s
			AND (sii.custom_bundle_id IS NULL OR sii.custom_bundle_id = '')
		GROUP BY sii.item_code
		ORDER BY amount DESC
	""", (date,), as_dict=1)

	total_qty = sum(flt(d.qty) for d in data)
	total_amount = sum(flt(d.amount) for d in data)

	return {
		"items": data,
		"total_qty": flt(total_qty),
		"total_amount": flt(total_amount, 2),
		"total_orders": len(data),
	}


@frappe.whitelist()
def get_revenue_trend(days=7):
	"""Get daily revenue for the last N days."""

	days = int(days)
	from_date = str(add_days(getdate(nowdate()), -(days - 1)))

	data = frappe.db.sql("""
		SELECT
			posting_date as date,
			COUNT(*) as orders,
			COALESCE(SUM(grand_total), 0) as revenue
		FROM `tabSales Invoice`
		WHERE docstatus = 1
			AND posting_date >= %s
		GROUP BY posting_date
		ORDER BY posting_date
	""", (from_date,), as_dict=1)

	# Fill gaps (days with no sales)
	result = []
	current = getdate(from_date)
	end = getdate(nowdate())
	data_map = {str(d.date): d for d in data}

	while current <= end:
		date_str = str(current)
		if date_str in data_map:
			result.append({
				"date": date_str,
				"revenue": flt(data_map[date_str].revenue, 2),
				"orders": data_map[date_str].orders,
			})
		else:
			result.append({"date": date_str, "revenue": 0, "orders": 0})
		current = add_days(current, 1)

	return result


@frappe.whitelist()
def get_payment_breakdown(date=None):
	"""Get payment method breakdown for a given date."""

	if not date:
		date = nowdate()

	data = frappe.db.sql("""
		SELECT
			sip.mode_of_payment,
			COALESCE(SUM(sip.amount), 0) as amount
		FROM `tabSales Invoice Payment` sip
		JOIN `tabSales Invoice` si ON si.name = sip.parent
		WHERE si.docstatus = 1
			AND si.posting_date = %s
		GROUP BY sip.mode_of_payment
		ORDER BY amount DESC
	""", (date,), as_dict=1)

	return data


@frappe.whitelist()
def get_recent_invoices(limit=10, user=None):
	"""Get recent Sales Invoices for the invoice ticker/list."""

	filters = {"docstatus": 1}
	if user:
		filters["owner"] = user

	invoices = frappe.get_all("Sales Invoice",
		filters=filters,
		fields=["name", "customer_name", "grand_total", "total_qty",
				"posting_date", "posting_time", "owner"],
		order_by="creation desc",
		limit=limit,
	)

	# Check which have bundle items
	if invoices:
		inv_names = [i.name for i in invoices]
		bundle_invoices = frappe.db.sql("""
			SELECT DISTINCT parent
			FROM `tabSales Invoice Item`
			WHERE parent IN ({})
				AND custom_bundle_id IS NOT NULL AND custom_bundle_id != ''
		""".format(", ".join(["%s"] * len(inv_names))),
			tuple(inv_names),
		)
		bundle_set = set(r[0] for r in bundle_invoices)

		# Get user full names
		users = list(set(i.owner for i in invoices))
		user_names = {}
		for u in frappe.get_all("User", filters={"name": ["in", users]}, fields=["name", "full_name"]):
			user_names[u.name] = u.full_name

		for inv in invoices:
			inv["type"] = "bundle" if inv.name in bundle_set else "loose"
			inv["time"] = str(inv.posting_time)[:5] if inv.posting_time else ""
			inv["user_name"] = user_names.get(inv.owner, inv.owner)

	return invoices
