import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today, flt


class POFollowUp(Document):
	def validate(self):
		self.validate_purchase_order()
		self.validate_dates()
		self.set_previously_confirmed_qty()

	def validate_purchase_order(self):
		po_docstatus = frappe.db.get_value("Purchase Order", self.purchase_order, "docstatus")
		if po_docstatus != 1:
			frappe.throw(_("Purchase Order {0} must be submitted").format(self.purchase_order))

	def validate_dates(self):
		if self.next_followup_date and self.followup_date:
			if getdate(self.next_followup_date) < getdate(self.followup_date):
				frappe.throw(_("Next Follow Up Date cannot be before Follow Up Date"))

	def set_previously_confirmed_qty(self):
		for row in self.items:
			if not row.po_detail:
				continue

			prev_qty = frappe.db.sql(
				"""
				SELECT COALESCE(SUM(fi.expected_qty), 0)
				FROM `tabPO Follow Up Item` fi
				INNER JOIN `tabPO Follow Up` fu ON fi.parent = fu.name
				WHERE fu.purchase_order = %s
				  AND fi.po_detail = %s
				  AND fu.name != %s
				""",
				(self.purchase_order, row.po_detail, self.name or ""),
			)[0][0]

			row.previously_confirmed_qty = flt(prev_qty)

	def on_save(self):
		self.update_po_summary()

	def on_trash(self):
		self.update_po_summary()

	def update_po_summary(self):
		po_name = self.purchase_order

		latest = frappe.db.sql(
			"""
			SELECT followup_date, overall_status
			FROM `tabPO Follow Up`
			WHERE purchase_order = %s
			ORDER BY followup_date DESC, creation DESC
			LIMIT 1
			""",
			po_name,
			as_dict=True,
		)

		total = frappe.db.count("PO Follow Up", {"purchase_order": po_name})

		next_date = frappe.db.sql(
			"""
			SELECT MIN(next_followup_date) as next_date
			FROM `tabPO Follow Up`
			WHERE purchase_order = %s
			  AND next_followup_date >= %s
			""",
			(po_name, today()),
		)[0][0]

		if latest:
			frappe.db.set_value(
				"Purchase Order",
				po_name,
				{
					"custom_last_followup_date": latest[0].followup_date,
					"custom_last_followup_status": latest[0].overall_status,
					"custom_next_followup_date": next_date,
					"custom_total_followups": total,
				},
				update_modified=False,
			)
		else:
			frappe.db.set_value(
				"Purchase Order",
				po_name,
				{
					"custom_last_followup_date": None,
					"custom_last_followup_status": "",
					"custom_next_followup_date": None,
					"custom_total_followups": 0,
				},
				update_modified=False,
			)
