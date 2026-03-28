import frappe
from frappe import _
from frappe.utils import flt
import json


@frappe.whitelist()
def get_so_items_with_suppliers(sales_order, include_ordered=0):
	"""Get Sales Order items with their default suppliers.

	Args:
		sales_order: Sales Order name
		include_ordered: If 1, include items that already have POs (uses original qty)
	"""
	so = frappe.get_doc("Sales Order", sales_order)
	include_ordered = int(include_ordered)

	if so.docstatus != 1:
		frappe.throw(_("Sales Order must be submitted"))

	items = []
	for d in so.items:
		if include_ordered:
			qty = flt(d.qty)
		else:
			qty = (flt(d.stock_qty) - flt(d.ordered_qty)) / (flt(d.conversion_factor) or 1)

		if qty <= 0:
			continue

		supplier = d.supplier
		if not supplier:
			supplier = _get_item_default_supplier(d.item_code, so.company)

		items.append({
			"so_detail": d.name,
			"item_code": d.item_code,
			"item_name": d.item_name,
			"pending_qty": qty,
			"uom": d.uom,
			"stock_uom": d.stock_uom,
			"conversion_factor": d.conversion_factor,
			"warehouse": d.warehouse,
			"delivery_date": str(d.delivery_date) if d.delivery_date else "",
			"supplier": supplier or "",
		})

	return items


@frappe.whitelist()
def create_po_supplier_wise(sales_order, items):
	"""Create Purchase Orders grouped by supplier from a Sales Order.

	Items without a supplier are grouped under a 'No Supplier' placeholder.
	"""
	if isinstance(items, str):
		items = json.loads(items)

	if not items:
		frappe.throw(_("No items selected"))

	so = frappe.get_doc("Sales Order", sales_order)
	if so.docstatus != 1:
		frappe.throw(_("Sales Order must be submitted"))

	# Group items by supplier
	supplier_groups = {}
	for item in items:
		supplier = item.get("supplier") or ""
		supplier_groups.setdefault(supplier, []).append(item)

	# Handle items without supplier
	no_supplier_name = "No Supplier"
	if "" in supplier_groups:
		_ensure_no_supplier_exists(no_supplier_name)
		supplier_groups[no_supplier_name] = supplier_groups.pop("")

	created_pos = []
	for supplier, group_items in supplier_groups.items():
		po = _create_po_for_supplier(so, supplier, group_items)
		created_pos.append(po.name)

	return created_pos


@frappe.whitelist()
def setup_school_fields():
	"""One-time setup: Create School Name custom fields on SO, PO, SI.

	Call from browser console:
	frappe.call({method: 'trustbit_school_book_seller.api.setup_school_fields', callback: function(r) { console.log(r.message); }})
	"""
	from trustbit_school_book_seller.install import create_school_custom_fields
	create_school_custom_fields()

	# Rename Remark to "Remark & Requisitioner" if it exists with old label
	if frappe.db.exists("Custom Field", {"dt": "Purchase Order", "fieldname": "custom_remark"}):
		cf = frappe.get_doc("Custom Field", {"dt": "Purchase Order", "fieldname": "custom_remark"})
		if cf.label != "Remark & Requisitioner":
			cf.label = "Remark & Requisitioner"
			cf.save(ignore_permissions=True)

	# Upgrade PO custom_school_name from Data to Link if School DocType exists
	if frappe.db.exists("DocType", "School"):
		po_cf = frappe.db.exists("Custom Field", {"dt": "Purchase Order", "fieldname": "custom_school_name"})
		if po_cf:
			cf = frappe.get_doc("Custom Field", po_cf)
			if cf.fieldtype != "Link" or cf.options != "School":
				# Frappe doesn't allow fieldtype change via save, so delete and recreate
				frappe.delete_doc("Custom Field", po_cf, ignore_permissions=True)
				frappe.db.commit()
				new_cf = frappe.get_doc({
					"doctype": "Custom Field",
					"dt": "Purchase Order",
					"fieldname": "custom_school_name",
					"fieldtype": "Link",
					"label": "School Name",
					"options": "School",
					"insert_after": "supplier_name",
				})
				new_cf.insert(ignore_permissions=True)

		# Also upgrade SI custom_school_name from Data to Link
		si_cf = frappe.db.exists("Custom Field", {"dt": "Sales Invoice", "fieldname": "custom_school_name"})
		if si_cf:
			cf = frappe.get_doc("Custom Field", si_cf)
			if cf.fieldtype != "Link" or cf.options != "School":
				frappe.delete_doc("Custom Field", si_cf, ignore_permissions=True)
				frappe.db.commit()
				new_cf = frappe.get_doc({
					"doctype": "Custom Field",
					"dt": "Sales Invoice",
					"fieldname": "custom_school_name",
					"fieldtype": "Link",
					"label": "School Name",
					"options": "School",
					"insert_after": "customer_name",
				})
				new_cf.insert(ignore_permissions=True)

	frappe.db.commit()
	return "Custom fields created/updated successfully"


@frappe.whitelist()
def backfill_item_default_suppliers():
	"""One-time utility: populate Item Default.default_supplier from Item Supplier table.

	For items that have a supplier in supplier_items but no default_supplier
	in item_defaults. Call via: frappe.call({method: 'trustbit_school_book_seller.api.backfill_item_default_suppliers'})
	"""
	# Get all items that have Item Supplier rows
	items_with_suppliers = frappe.db.sql("""
		SELECT DISTINCT si.parent as item_code, si.supplier
		FROM `tabItem Supplier` si
		WHERE si.supplier IS NOT NULL AND si.supplier != ''
		ORDER BY si.parent
	""", as_dict=True)

	# Group by item (take the first supplier for each item)
	item_suppliers = {}
	for row in items_with_suppliers:
		if row.item_code not in item_suppliers:
			item_suppliers[row.item_code] = row.supplier

	updated = 0
	for item_code, supplier in item_suppliers.items():
		# Check if item already has default_supplier in Item Default
		existing = frappe.db.sql("""
			SELECT name, default_supplier, company
			FROM `tabItem Default`
			WHERE parent = %s
		""", item_code, as_dict=True)

		if existing:
			# Update existing Item Default rows that don't have a supplier
			for row in existing:
				if not row.default_supplier:
					frappe.db.set_value("Item Default", row.name, "default_supplier", supplier)
					updated += 1
		else:
			# No Item Default entry exists — create one
			company = frappe.db.get_single_value("Global Defaults", "default_company")
			if company:
				item_doc = frappe.get_doc("Item", item_code)
				item_doc.append("item_defaults", {
					"company": company,
					"default_supplier": supplier,
				})
				item_doc.save(ignore_permissions=True)
				updated += 1

	frappe.db.commit()
	return {"updated": updated, "total_items_checked": len(item_suppliers)}


def _get_item_default_supplier(item_code, company=None):
	"""Get default supplier for an item from Item Default or Item Supplier table."""
	# Check Item Default table (company-specific first)
	if company:
		supplier = frappe.db.get_value(
			"Item Default",
			{"parent": item_code, "company": company},
			"default_supplier"
		)
		if supplier:
			return supplier

	# Check Item Default without company filter
	supplier = frappe.db.get_value(
		"Item Default",
		{"parent": item_code},
		"default_supplier"
	)
	if supplier:
		return supplier

	# Fallback to Item Supplier table (first entry)
	supplier = frappe.db.get_value(
		"Item Supplier",
		{"parent": item_code},
		"supplier"
	)
	return supplier


def _ensure_no_supplier_exists(supplier_name="No Supplier"):
	"""Create the 'No Supplier' placeholder if it doesn't exist."""
	if frappe.db.exists("Supplier", supplier_name):
		return

	supplier_group = (
		frappe.db.get_single_value("Buying Settings", "supplier_group")
		or "All Supplier Groups"
	)

	doc = frappe.get_doc({
		"doctype": "Supplier",
		"supplier_name": supplier_name,
		"supplier_group": supplier_group,
	})
	doc.insert(ignore_permissions=True)
	frappe.db.commit()


def _create_po_for_supplier(so, supplier, items):
	"""Create a single Purchase Order for a supplier from Sales Order items."""
	po = frappe.new_doc("Purchase Order")
	po.supplier = supplier
	po.company = so.company
	po.schedule_date = so.delivery_date

	# Copy school name from Sales Order
	if so.get("custom_school_name"):
		po.custom_school_name = so.custom_school_name
	if so.get("custom_remark"):
		po.custom_remark = so.custom_remark

	# Set supplier defaults
	supplier_defaults = frappe.db.get_value(
		"Supplier", supplier,
		["default_currency", "default_price_list", "payment_terms"],
		as_dict=True
	) or {}

	if supplier_defaults.get("default_currency"):
		po.currency = supplier_defaults["default_currency"]
	if supplier_defaults.get("default_price_list"):
		po.buying_price_list = supplier_defaults["default_price_list"]
	if supplier_defaults.get("payment_terms"):
		po.payment_terms_template = supplier_defaults["payment_terms"]

	for item in items:
		so_detail = item.get("so_detail")
		pending_qty = flt(item.get("pending_qty"))
		if pending_qty <= 0:
			continue

		po_item = {
			"item_code": item["item_code"],
			"item_name": item["item_name"],
			"qty": pending_qty,
			"uom": item.get("uom"),
			"stock_uom": item.get("stock_uom") or item.get("uom"),
			"conversion_factor": flt(item.get("conversion_factor")) or 1,
			"warehouse": item.get("warehouse"),
			"schedule_date": item.get("delivery_date") or str(so.delivery_date),
			"sales_order": so.name,
			"sales_order_item": so_detail,
		}
		po.append("items", po_item)

	if not po.items:
		frappe.throw(_("No pending items for supplier {0}").format(supplier))

	po.run_method("set_missing_values")

	# Batch-fetch rates from Item Price in one query
	if po.buying_price_list and po.items:
		item_codes = [row.item_code for row in po.items]
		prices = frappe.get_all(
			"Item Price",
			filters={"item_code": ["in", item_codes], "price_list": po.buying_price_list},
			fields=["item_code", "price_list_rate"],
		)
		rate_map = {}
		for p in prices:
			if p.item_code not in rate_map:
				rate_map[p.item_code] = flt(p.price_list_rate)

		for row in po.items:
			rate = rate_map.get(row.item_code)
			if rate:
				row.price_list_rate = rate
				row.rate = rate

	po.run_method("calculate_taxes_and_totals")
	po.flags.ignore_permissions = True
	po.insert()
	frappe.db.commit()

	return po


def copy_school_name_to_invoice(doc, method):
	"""Copy School Name from linked Sales Order to Sales Invoice.

	Called via doc_events hook on Sales Invoice before_save.
	"""
	if doc.get("custom_school_name"):
		return  # Already set, don't overwrite

	for item in doc.items:
		if item.sales_order:
			school_name = frappe.db.get_value(
				"Sales Order", item.sales_order, "custom_school_name"
			)
			if school_name:
				doc.custom_school_name = school_name
				break


def on_sales_invoice_save(doc, method):
	"""Publish realtime event for multi-print on Sales Invoice save (draft).

	Only triggers if Multi Print Setting trigger_on is 'Draft (Save)' or 'Both (Save + Submit)'.
	Skips submitted docs (docstatus=1) to avoid double-print when trigger_on is 'Both'.
	"""
	if doc.docstatus == 1:
		return  # Submitted docs are handled by on_submit hook

	if not frappe.db.exists("DocType", "Multi Print Setting"):
		return

	trigger_on = frappe.db.get_single_value("Multi Print Setting", "trigger_on") or "Submitted Only"
	if trigger_on not in ("Draft (Save)", "Both (Save + Submit)"):
		return

	frappe.publish_realtime(
		"multi_print_invoice",
		{"docname": doc.name},
		user=frappe.session.user,
		after_commit=True,
	)


def on_sales_invoice_submit(doc, method):
	"""Publish realtime event for multi-print on Sales Invoice submit.

	Only triggers if Multi Print Setting trigger_on is 'Submitted Only' or 'Both (Save + Submit)'.
	Works from any submission source: standard form, POS Awesome, API, background jobs.
	"""
	if not frappe.db.exists("DocType", "Multi Print Setting"):
		return

	trigger_on = frappe.db.get_single_value("Multi Print Setting", "trigger_on") or "Submitted Only"
	if trigger_on not in ("Submitted Only", "Both (Save + Submit)"):
		return

	frappe.publish_realtime(
		"multi_print_invoice",
		{"docname": doc.name},
		user=frappe.session.user,
		after_commit=True,
	)


@frappe.whitelist()
def get_multi_print_settings():
	"""Get print config for current user.

	Priority: User Print Config (per-user) > Multi Print Setting (global default).
	Global settings (enabled, show_token, token_digits, trigger_on) always come from Multi Print Setting.
	Print formats/printers come from user config if it exists, otherwise global default
	(only if use_default_fallback is enabled).
	"""
	if not frappe.db.exists("DocType", "Multi Print Setting"):
		return {"enabled": 0, "print_formats": []}

	settings = frappe.get_single("Multi Print Setting")
	result = {
		"enabled": settings.enabled,
		"show_token": settings.show_token,
		"token_digits": settings.token_digits or 3,
		"trigger_on": settings.get("trigger_on") or "Submitted Only",
		"source": "global",
		"print_formats": [],
	}

	# Check for user-specific config first
	user = frappe.session.user
	user_config_name = frappe.db.exists("User Print Config", user)

	if user_config_name:
		user_config = frappe.get_doc("User Print Config", user_config_name)
		if user_config.print_formats:
			result["source"] = "user"
			result["print_formats"] = [
				{
					"print_format": row.print_format,
					"printer_name": row.printer_name,
					"copies": row.copies or 1,
					"enabled": row.enabled,
				}
				for row in user_config.print_formats
			]
			return result

	# Fallback to global default (only if use_default_fallback is enabled)
	use_fallback = settings.get("use_default_fallback")
	if use_fallback is None:
		use_fallback = 1  # default to enabled for backwards compatibility

	if not use_fallback:
		# No user config and fallback disabled — return empty
		return result

	result["print_formats"] = [
		{
			"print_format": row.print_format,
			"printer_name": row.printer_name,
			"copies": row.copies or 1,
			"enabled": row.enabled,
		}
		for row in (settings.print_formats or [])
	]
	return result


@frappe.whitelist()
def search_items(search_text="", limit=50):
	"""Fuzzy search Items by code, name, group, description, barcode.

	Splits search_text into words and matches ALL words (AND logic).
	Returns: item_code, item_name, item_group, stock_uom, barcode
	"""
	search_text = (search_text or "").strip()
	limit = min(int(limit), 100)

	if len(search_text) < 2:
		return []

	words = search_text.split()
	conditions = []
	values = []

	for word in words:
		like_val = "%{}%".format(word)
		conditions.append("""(
			i.name LIKE %s
			OR i.item_name LIKE %s
			OR i.item_group LIKE %s
			OR i.description LIKE %s
			OR ib.barcode LIKE %s
		)""")
		values.extend([like_val, like_val, like_val, like_val, like_val])

	where_clause = " AND ".join(conditions)

	items = frappe.db.sql("""
		SELECT DISTINCT i.name as item_code, i.item_name, i.item_group,
			i.stock_uom, i.image,
			(SELECT ib2.barcode FROM `tabItem Barcode` ib2
			 WHERE ib2.parent = i.name LIMIT 1) as barcode
		FROM `tabItem` i
		LEFT JOIN `tabItem Barcode` ib ON ib.parent = i.name
		WHERE i.disabled = 0 AND i.has_variants = 0
			AND {where_clause}
		ORDER BY
			CASE WHEN i.name LIKE %s THEN 0 ELSE 1 END,
			i.name
		LIMIT %s
	""".format(where_clause=where_clause),
		values + ["%{}%".format(words[0]), limit],
		as_dict=True,
	)

	return items


@frappe.whitelist()
def search_product_bundles(search_text="", limit=20):
	"""Fuzzy search Product Bundles by name, parent item name, description, item group.

	Splits search_text into words and matches ALL words (AND logic) against:
	- Product Bundle name (= parent item code)
	- Parent item's item_name
	- Parent item's description
	- Parent item's item_group

	Returns list of dicts with: name, item_name, description, item_group, items_count
	"""
	search_text = (search_text or "").strip()
	limit = min(int(limit), 50)

	if not search_text:
		# Return all bundles (up to limit) when no search text
		bundles = frappe.db.sql("""
			SELECT pb.name, i.item_name, i.description, i.item_group,
				(SELECT COUNT(*) FROM `tabProduct Bundle Item` pbi WHERE pbi.parent = pb.name) as items_count
			FROM `tabProduct Bundle` pb
			LEFT JOIN `tabItem` i ON i.name = pb.new_item_code
			ORDER BY pb.name
			LIMIT %s
		""", (limit,), as_dict=True)
		return bundles

	words = search_text.split()
	conditions = []
	values = []

	for word in words:
		like_val = "%{}%".format(word)
		conditions.append("""(
			pb.name LIKE %s
			OR i.item_name LIKE %s
			OR i.description LIKE %s
			OR i.item_group LIKE %s
		)""")
		values.extend([like_val, like_val, like_val, like_val])

	where_clause = " AND ".join(conditions)

	bundles = frappe.db.sql("""
		SELECT pb.name, i.item_name, i.description, i.item_group,
			(SELECT COUNT(*) FROM `tabProduct Bundle Item` pbi WHERE pbi.parent = pb.name) as items_count
		FROM `tabProduct Bundle` pb
		LEFT JOIN `tabItem` i ON i.name = pb.new_item_code
		WHERE {where_clause}
		ORDER BY pb.name
		LIMIT %s
	""".format(where_clause=where_clause), values + [limit], as_dict=True)

	return bundles


@frappe.whitelist()
def validate_privilege_card(card_name):
	"""Validate a privilege card and return its details.

	Checks: exists, status is Active, not expired.
	Returns: card_type, discount_percent, holder_name, school, status.
	"""
	from frappe.utils import getdate, today

	if not frappe.db.exists("Privilege Card", card_name):
		frappe.throw(_("Privilege Card {0} not found").format(card_name))

	card = frappe.get_doc("Privilege Card", card_name)

	if card.status != "Active":
		frappe.throw(_("Privilege Card {0} is {1}").format(card_name, card.status))

	if card.expiry_date and getdate(card.expiry_date) < getdate(today()):
		card.db_set("status", "Expired")
		frappe.throw(_("Privilege Card {0} has expired on {1}").format(
			card_name, card.expiry_date))

	return {
		"card_name": card.name,
		"card_type": card.card_type,
		"discount_percent": card.discount_percent,
		"holder_name": card.holder_name,
		"school": card.school,
		"status": card.status,
	}


@frappe.whitelist()
def get_product_bundle_items(product_bundle, qty_sets=1, price_list=""):
	"""Get component items from a Product Bundle, multiplied by number of sets.

	Skips items marked as "Not Available" in custom_product_bundle_stock.
	If price_list is provided, fetches rates in a single batch query.

	Args:
		product_bundle: Name of the Product Bundle document
		qty_sets: Number of sets (multiplier for component qty)
		price_list: Optional price list name to fetch rates

	Returns:
		List of dicts with item_code, item_name, description, qty, uom,
		stock_uom, conversion_factor. If price_list given, also includes
		price_list_rate and rate.
	"""
	qty_sets = flt(qty_sets)
	if qty_sets <= 0:
		frappe.throw(_("Number of Sets must be greater than zero"))

	if not frappe.db.exists("Product Bundle", product_bundle):
		frappe.throw(_("Product Bundle {0} not found").format(product_bundle))

	bundle = frappe.get_doc("Product Bundle", product_bundle)

	if not bundle.items:
		frappe.throw(_("Product Bundle {0} has no items").format(product_bundle))

	items = []
	skipped = []
	for row in bundle.items:
		stock_status = getattr(row, "custom_product_bundle_stock", "") or "Available"

		if stock_status == "Not Available":
			skipped.append(row.item_code)
			continue

		item_details = frappe.db.get_value(
			"Item",
			row.item_code,
			["item_name", "description", "stock_uom"],
			as_dict=True,
		)

		if not item_details:
			frappe.throw(
				_("Item {0} in Product Bundle does not exist").format(row.item_code)
			)

		items.append(
			{
				"item_code": row.item_code,
				"item_name": item_details.item_name or row.item_code,
				"description": item_details.description or "",
				"qty": flt(row.qty) * qty_sets,
				"uom": row.uom or item_details.stock_uom,
				"stock_uom": item_details.stock_uom,
				"conversion_factor": 1,
			}
		)

	if skipped:
		frappe.msgprint(
			_("Skipped {0} item(s) marked as Not Available: {1}").format(
				len(skipped), ", ".join(skipped)
			),
			alert=True,
			indicator="orange",
		)

	# Batch-fetch rates from Item Price in one query (no N+1 calls)
	if price_list and items:
		item_codes = [d["item_code"] for d in items]
		prices = frappe.get_all(
			"Item Price",
			filters={"item_code": ["in", item_codes], "price_list": price_list},
			fields=["item_code", "price_list_rate"],
		)
		rate_map = {}
		for p in prices:
			if p.item_code not in rate_map:
				rate_map[p.item_code] = flt(p.price_list_rate)

		for item in items:
			rate = rate_map.get(item["item_code"], 0)
			item["price_list_rate"] = rate
			item["rate"] = rate

	return items
