# Copyright (c) 2024, Trustbit and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def after_install():
    """Run after app installation"""
    create_custom_fields()
    create_default_classes()
    create_default_subjects()
    frappe.db.commit()
    print("Trustbit School Book Seller App installed successfully!")


def create_custom_fields():
    """Create custom fields on Item doctype"""
    custom_fields = [
        # Book Details Section
        {
            "doctype": "Custom Field",
            "dt": "Item",
            "fieldname": "custom_book_details_section",
            "fieldtype": "Section Break",
            "label": "Book Details",
            "insert_after": "description",
            "collapsible": 1
        },
        {
            "doctype": "Custom Field",
            "dt": "Item",
            "fieldname": "custom_publication",
            "fieldtype": "Link",
            "label": "Publication",
            "options": "Publication",
            "insert_after": "custom_book_details_section"
        },
        {
            "doctype": "Custom Field",
            "dt": "Item",
            "fieldname": "custom_subject",
            "fieldtype": "Link",
            "label": "Subject",
            "options": "Subject",
            "insert_after": "custom_publication"
        },
        {
            "doctype": "Custom Field",
            "dt": "Item",
            "fieldname": "custom_class",
            "fieldtype": "Link",
            "label": "Class",
            "options": "Class Master",
            "insert_after": "custom_subject"
        },
        {
            "doctype": "Custom Field",
            "dt": "Item",
            "fieldname": "custom_author",
            "fieldtype": "Data",
            "label": "Author",
            "insert_after": "custom_class"
        },
        {
            "doctype": "Custom Field",
            "dt": "Item",
            "fieldname": "custom_edition",
            "fieldtype": "Data",
            "label": "Edition",
            "insert_after": "custom_author"
        },
        {
            "doctype": "Custom Field",
            "dt": "Item",
            "fieldname": "custom_publication_year",
            "fieldtype": "Data",
            "label": "Publication Year",
            "insert_after": "custom_edition"
        },
        {
            "doctype": "Custom Field",
            "dt": "Item",
            "fieldname": "custom_isbn_barcode",
            "fieldtype": "Data",
            "label": "ISBN/Barcode",
            "insert_after": "custom_publication_year",
            "unique": 1
        },
        # Discount Section
        {
            "doctype": "Custom Field",
            "dt": "Item",
            "fieldname": "custom_discount_section",
            "fieldtype": "Section Break",
            "label": "Discount",
            "insert_after": "custom_isbn_barcode",
            "collapsible": 1
        },
        {
            "doctype": "Custom Field",
            "dt": "Item",
            "fieldname": "custom_sales_discount_percent",
            "fieldtype": "Percent",
            "label": "Sales Discount %",
            "insert_after": "custom_discount_section"
        },
        {
            "doctype": "Custom Field",
            "dt": "Item",
            "fieldname": "custom_purchase_discount_percent",
            "fieldtype": "Percent",
            "label": "Purchase Discount %",
            "insert_after": "custom_sales_discount_percent"
        },
        {
            "doctype": "Custom Field",
            "dt": "Item",
            "fieldname": "custom_book_item_creator",
            "fieldtype": "Link",
            "label": "Created From",
            "options": "Book Item Creator",
            "insert_after": "custom_purchase_discount_percent",
            "read_only": 1
        }
    ]
    
    for field in custom_fields:
        if not frappe.db.exists("Custom Field", {"dt": field["dt"], "fieldname": field["fieldname"]}):
            doc = frappe.get_doc(field)
            doc.insert(ignore_permissions=True)
            print(f"Created custom field: {field['fieldname']}")


def create_default_classes():
    """Create default class master entries"""
    classes = [
        {"name": "Nursery", "class_name": "Nursery", "short_code": "NUR", "sort_order": 1},
        {"name": "LKG", "class_name": "LKG", "short_code": "LKG", "sort_order": 2},
        {"name": "UKG", "class_name": "UKG", "short_code": "UKG", "sort_order": 3},
        {"name": "Class 1", "class_name": "Class 1", "short_code": "C1", "sort_order": 4},
        {"name": "Class 2", "class_name": "Class 2", "short_code": "C2", "sort_order": 5},
        {"name": "Class 3", "class_name": "Class 3", "short_code": "C3", "sort_order": 6},
        {"name": "Class 4", "class_name": "Class 4", "short_code": "C4", "sort_order": 7},
        {"name": "Class 5", "class_name": "Class 5", "short_code": "C5", "sort_order": 8},
        {"name": "Class 6", "class_name": "Class 6", "short_code": "C6", "sort_order": 9},
        {"name": "Class 7", "class_name": "Class 7", "short_code": "C7", "sort_order": 10},
        {"name": "Class 8", "class_name": "Class 8", "short_code": "C8", "sort_order": 11},
        {"name": "Class 9", "class_name": "Class 9", "short_code": "C9", "sort_order": 12},
        {"name": "Class 10", "class_name": "Class 10", "short_code": "C10", "sort_order": 13},
        {"name": "Class 11", "class_name": "Class 11", "short_code": "C11", "sort_order": 14},
        {"name": "Class 12", "class_name": "Class 12", "short_code": "C12", "sort_order": 15},
    ]
    
    for cls in classes:
        if not frappe.db.exists("Class Master", cls["name"]):
            doc = frappe.get_doc({
                "doctype": "Class Master",
                **cls
            })
            doc.insert(ignore_permissions=True)
            print(f"Created class: {cls['name']}")


def create_default_subjects():
    """Create default subject entries"""
    subjects = [
        {"name": "Mathematics", "subject_name": "Mathematics", "short_code": "MATH", "sort_order": 1},
        {"name": "English", "subject_name": "English", "short_code": "ENG", "sort_order": 2},
        {"name": "Hindi", "subject_name": "Hindi", "short_code": "HIN", "sort_order": 3},
        {"name": "Science", "subject_name": "Science", "short_code": "SCI", "sort_order": 4},
        {"name": "Social Science", "subject_name": "Social Science", "short_code": "SST", "sort_order": 5},
        {"name": "Physics", "subject_name": "Physics", "short_code": "PHY", "sort_order": 6},
        {"name": "Chemistry", "subject_name": "Chemistry", "short_code": "CHEM", "sort_order": 7},
        {"name": "Biology", "subject_name": "Biology", "short_code": "BIO", "sort_order": 8},
        {"name": "Computer Science", "subject_name": "Computer Science", "short_code": "CS", "sort_order": 9},
        {"name": "Economics", "subject_name": "Economics", "short_code": "ECO", "sort_order": 10},
        {"name": "Accountancy", "subject_name": "Accountancy", "short_code": "ACC", "sort_order": 11},
        {"name": "Business Studies", "subject_name": "Business Studies", "short_code": "BST", "sort_order": 12},
        {"name": "Geography", "subject_name": "Geography", "short_code": "GEO", "sort_order": 13},
        {"name": "History", "subject_name": "History", "short_code": "HIST", "sort_order": 14},
        {"name": "Political Science", "subject_name": "Political Science", "short_code": "POL", "sort_order": 15},
        {"name": "Sanskrit", "subject_name": "Sanskrit", "short_code": "SANS", "sort_order": 16},
        {"name": "Physical Education", "subject_name": "Physical Education", "short_code": "PE", "sort_order": 17},
        {"name": "Art & Craft", "subject_name": "Art & Craft", "short_code": "ART", "sort_order": 18},
        {"name": "Music", "subject_name": "Music", "short_code": "MUS", "sort_order": 19},
        {"name": "General Knowledge", "subject_name": "General Knowledge", "short_code": "GK", "sort_order": 20},
    ]
    
    for subj in subjects:
        if not frappe.db.exists("Subject", subj["name"]):
            doc = frappe.get_doc({
                "doctype": "Subject",
                **subj
            })
            doc.insert(ignore_permissions=True)
            print(f"Created subject: {subj['name']}")
