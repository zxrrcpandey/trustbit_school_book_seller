import frappe
from frappe import _

ALLOWED_DOCTYPES = ("Sales Invoice", "Purchase Invoice")
CHILD_DOCTYPE_MAP = {
	"Sales Invoice": "Sales Invoice Item",
	"Purchase Invoice": "Purchase Invoice Item",
}


def _validate_doctype(doctype):
	"""Validate doctype is one of the allowed invoice types."""
	if doctype not in ALLOWED_DOCTYPES:
		frappe.throw(_("Invalid doctype: {0}").format(doctype))


def _get_child_doctype(doctype):
	"""Get the child table doctype for the given invoice doctype."""
	return CHILD_DOCTYPE_MAP[doctype]


def _is_selling(doctype):
	"""Return True if Sales Invoice, False if Purchase Invoice."""
	return doctype == "Sales Invoice"


def _get_already_returned_qty(doctype, return_against, item_code=None):
	"""Calculate already-returned quantities from submitted return invoices.

	Returns dict: {item_code: returned_qty} or single float if item_code given.
	"""
	child_doctype = _get_child_doctype(doctype)

	existing_returns = frappe.get_all(
		doctype,
		filters={
			"return_against": return_against,
			"is_return": 1,
			"docstatus": 1,
		},
		pluck="name",
	)

	if not existing_returns:
		return 0 if item_code else {}

	returned_qty = {}
	for ret_name in existing_returns:
		filters = {"parent": ret_name}
		if item_code:
			filters["item_code"] = item_code

		ret_items = frappe.get_all(
			child_doctype,
			filters=filters,
			fields=["item_code", "qty"],
		)
		for ri in ret_items:
			# Return qty is negative in ERPNext
			returned = abs(ri.qty)
			returned_qty[ri.item_code] = returned_qty.get(ri.item_code, 0) + returned

	if item_code:
		return returned_qty.get(item_code, 0)

	return returned_qty


@frappe.whitelist()
def get_return_scanner_settings():
	"""Return the Return Scanner Settings (Single DocType)."""
	try:
		settings = frappe.get_single("Return Scanner Settings")
		return {
			"return_mode": settings.return_mode or "Hybrid",
			"auto_focus_barcode": settings.auto_focus_barcode,
			"play_sound_on_scan": settings.play_sound_on_scan,
			"allow_exceed_original_qty": settings.allow_exceed_original_qty,
			"max_return_without_approval": settings.max_return_without_approval or 0,
		}
	except Exception:
		return {
			"return_mode": "Hybrid",
			"auto_focus_barcode": 1,
			"play_sound_on_scan": 1,
			"allow_exceed_original_qty": 0,
			"max_return_without_approval": 0,
		}


@frappe.whitelist()
def get_original_invoice_items(return_against, doctype):
	"""Get items from the original invoice with already-returned quantities calculated."""
	if not return_against or not doctype:
		return []

	_validate_doctype(doctype)

	original = frappe.get_doc(doctype, return_against)

	# Build dict of original items: item_code -> {qty, rate, ...}
	original_items = {}
	for item in original.items:
		key = item.item_code
		if key in original_items:
			original_items[key]["qty"] += item.qty
		else:
			original_items[key] = {
				"item_code": item.item_code,
				"item_name": item.item_name,
				"brand": item.brand or "",
				"qty": item.qty,
				"rate": item.rate,
				"price_list_rate": item.price_list_rate or item.rate,
				"uom": item.uom,
				"discount_percentage": item.discount_percentage or 0,
				"warehouse": item.warehouse or "",
			}

	# Calculate already-returned quantities
	returned_qty = _get_already_returned_qty(doctype, return_against)

	# Build result
	result = []
	for item_code, data in original_items.items():
		already_returned = returned_qty.get(item_code, 0)
		returnable = max(0, data["qty"] - already_returned)
		result.append({
			"item_code": item_code,
			"item_name": data["item_name"],
			"brand": data["brand"],
			"original_qty": data["qty"],
			"rate": data["rate"],
			"price_list_rate": data["price_list_rate"],
			"uom": data["uom"],
			"discount_percentage": data["discount_percentage"],
			"warehouse": data["warehouse"],
			"already_returned_qty": already_returned,
			"returnable_qty": returnable,
		})

	return result


@frappe.whitelist()
def scan_return_barcode(barcode, return_against=None, doctype=None):
	"""Scan a barcode and return item details.

	In strict mode (return_against provided), also returns available qty from original invoice.
	In free mode, returns item details with no qty limit.
	"""
	if not barcode:
		return {"success": False, "message": _("No barcode provided")}

	if doctype:
		_validate_doctype(doctype)

	# Try ERPNext's barcode scanner first (searches Item Barcode, Serial No, Batch)
	from erpnext.stock.utils import scan_barcode as erp_scan_barcode

	scan_result = erp_scan_barcode(barcode)
	item_code = scan_result.get("item_code") if scan_result else None

	# If barcode scan didn't find it, try matching by item_code directly
	if not item_code:
		if frappe.db.exists("Item", barcode):
			item_code = barcode

	# If still not found, try matching by item_name (partial match, take first)
	if not item_code:
		item_code = frappe.db.get_value("Item", {"item_name": barcode, "disabled": 0}, "name")

	# If still not found, try fuzzy search by item_name LIKE
	if not item_code:
		match = frappe.db.get_value(
			"Item",
			{"item_name": ("like", f"%{barcode}%"), "disabled": 0},
			"name",
		)
		if match:
			item_code = match

	if not item_code:
		return {"success": False, "message": _("Item not found for: {0}").format(barcode)}

	item = frappe.get_doc("Item", item_code)

	result = {
		"success": True,
		"item_code": item_code,
		"item_name": item.item_name,
		"brand": item.brand or "",
		"uom": item.stock_uom or "Nos",
		"barcode": barcode,
	}

	# If strict mode — get rate and qty from original invoice
	if return_against and doctype:
		child_doctype = _get_child_doctype(doctype)

		# Find item in original invoice
		orig_items = frappe.get_all(
			child_doctype,
			filters={"parent": return_against, "item_code": item_code},
			fields=["qty", "rate", "price_list_rate", "uom", "discount_percentage", "warehouse"],
		)

		if not orig_items:
			return {
				"success": False,
				"message": _("Item {0} not found in original invoice {1}").format(item_code, return_against),
			}

		# Sum qty across rows (same item may appear multiple times)
		total_orig_qty = sum(i.qty for i in orig_items)
		rate = orig_items[0].rate
		price_list_rate = orig_items[0].price_list_rate or rate
		uom = orig_items[0].uom
		discount_percentage = orig_items[0].discount_percentage or 0
		warehouse = orig_items[0].warehouse or ""

		# Calculate already returned
		already_returned = _get_already_returned_qty(doctype, return_against, item_code)
		returnable_qty = max(0, total_orig_qty - already_returned)

		result.update({
			"original_qty": total_orig_qty,
			"rate": rate,
			"price_list_rate": price_list_rate,
			"uom": uom,
			"discount_percentage": discount_percentage,
			"warehouse": warehouse,
			"already_returned_qty": already_returned,
			"returnable_qty": returnable_qty,
		})
	else:
		# Free mode — get selling or buying price based on doctype
		selling = 1
		if doctype == "Purchase Invoice":
			selling = 0

		price = frappe.db.get_value(
			"Item Price",
			{"item_code": item_code, "selling": selling},
			"price_list_rate",
		) or 0
		result.update({
			"rate": price,
			"price_list_rate": price,
			"original_qty": 0,
			"returnable_qty": 9999,
			"already_returned_qty": 0,
			"uom": item.stock_uom or "Nos",
			"discount_percentage": 0,
			"warehouse": "",
		})

	return result


@frappe.whitelist()
def search_return_items(query, return_against=None, doctype=None):
	"""Search items by name/code for the return scanner dropdown.

	In strict mode, only searches items present in the original invoice.
	In free mode, searches all items.
	"""
	if not query or len(query) < 2:
		return []

	if doctype:
		_validate_doctype(doctype)

	query_str = f"%{query}%"

	if return_against and doctype:
		child_doctype = _get_child_doctype(doctype)

		items = frappe.db.sql(
			"""
			SELECT DISTINCT ci.item_code, ci.item_name, i.brand, ci.uom, ci.rate,
				ci.price_list_rate, ci.discount_percentage, ci.warehouse
			FROM `tab{child}` ci
			JOIN `tabItem` i ON i.name = ci.item_code
			WHERE ci.parent = %(invoice)s
				AND (ci.item_code LIKE %(q)s OR ci.item_name LIKE %(q)s OR i.brand LIKE %(q)s)
			LIMIT 10
			""".format(child=child_doctype),
			{"invoice": return_against, "q": query_str},
			as_dict=True,
		)

		# Get returned qty map once (not per item)
		returned_qty = _get_already_returned_qty(doctype, return_against)

		# Add returnable qty info
		for item in items:
			# Get total orig qty
			total_orig = frappe.db.sql(
				"""SELECT SUM(qty) as total FROM `tab{child}`
				WHERE parent=%(inv)s AND item_code=%(ic)s""".format(child=child_doctype),
				{"inv": return_against, "ic": item.item_code},
			)
			item["original_qty"] = total_orig[0][0] if total_orig and total_orig[0][0] else 0
			item["already_returned_qty"] = returned_qty.get(item.item_code, 0)
			item["returnable_qty"] = max(0, item["original_qty"] - item["already_returned_qty"])

		return items
	else:
		# Free: search all items
		items = frappe.db.sql(
			"""
			SELECT i.name as item_code, i.item_name, i.brand, i.stock_uom as uom
			FROM `tabItem` i
			WHERE i.disabled = 0
				AND (i.name LIKE %(q)s OR i.item_name LIKE %(q)s OR i.brand LIKE %(q)s)
			LIMIT 10
			""",
			{"q": query_str},
			as_dict=True,
		)

		selling = 1
		if doctype == "Purchase Invoice":
			selling = 0

		for item in items:
			price = frappe.db.get_value(
				"Item Price", {"item_code": item.item_code, "selling": selling}, "price_list_rate"
			) or 0
			item["rate"] = price
			item["price_list_rate"] = price
			item["original_qty"] = 0
			item["returnable_qty"] = 9999
			item["already_returned_qty"] = 0
			item["discount_percentage"] = 0
			item["warehouse"] = ""

		return items
