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
# app_include_js = "/assets/trustbit_school_book_seller/js/trustbit_school_book_seller.js"

# include js, css files in header of web template
# web_include_css = "/assets/trustbit_school_book_seller/css/trustbit_school_book_seller.css"
# web_include_js = "/assets/trustbit_school_book_seller/js/trustbit_school_book_seller.js"

# include custom scss in every website theme (without signing in)
# website_theme_scss = "trustbit_school_book_seller/public/scss/website"

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
    "Book Item Creator": "public/js/book_item_creator.js"
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

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
#	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"trustbit_school_book_seller.tasks.all"
# 	],
# 	"daily": [
# 		"trustbit_school_book_seller.tasks.daily"
# 	],
# 	"hourly": [
# 		"trustbit_school_book_seller.tasks.hourly"
# 	],
# 	"weekly": [
# 		"trustbit_school_book_seller.tasks.weekly"
# 	],
# 	"monthly": [
# 		"trustbit_school_book_seller.tasks.monthly"
# 	],
# }

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
                "Item-custom_author",
                "Item-custom_edition",
                "Item-custom_publication_year",
                "Item-custom_isbn_barcode",
                "Item-custom_discount_section",
                "Item-custom_sales_discount_percent",
                "Item-custom_purchase_discount_percent",
                "Item-custom_book_item_creator"
            ]]
        ]
    }
]
