# Copyright (c) 2024, Trustbit and contributors
# For license information, please see license.txt

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
        {"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 150},
        {"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 200},
        {"label": _("Publication"), "fieldname": "publication", "fieldtype": "Link", "options": "Publication", "width": 120},
        {"label": _("Subject"), "fieldname": "subject", "fieldtype": "Link", "options": "Subject", "width": 120},
        {"label": _("Class"), "fieldname": "class", "fieldtype": "Link", "options": "Class Master", "width": 100},
        {"label": _("Author"), "fieldname": "author", "fieldtype": "Data", "width": 120},
        {"label": _("ISBN/Barcode"), "fieldname": "isbn_barcode", "fieldtype": "Data", "width": 130},
        {"label": _("Selling Rate"), "fieldname": "selling_rate", "fieldtype": "Currency", "width": 110},
        {"label": _("Valuation Rate"), "fieldname": "valuation_rate", "fieldtype": "Currency", "width": 110},
        {"label": _("Current Stock"), "fieldname": "actual_qty", "fieldtype": "Float", "width": 100},
        {"label": _("Stock Value"), "fieldname": "stock_value", "fieldtype": "Currency", "width": 120},
        {"label": _("Created On"), "fieldname": "creation", "fieldtype": "Date", "width": 100},
    ]


def get_data(filters):
    conditions = ["i.custom_book_item_creator IS NOT NULL"]
    values = {}

    if filters.get("publication"):
        conditions.append("i.custom_publication = %(publication)s")
        values["publication"] = filters.get("publication")
    if filters.get("subject"):
        conditions.append("i.custom_subject = %(subject)s")
        values["subject"] = filters.get("subject")
    if filters.get("class"):
        conditions.append("i.custom_class = %(class)s")
        values["class"] = filters.get("class")
    if filters.get("from_date"):
        conditions.append("i.creation >= %(from_date)s")
        values["from_date"] = filters.get("from_date")
    if filters.get("to_date"):
        conditions.append("i.creation <= %(to_date)s")
        values["to_date"] = filters.get("to_date")

    where_clause = " AND ".join(conditions)

    data = frappe.db.sql("""
        SELECT
            i.name as item_code,
            i.item_name,
            i.custom_publication as publication,
            i.custom_subject as subject,
            i.custom_class as class,
            i.custom_author as author,
            i.custom_isbn_barcode as isbn_barcode,
            i.valuation_rate,
            i.creation,
            COALESCE(bin.actual_qty, 0) as actual_qty,
            COALESCE(bin.stock_value, 0) as stock_value,
            (SELECT price_list_rate FROM `tabItem Price`
             WHERE item_code = i.name AND selling = 1 LIMIT 1) as selling_rate
        FROM `tabItem` i
        LEFT JOIN `tabBin` bin ON bin.item_code = i.name
        WHERE {where_clause}
        ORDER BY i.creation DESC
    """.format(where_clause=where_clause), values, as_dict=True)

    return data


def get_chart(data):
    # Group by publication
    pub_data = {}
    for row in data:
        pub = row.get('publication') or 'Unknown'
        pub_data[pub] = pub_data.get(pub, 0) + 1
    
    return {
        "data": {
            "labels": list(pub_data.keys()),
            "datasets": [{"values": list(pub_data.values())}]
        },
        "type": "bar",
        "colors": ["#5e64ff"]
    }


def get_summary(data):
    total_items = len(data)
    total_stock = sum(flt(row.get('actual_qty', 0)) for row in data)
    total_value = sum(flt(row.get('stock_value', 0)) for row in data)
    
    return [
        {"label": _("Total Book Items"), "value": total_items, "indicator": "blue"},
        {"label": _("Total Stock Qty"), "value": total_stock, "indicator": "green"},
        {"label": _("Total Stock Value"), "value": frappe.format_value(total_value, {"fieldtype": "Currency"}), "indicator": "orange"},
    ]
