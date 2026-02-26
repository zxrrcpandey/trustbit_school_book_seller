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
	frappe.db.commit()
	return "School Name custom fields created successfully"


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
