// Copyright (c) 2024, Trustbit and contributors
// For license information, please see license.txt

frappe.query_reports["Book Items Report"] = {
    "filters": [
        {
            "fieldname": "publication",
            "label": __("Publication"),
            "fieldtype": "Link",
            "options": "Publication"
        },
        {
            "fieldname": "subject",
            "label": __("Subject"),
            "fieldtype": "Link",
            "options": "Subject"
        },
        {
            "fieldname": "class",
            "label": __("Class"),
            "fieldtype": "Link",
            "options": "Class Master"
        },
        {
            "fieldname": "from_date",
            "label": __("From Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.add_months(frappe.datetime.get_today(), -1)
        },
        {
            "fieldname": "to_date",
            "label": __("To Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.get_today()
        }
    ]
};
