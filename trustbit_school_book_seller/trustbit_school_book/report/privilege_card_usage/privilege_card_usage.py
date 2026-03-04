import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    chart = get_chart(data)
    summary = get_summary(data)
    return columns, data, None, chart, summary


def get_columns():
    return [
        {
            "label": _("Card Number"),
            "fieldname": "card_name",
            "fieldtype": "Link",
            "options": "Privilege Card",
            "width": 120,
        },
        {
            "label": _("Card Type"),
            "fieldname": "card_type",
            "fieldtype": "Link",
            "options": "Privilege Card Type",
            "width": 100,
        },
        {
            "label": _("Holder Name"),
            "fieldname": "holder_name",
            "fieldtype": "Data",
            "width": 150,
        },
        {
            "label": _("School"),
            "fieldname": "school",
            "fieldtype": "Link",
            "options": "School",
            "width": 150,
        },
        {
            "label": _("Discount %"),
            "fieldname": "discount_percent",
            "fieldtype": "Percent",
            "width": 90,
        },
        {
            "label": _("Document Type"),
            "fieldname": "document_type",
            "fieldtype": "Data",
            "width": 110,
        },
        {
            "label": _("Document"),
            "fieldname": "document_name",
            "fieldtype": "Dynamic Link",
            "options": "document_type",
            "width": 150,
        },
        {
            "label": _("Date"),
            "fieldname": "posting_date",
            "fieldtype": "Date",
            "width": 100,
        },
        {
            "label": _("Discount Amount"),
            "fieldname": "total_discount_amount",
            "fieldtype": "Currency",
            "width": 130,
        },
        {
            "label": _("Status"),
            "fieldname": "status",
            "fieldtype": "Data",
            "width": 80,
        },
    ]


def get_data(filters):
    conditions = []
    values = {}

    if filters.get("from_date"):
        conditions.append("ul.posting_date >= %(from_date)s")
        values["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        conditions.append("ul.posting_date <= %(to_date)s")
        values["to_date"] = filters["to_date"]

    if filters.get("card_type"):
        conditions.append("pc.card_type = %(card_type)s")
        values["card_type"] = filters["card_type"]

    if filters.get("school"):
        conditions.append("pc.school = %(school)s")
        values["school"] = filters["school"]

    if filters.get("status"):
        conditions.append("pc.status = %(status)s")
        values["status"] = filters["status"]

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    data = frappe.db.sql(
        """
        SELECT
            pc.name as card_name,
            pc.card_type,
            pc.holder_name,
            pc.school,
            pc.discount_percent,
            ul.document_type,
            ul.document_name,
            ul.posting_date,
            ul.total_discount_amount,
            pc.status
        FROM `tabPrivilege Card Usage Log` ul
        JOIN `tabPrivilege Card` pc ON pc.name = ul.parent
        WHERE {where_clause}
        ORDER BY ul.posting_date DESC, pc.name
    """.format(
            where_clause=where_clause
        ),
        values,
        as_dict=True,
    )

    return data


def get_chart(data):
    if not data:
        return None

    # Group discount amounts by card type
    type_totals = {}
    for row in data:
        ct = row.get("card_type") or "Unknown"
        type_totals[ct] = flt(type_totals.get(ct, 0)) + flt(row.get("total_discount_amount"))

    return {
        "data": {
            "labels": list(type_totals.keys()),
            "datasets": [
                {
                    "name": _("Total Discount"),
                    "values": list(type_totals.values()),
                }
            ],
        },
        "type": "bar",
        "colors": ["#1a237e"],
    }


def get_summary(data):
    if not data:
        return []

    unique_cards = len(set(row["card_name"] for row in data))
    total_discount = sum(flt(row.get("total_discount_amount")) for row in data)
    total_transactions = len(data)

    return [
        {
            "value": unique_cards,
            "indicator": "Blue",
            "label": _("Cards Used"),
            "datatype": "Int",
        },
        {
            "value": total_transactions,
            "indicator": "Green",
            "label": _("Transactions"),
            "datatype": "Int",
        },
        {
            "value": total_discount,
            "indicator": "Orange",
            "label": _("Total Discount Given"),
            "datatype": "Currency",
        },
    ]
