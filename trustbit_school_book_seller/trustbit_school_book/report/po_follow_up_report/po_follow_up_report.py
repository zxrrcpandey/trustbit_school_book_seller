import frappe
from frappe import _


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	chart = get_chart(data)
	summary = get_summary(data)
	return columns, data, None, chart, summary


def get_columns():
	return [
		{
			"label": _("Follow Up"),
			"fieldname": "name",
			"fieldtype": "Link",
			"options": "PO Follow Up",
			"width": 140,
		},
		{
			"label": _("Purchase Order"),
			"fieldname": "purchase_order",
			"fieldtype": "Link",
			"options": "Purchase Order",
			"width": 150,
		},
		{
			"label": _("Supplier"),
			"fieldname": "supplier_name",
			"fieldtype": "Data",
			"width": 150,
		},
		{
			"label": _("Follow Up Date"),
			"fieldname": "followup_date",
			"fieldtype": "Date",
			"width": 110,
		},
		{
			"label": _("Next Follow Up"),
			"fieldname": "next_followup_date",
			"fieldtype": "Date",
			"width": 110,
		},
		{
			"label": _("Status"),
			"fieldname": "overall_status",
			"fieldtype": "Data",
			"width": 120,
		},
		{
			"label": _("Contacted Person"),
			"fieldname": "contacted_person",
			"fieldtype": "Data",
			"width": 130,
		},
		{
			"label": _("Transport"),
			"fieldname": "transport_name",
			"fieldtype": "Data",
			"width": 120,
		},
		{
			"label": _("Items Count"),
			"fieldname": "items_count",
			"fieldtype": "Int",
			"width": 80,
		},
		{
			"label": _("Remarks"),
			"fieldname": "remarks",
			"fieldtype": "Data",
			"width": 200,
		},
	]


def get_data(filters):
	if not filters:
		filters = {}

	conditions = ["1=1"]
	values = {}

	if filters.get("supplier"):
		conditions.append("fu.supplier = %(supplier)s")
		values["supplier"] = filters["supplier"]

	if filters.get("status"):
		conditions.append("fu.overall_status = %(status)s")
		values["status"] = filters["status"]

	if filters.get("from_date"):
		conditions.append("fu.followup_date >= %(from_date)s")
		values["from_date"] = filters["from_date"]

	if filters.get("to_date"):
		conditions.append("fu.followup_date <= %(to_date)s")
		values["to_date"] = filters["to_date"]

	where_clause = " AND ".join(conditions)

	return frappe.db.sql(
		"""
		SELECT
			fu.name,
			fu.purchase_order,
			fu.supplier_name,
			fu.followup_date,
			fu.next_followup_date,
			fu.overall_status,
			fu.contacted_person,
			fu.transport_name,
			fu.remarks,
			(SELECT COUNT(*) FROM `tabPO Follow Up Item` fi
			 WHERE fi.parent = fu.name) as items_count
		FROM `tabPO Follow Up` fu
		WHERE {where_clause}
		ORDER BY fu.followup_date DESC
		""".format(where_clause=where_clause),
		values,
		as_dict=True,
	)


def get_chart(data):
	status_counts = {}
	for row in data:
		s = row.get("overall_status") or "Unknown"
		status_counts[s] = status_counts.get(s, 0) + 1

	if not status_counts:
		return None

	return {
		"data": {
			"labels": list(status_counts.keys()),
			"datasets": [{"values": list(status_counts.values())}],
		},
		"type": "bar",
		"colors": ["#5e64ff"],
	}


def get_summary(data):
	total = len(data)
	overdue = sum(
		1 for r in data if r.get("overall_status") in ("Pending", "Delayed")
	)
	delivered = sum(1 for r in data if r.get("overall_status") == "Delivered")

	return [
		{"label": _("Total Follow Ups"), "value": total, "indicator": "blue"},
		{"label": _("Pending/Delayed"), "value": overdue, "indicator": "red"},
		{"label": _("Delivered"), "value": delivered, "indicator": "green"},
	]
