app_name = "trustbit_school_book_seller"
app_title = "Trustbit School Book Seller"
app_publisher = "Trustbit"
app_description = "School Book Seller App for ERPNext - Bulk Book Item Creation"
app_email = "info@trustbit.in"
app_license = "MIT"
app_version = "1.0.0"

# Required Apps
required_apps = ["frappe", "erpnext"]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/trustbit_school_book_seller/css/trustbit_school_book_seller.css"
app_include_js = "/assets/trustbit_school_book_seller/js/sales_invoice_print.js"

# include js, css files in header of web template
# web_include_css = "/assets/trustbit_school_book_seller/css/trustbit_school_book_seller.css"
# web_include_js = "/assets/trustbit_school_book_seller/js/trustbit_school_book_seller.js"

# include custom scss in every website theme (without signing in)
# website_theme_scss = "trustbit_school_book_seller/public/scss/website"

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
    "Book Item Creator": "public/js/book_item_creator.js",
    "Sales Order": ["public/js/sales_order.js", "public/js/product_bundle.js", "public/js/privilege_card_so_si.js"],
    "Sales Invoice": ["public/js/product_bundle.js", "public/js/privilege_card_so_si.js", "public/js/return_scanner.js"],
    "Purchase Order": ["public/js/product_bundle.js", "public/js/purchase_order_followup.js"],
    "Purchase Invoice": ["public/js/product_bundle.js", "public/js/return_scanner.js"],
    "Material Request": "public/js/product_bundle.js",
    "Product Bundle": "public/js/product_bundle_form.js",
    "User Print Config": "public/js/user_print_config.js",
}

# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
#	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Installation
# ------------

# before_install = "trustbit_school_book_seller.install.before_install"
after_install = "trustbit_school_book_seller.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "trustbit_school_book_seller.uninstall.before_uninstall"
# after_uninstall = "trustbit_school_book_seller.uninstall.after_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "trustbit_school_book_seller.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Sales Invoice": {
		"before_save": "trustbit_school_book_seller.api.copy_school_name_to_invoice",
		"before_validate": "trustbit_school_book_seller.privilege_card.validate_privilege_card_on_doc",
		"after_insert": "trustbit_school_book_seller.api.on_sales_invoice_save",
		"on_submit": [
			"trustbit_school_book_seller.api.on_sales_invoice_submit",
			"trustbit_school_book_seller.privilege_card.log_privilege_card_usage",
		],
	},
	"Sales Order": {
		"before_validate": "trustbit_school_book_seller.privilege_card.validate_privilege_card_on_doc",
		"on_submit": "trustbit_school_book_seller.privilege_card.log_privilege_card_usage",
	},
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"daily": [
		"trustbit_school_book_seller.privilege_card.expire_cards_daily",
		"trustbit_school_book_seller.followup_api.send_followup_reminders",
		"trustbit_school_book_seller.followup_api.check_pos_without_followups",
	],
}

# Testing
# -------

# before_tests = "trustbit_school_book_seller.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "trustbit_school_book_seller.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "trustbit_school_book_seller.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"trustbit_school_book_seller.auth.validate"
# ]

# Fixtures - Export these doctypes when running bench export-fixtures
fixtures = [
    {
        "doctype": "Subject",
        "filters": []
    },
    {
        "doctype": "Class Master",
        "filters": []
    },
    {
        "doctype": "Custom Field",
        "filters": [
            ["name", "in", [
                "Item-custom_book_details_section",
                "Item-custom_publication",
                "Item-custom_subject",
                "Item-custom_class",
                "Item-custom_class_grades",
                "Item-custom_column_break_book",
                "Item-custom_author",
                "Item-custom_edition",
                "Item-custom_edition_year",
                "Item-custom_publication_year",
                "Item-custom_isbn",
                "Item-custom_isbn_barcode",
                "Item-custom_publisher",
                "Item-custom_discount_section",
                "Item-custom_sales_discount_percent",
                "Item-custom_purchase_discount_percent",
                "Item-custom_book_item_creator",
                "Sales Order-custom_school_name",
                "Purchase Order-custom_school_name",
                "Purchase Order-custom_remark",
                "Purchase Order-custom_transport_name",
                "Sales Invoice-custom_school_name",
                "Sales Order-custom_privilege_card",
                "Sales Order-custom_privilege_card_discount",
                "Sales Invoice-custom_privilege_card",
                "Sales Invoice-custom_privilege_card_discount",
                "Purchase Order-custom_followup_section",
                "Purchase Order-custom_last_followup_date",
                "Purchase Order-custom_last_followup_status",
                "Purchase Order-custom_column_break_followup",
                "Purchase Order-custom_next_followup_date",
                "Purchase Order-custom_total_followups"
            ]]
        ]
    },
    {
        "doctype": "Print Format",
        "filters": [
            ["name", "in", ["KGS Purchase Order", "80MM Token"]]
        ]
    }
]
