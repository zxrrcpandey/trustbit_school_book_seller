import frappe
from frappe import _
from frappe.utils import flt, today, add_days


@frappe.whitelist()
def get_po_items(purchase_order):
	"""Fetch PO items with ordered qty and received qty for populating
	the PO Follow Up Item child table."""
	po = frappe.get_doc("Purchase Order", purchase_order)
	if po.docstatus != 1:
		frappe.throw(_("Purchase Order must be submitted"))

	items = []
	for d in po.items:
		items.append(
			{
				"po_detail": d.name,
				"item_code": d.item_code,
				"item_name": d.item_name,
				"ordered_qty": flt(d.qty),
				"received_qty": flt(d.received_qty),
				"pending_qty": flt(d.qty) - flt(d.received_qty),
			}
		)
	return items


@frappe.whitelist()
def get_followup_summary(purchase_order):
	"""Return follow-up stats for a Purchase Order."""
	followups = frappe.get_all(
		"PO Follow Up",
		filters={"purchase_order": purchase_order},
		fields=[
			"name",
			"followup_date",
			"next_followup_date",
			"overall_status",
			"contacted_person",
			"remarks",
		],
		order_by="followup_date desc",
	)
	return {
		"total": len(followups),
		"followups": followups,
	}


@frappe.whitelist()
def create_followup_from_po(purchase_order):
	"""Create a new PO Follow Up pre-filled with PO items.
	Returns the name of the created document for routing."""
	po = frappe.get_doc("Purchase Order", purchase_order)
	if po.docstatus != 1:
		frappe.throw(_("Purchase Order must be submitted"))

	fu = frappe.new_doc("PO Follow Up")
	fu.purchase_order = purchase_order
	fu.supplier = po.supplier
	fu.supplier_name = po.supplier_name

	for d in po.items:
		fu.append(
			"items",
			{
				"po_detail": d.name,
				"item_code": d.item_code,
				"item_name": d.item_name,
				"ordered_qty": flt(d.qty),
				"expected_qty": flt(d.qty) - flt(d.received_qty),
				"status": "Pending",
			},
		)

	fu.insert(ignore_permissions=True)
	return fu.name


def send_followup_reminders():
	"""Daily scheduler: Send notifications for upcoming/overdue follow-ups.

	Finds PO Follow Up records where next_followup_date <= today
	and sends system notifications to Purchase Manager/User roles.
	"""
	overdue = frappe.get_all(
		"PO Follow Up",
		filters={
			"next_followup_date": ["<=", today()],
			"overall_status": ["not in", ["Delivered"]],
		},
		fields=[
			"name",
			"purchase_order",
			"supplier",
			"supplier_name",
			"next_followup_date",
			"overall_status",
		],
	)

	if not overdue:
		return

	recipients = _get_purchase_role_users()

	for fu in overdue:
		for user in recipients:
			frappe.get_doc(
				{
					"doctype": "Notification Log",
					"for_user": user,
					"type": "Alert",
					"document_type": "PO Follow Up",
					"document_name": fu.name,
					"subject": _("Follow Up Due: {0} - {1}").format(
						fu.purchase_order, fu.supplier_name or fu.supplier
					),
					"email_content": _(
						"Follow up on PO {0} (Supplier: {1}) was due on {2}. Current status: {3}"
					).format(
						fu.purchase_order,
						fu.supplier_name or fu.supplier,
						fu.next_followup_date,
						fu.overall_status,
					),
				}
			).insert(ignore_permissions=True)

	frappe.db.commit()


def check_pos_without_followups():
	"""Daily scheduler: Flag submitted POs older than 3 days with no follow-ups."""
	threshold_date = add_days(today(), -3)

	pos = frappe.db.sql(
		"""
		SELECT po.name, po.supplier, po.supplier_name
		FROM `tabPurchase Order` po
		WHERE po.docstatus = 1
		  AND po.status NOT IN ('Completed', 'Cancelled', 'Closed')
		  AND po.transaction_date <= %s
		  AND po.custom_total_followups = 0
		""",
		threshold_date,
		as_dict=True,
	)

	if not pos:
		return

	recipients = _get_purchase_role_users()

	for po in pos:
		for user in recipients:
			frappe.get_doc(
				{
					"doctype": "Notification Log",
					"for_user": user,
					"type": "Alert",
					"document_type": "Purchase Order",
					"document_name": po.name,
					"subject": _("No Follow Up: PO {0} - {1}").format(
						po.name, po.supplier_name or po.supplier
					),
					"email_content": _(
						"Purchase Order {0} (Supplier: {1}) has no follow-ups recorded yet."
					).format(po.name, po.supplier_name or po.supplier),
				}
			).insert(ignore_permissions=True)

	frappe.db.commit()


def _get_purchase_role_users():
	"""Get unique users with Purchase Manager or Purchase User role."""
	recipients = frappe.get_all(
		"Has Role",
		filters={
			"role": ["in", ["Purchase Manager", "Purchase User"]],
			"parenttype": "User",
		},
		pluck="parent",
	)
	return list(set(recipients))
