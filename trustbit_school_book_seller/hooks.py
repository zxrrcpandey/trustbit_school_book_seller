app_name = "trustbit_school_book_seller"
app_title = "Trustbit School Book Seller"
app_publisher = "Trustbit"
app_description = "Advanced Item Creation System for School Book Shops"
app_email = "info@trustbit.com"
app_license = "MIT"
app_version = "1.0.0"

# Required Apps
required_apps = ["erpnext"]

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

# Doctype JS (Client Scripts)
# ---------------------------
doctype_js = {
    "Book Item Creator": "public/js/book_item_creator.js"
}

# Doctype List JS
# ---------------
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}

# Doctype Tree JS
# ---------------
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}

# Doctype Calendar JS
# -------------------
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Fixtures
# --------
fixtures = [
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
                "Item-custom_book_item_creator",
                "Item-custom_column_break_book"
            ]]
        ]
    },
    {
        "doctype": "Class Master"
    },
    {
        "doctype": "Subject"
    }
]

# Installation Hooks
# ------------------
after_install = "trustbit_school_book_seller.install.after_install"
# before_uninstall = "trustbit_school_book_seller.uninstall.before_uninstall"

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
    # "Item": {
    #     "validate": "trustbit_school_book_seller.events.item.validate"
    # }
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
#     "all": [
#         "trustbit_school_book_seller.tasks.all"
#     ],
#     "daily": [
#         "trustbit_school_book_seller.tasks.daily"
#     ],
#     "hourly": [
#         "trustbit_school_book_seller.tasks.hourly"
#     ],
#     "weekly": [
#         "trustbit_school_book_seller.tasks.weekly"
#     ],
#     "monthly": [
#         "trustbit_school_book_seller.tasks.monthly"
#     ],
# }

# Testing
# -------

# before_tests = "trustbit_school_book_seller.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
#     "frappe.desk.doctype.event.event.get_events": "trustbit_school_book_seller.event.get_events"
# }

# override_doctype_dashboards = {
#     "Task": "trustbit_school_book_seller.task.get_dashboard_data"
# }

# Permission Query Conditions
# ---------------------------
#
# permission_query_conditions = {
#     "Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }

# Document Actions
# ----------------
# Jinja methods
# jinja = {
#     "methods": "trustbit_school_book_seller.utils.jinja_methods",
#     "filters": "trustbit_school_book_seller.utils.jinja_filters"
# }

# User Data Protection
# --------------------
user_data_fields = [
    {
        "doctype": "{doctype_1}",
        "filter_by": "{filter_by}",
        "redact_fields": ["{field_1}", "{field_2}"],
        "partial": 1,
    },
]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
#     "trustbit_school_book_seller.auth.validate"
# ]
