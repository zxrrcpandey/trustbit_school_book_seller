import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def after_install():
    """Run after app installation"""
    create_item_custom_fields()
    create_default_classes()
    create_default_subjects()
    frappe.db.commit()
    print("Trustbit School Book Seller App installed successfully!")


def create_item_custom_fields():
    """Create custom fields on Item doctype for book details"""
    
    custom_fields = {
        "Item": [
            {
                "fieldname": "custom_book_details_section",
                "label": "Book Details",
                "fieldtype": "Section Break",
                "insert_after": "description",
                "collapsible": 1
            },
            {
                "fieldname": "custom_publication",
                "label": "Publication",
                "fieldtype": "Link",
                "options": "Publication",
                "insert_after": "custom_book_details_section"
            },
            {
                "fieldname": "custom_subject",
                "label": "Subject",
                "fieldtype": "Link",
                "options": "Subject",
                "insert_after": "custom_publication"
            },
            {
                "fieldname": "custom_class",
                "label": "Class",
                "fieldtype": "Link",
                "options": "Class Master",
                "insert_after": "custom_subject"
            },
            {
                "fieldname": "custom_author",
                "label": "Author",
                "fieldtype": "Data",
                "insert_after": "custom_class"
            },
            {
                "fieldname": "custom_column_break_book",
                "fieldtype": "Column Break",
                "insert_after": "custom_author"
            },
            {
                "fieldname": "custom_edition",
                "label": "Edition",
                "fieldtype": "Data",
                "insert_after": "custom_column_break_book"
            },
            {
                "fieldname": "custom_publication_year",
                "label": "Publication Year",
                "fieldtype": "Data",
                "insert_after": "custom_edition"
            },
            {
                "fieldname": "custom_isbn_barcode",
                "label": "ISBN/Barcode",
                "fieldtype": "Data",
                "insert_after": "custom_publication_year",
                "unique": 1
            },
            {
                "fieldname": "custom_discount_section",
                "label": "Discount Details",
                "fieldtype": "Section Break",
                "insert_after": "custom_isbn_barcode",
                "collapsible": 1
            },
            {
                "fieldname": "custom_sales_discount_percent",
                "label": "Sales Discount %",
                "fieldtype": "Percent",
                "insert_after": "custom_discount_section"
            },
            {
                "fieldname": "custom_purchase_discount_percent",
                "label": "Purchase Discount %",
                "fieldtype": "Percent",
                "insert_after": "custom_sales_discount_percent"
            },
            {
                "fieldname": "custom_book_item_creator",
                "label": "Created From",
                "fieldtype": "Link",
                "options": "Book Item Creator",
                "insert_after": "custom_purchase_discount_percent",
                "read_only": 1
            }
        ]
    }
    
    create_custom_fields(custom_fields, update=True)
    print("Custom fields created on Item doctype")


def create_default_classes():
    """Create default class masters (Class 1 to Class 12)"""
    
    classes = [
        {"class_name": "Nursery", "short_code": "NUR", "display_order": 1},
        {"class_name": "LKG", "short_code": "LKG", "display_order": 2},
        {"class_name": "UKG", "short_code": "UKG", "display_order": 3},
        {"class_name": "Class 1", "short_code": "01", "display_order": 4},
        {"class_name": "Class 2", "short_code": "02", "display_order": 5},
        {"class_name": "Class 3", "short_code": "03", "display_order": 6},
        {"class_name": "Class 4", "short_code": "04", "display_order": 7},
        {"class_name": "Class 5", "short_code": "05", "display_order": 8},
        {"class_name": "Class 6", "short_code": "06", "display_order": 9},
        {"class_name": "Class 7", "short_code": "07", "display_order": 10},
        {"class_name": "Class 8", "short_code": "08", "display_order": 11},
        {"class_name": "Class 9", "short_code": "09", "display_order": 12},
        {"class_name": "Class 10", "short_code": "10", "display_order": 13},
        {"class_name": "Class 11", "short_code": "11", "display_order": 14},
        {"class_name": "Class 12", "short_code": "12", "display_order": 15},
    ]
    
    for cls in classes:
        if not frappe.db.exists("Class Master", cls["class_name"]):
            doc = frappe.get_doc({
                "doctype": "Class Master",
                "class_name": cls["class_name"],
                "short_code": cls["short_code"],
                "display_order": cls["display_order"]
            })
            doc.insert(ignore_permissions=True)
    
    print("Default classes created")


def create_default_subjects():
    """Create default subject masters"""
    
    subjects = [
        {"subject_name": "Mathematics", "short_code": "MATH"},
        {"subject_name": "English", "short_code": "ENG"},
        {"subject_name": "Hindi", "short_code": "HIN"},
        {"subject_name": "Science", "short_code": "SCI"},
        {"subject_name": "Social Science", "short_code": "SST"},
        {"subject_name": "Physics", "short_code": "PHY"},
        {"subject_name": "Chemistry", "short_code": "CHEM"},
        {"subject_name": "Biology", "short_code": "BIO"},
        {"subject_name": "Computer Science", "short_code": "CS"},
        {"subject_name": "Economics", "short_code": "ECO"},
        {"subject_name": "Accountancy", "short_code": "ACC"},
        {"subject_name": "Business Studies", "short_code": "BST"},
        {"subject_name": "History", "short_code": "HIST"},
        {"subject_name": "Geography", "short_code": "GEO"},
        {"subject_name": "Political Science", "short_code": "POL"},
        {"subject_name": "Sanskrit", "short_code": "SAN"},
        {"subject_name": "Environmental Studies", "short_code": "EVS"},
        {"subject_name": "General Knowledge", "short_code": "GK"},
        {"subject_name": "Art & Craft", "short_code": "ART"},
        {"subject_name": "Physical Education", "short_code": "PE"},
    ]
    
    for subj in subjects:
        if not frappe.db.exists("Subject", subj["subject_name"]):
            doc = frappe.get_doc({
                "doctype": "Subject",
                "subject_name": subj["subject_name"],
                "short_code": subj["short_code"]
            })
            doc.insert(ignore_permissions=True)
    
    print("Default subjects created")
