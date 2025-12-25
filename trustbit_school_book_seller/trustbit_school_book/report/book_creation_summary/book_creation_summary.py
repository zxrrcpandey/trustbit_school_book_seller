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
        {"label": _("Book Entry"), "fieldname": "name", "fieldtype": "Link", "options": "Book Item Creator", "width": 150},
        {"label": _("Publication"), "fieldname": "publication", "fieldtype": "Link", "options": "Publication", "width": 120},
        {"label": _("Book Name"), "fieldname": "book_name", "fieldtype": "Data", "width": 180},
        {"label": _("Subject"), "fieldname": "subject", "fieldtype": "Link", "options": "Subject", "width": 120},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
        {"label": _("Total Items"), "fieldname": "total_items_to_create", "fieldtype": "Int", "width": 100},
        {"label": _("Items Created"), "fieldname": "items_created", "fieldtype": "Int", "width": 110},
        {"label": _("Success Rate"), "fieldname": "success_rate", "fieldtype": "Percent", "width": 100},
        {"label": _("Total Stock"), "fieldname": "total_opening_stock", "fieldtype": "Float", "width": 100},
        {"label": _("Stock Value"), "fieldname": "total_stock_value", "fieldtype": "Currency", "width": 120},
        {"label": _("Created By"), "fieldname": "owner", "fieldtype": "Link", "options": "User", "width": 120},
        {"label": _("Created On"), "fieldname": "creation", "fieldtype": "Date", "width": 100},
    ]


def get_data(filters):
    conditions = "WHERE docstatus = 1"
    
    if filters.get("publication"):
        conditions += f" AND publication = '{filters.get('publication')}'"
    if filters.get("subject"):
        conditions += f" AND subject = '{filters.get('subject')}'"
    if filters.get("status"):
        conditions += f" AND status = '{filters.get('status')}'"
    if filters.get("from_date"):
        conditions += f" AND creation >= '{filters.get('from_date')}'"
    if filters.get("to_date"):
        conditions += f" AND creation <= '{filters.get('to_date')}'"
    
    data = frappe.db.sql(f"""
        SELECT 
            name,
            publication,
            book_name,
            subject,
            status,
            total_items_to_create,
            items_created,
            ROUND((items_created / NULLIF(total_items_to_create, 0)) * 100, 1) as success_rate,
            total_opening_stock,
            total_stock_value,
            owner,
            creation
        FROM `tabBook Item Creator`
        {conditions}
        ORDER BY creation DESC
    """, as_dict=True)
    
    return data


def get_chart(data):
    status_data = {}
    for row in data:
        status = row.get('status') or 'Unknown'
        status_data[status] = status_data.get(status, 0) + 1
    
    return {
        "data": {
            "labels": list(status_data.keys()),
            "datasets": [{"values": list(status_data.values())}]
        },
        "type": "pie",
        "colors": ["#28a745", "#ffc107", "#dc3545", "#6c757d"]
    }


def get_summary(data):
    total_entries = len(data)
    total_items = sum(row.get('items_created', 0) for row in data)
    total_value = sum(flt(row.get('total_stock_value', 0)) for row in data)
    completed = len([d for d in data if d.get('status') == 'Completed'])
    
    return [
        {"label": _("Total Entries"), "value": total_entries, "indicator": "blue"},
        {"label": _("Items Created"), "value": total_items, "indicator": "green"},
        {"label": _("Completed"), "value": completed, "indicator": "green"},
        {"label": _("Total Value"), "value": frappe.format_value(total_value, {"fieldtype": "Currency"}), "indicator": "orange"},
    ]
