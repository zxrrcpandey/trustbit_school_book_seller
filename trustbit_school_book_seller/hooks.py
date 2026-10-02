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
app_include_js = [
	"/assets/trustbit_school_book_seller/js/sales_invoice_print.js",
	"/assets/trustbit_school_book_seller/js/po_print_title.js",
]

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
    "Purchase Order": ["public/js/product_bundle.js", "public/js/purchase_order_followup.js", "public/js/purchase_order_approval.js"],
    "Purchase Invoice": ["public/js/product_bundle.js", "public/js/return_scanner.js"],
    "Material Request": "public/js/product_bundle.js",
    "Product Bundle": "public/js/product_bundle_form.js",
    "User Print Config": "public/js/user_print_config.js",
    "Multi Print Setting": "public/js/multi_print_setting.js",
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
		"before_validate": [
			"trustbit_school_book_seller.api.fill_missing_item_defaults",
			"trustbit_school_book_seller.privilege_card.validate_privilege_card_on_doc",
		],
		"after_insert": "trustbit_school_book_seller.api.on_sales_invoice_save",
		"on_submit": [
			"trustbit_school_book_seller.api.on_sales_invoice_submit",
			"trustbit_school_book_seller.privilege_card.log_privilege_card_usage",
		],
	},
	"Sales Order": {
		"before_validate": [
			"trustbit_school_book_seller.api.fill_missing_item_defaults",
			"trustbit_school_book_seller.privilege_card.validate_privilege_card_on_doc",
		],
		"on_submit": "trustbit_school_book_seller.privilege_card.log_privilege_card_usage",
	},
	"Purchase Order": {
		"before_validate": "trustbit_school_book_seller.api.fill_missing_item_defaults",
		# Shop Owner approval (workflow "Purchase Order Approval") — see po_approval.py
		"validate": "trustbit_school_book_seller.po_approval.clear_stale_rejection_reason",
		"on_update": "trustbit_school_book_seller.po_approval.notify_on_state_change",
		"before_submit": "trustbit_school_book_seller.po_approval.only_shop_owner",
		"before_cancel": "trustbit_school_book_seller.po_approval.only_shop_owner",
	},
	"Purchase Invoice": {
		"before_validate": "trustbit_school_book_seller.api.fill_missing_item_defaults",
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
	"cron": {
		# Staff app long sessions: keep stamped session rows above the global
		# 1-hour threshold (staff_app/session_extend.py; inert without
		# site_config kgs_staff_session_days)
		"*/10 * * * *": [
			"trustbit_school_book_seller.staff_app.session_extend.touch_staff_sessions",
		],
	},
}

# KGS Staff app (/staff PWA) — staff_app/, www/staff.py, frontend/
# ONLY the SPA's own routes rewrite to the www/staff shell. Deliberately NOT a
# /staff/<path> catch-all: it would swallow the raw-served service worker
# (www/staff/sw.min.js) and manifest (www/staff/manifest.webmanifest).
# Every new top-level app route needs its own rule here.
website_route_rules = [
	{"from_route": "/staff/home", "to_route": "staff"},
	{"from_route": "/staff/login", "to_route": "staff"},
	{"from_route": "/staff/transfer", "to_route": "staff"},
	{"from_route": "/staff/transfers", "to_route": "staff"},
	{"from_route": "/staff/t/<path:app_path>", "to_route": "staff"},
]

# Staff app long sessions (owner decision 2026-10-02) — see session_extend.py
on_session_creation = [
	"trustbit_school_book_seller.staff_app.session_extend.stamp_staff_session_expiry",
]
after_request = [
	"trustbit_school_book_seller.staff_app.session_extend.extend_staff_session_cookie",
]

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
# Purchase Order PDFs download as "<PO ID> - <Supplier Name>.pdf"
override_whitelisted_methods = {
	"frappe.utils.print_format.download_pdf": "trustbit_school_book_seller.api.download_pdf",
	# One-tap Approve from the Shop Owners' PO approval email (po_approval.py); every
	# other workflow email link falls through to frappe's own functions.
	"frappe.workflow.doctype.workflow_action.workflow_action.apply_action": "trustbit_school_book_seller.po_approval.apply_action",
	"frappe.workflow.doctype.workflow_action.workflow_action.confirm_action": "trustbit_school_book_seller.po_approval.confirm_action",
}

# Purchase Order /printview page titled "<PO ID> - <Supplier Name>" so
# browser print -> Save as PDF suggests that filename
update_website_context = "trustbit_school_book_seller.api.update_website_context"
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
                "Purchase Order-custom_total_followups",
                "Product Bundle-custom_sell_goal",
                "Purchase Order-custom_rejection_reason"
            ]]
        ]
    },
    {
        "doctype": "Print Format",
        "filters": [
            ["name", "in", ["KGS Purchase Order", "80MM Token"]]
        ]
    },
    {
        # Name-filtered on purpose: the site has other Client Scripts
        # (e.g. "Privilege Card SI Rate Fix") that are NOT owned by this app.
        # Adding them here would make bench migrate overwrite the DB copy.
        "doctype": "Client Script",
        "filters": [
            ["name", "in", ["Sales Invoice - Update Stock default for new invoices"]]
        ]
    },
    # Purchase Order approval by the Shop Owners (po_approval.py). Re-importing a
    # Role on migrate does NOT remove it from users (Has Role rows belong to User).
    {"doctype": "Role", "filters": [["name", "in", ["Shop Owner"]]]},
    {
        "doctype": "Workflow State",
        "filters": [["name", "in", ["Draft", "Pending Approval", "Approved", "Rejected", "Cancelled"]]]
    },
    {
        "doctype": "Workflow Action Master",
        "filters": [["name", "in", ["Send for Approval", "Approve", "Reject", "Cancel"]]]
    },
    {"doctype": "Email Template", "filters": [["name", "in", ["Purchase Order Approval Request"]]]},
    {"doctype": "Workflow", "filters": [["name", "in", ["Purchase Order Approval"]]]}
]
