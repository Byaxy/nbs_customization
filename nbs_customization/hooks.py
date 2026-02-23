app_name = "nbs_customization"
app_title = "NBS Customization"
app_publisher = "Charles Byakutaga/NBS"
app_description = "Custom app for Northland Biomedical Solutions"
app_email = "charlesbyaxy@gmail.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "nbs_customization",
# 		"logo": "/assets/nbs_customization/logo.png",
# 		"title": "NBS Customization",
# 		"route": "/nbs_customization",
# 		"has_permission": "nbs_customization.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------
import time

# include js, css files in header of desk.html
app_include_css = "/assets/nbs_customization/css/nbs_theme.css?v={}".format(int(time.time()))
app_include_js = "/assets/nbs_customization/js/nbs_theme.js?v={}".format(int(time.time()))

# include js, css files in header of web template
web_include_css = "/assets/nbs_customization/css/nbs_theme.css?v={}".format(int(time.time()))
web_include_js = "/assets/nbs_customization/js/nbs_theme.js?v={}".format(int(time.time()))

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "nbs_customization/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "nbs_customization/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "nbs_customization.utils.jinja_methods",
# 	"filters": "nbs_customization.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "nbs_customization.install.before_install"
# after_install = "nbs_customization.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "nbs_customization.uninstall.before_uninstall"
# after_uninstall = "nbs_customization.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "nbs_customization.utils.before_app_install"
# after_app_install = "nbs_customization.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "nbs_customization.utils.before_app_uninstall"
# after_app_uninstall = "nbs_customization.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "nbs_customization.notifications.get_notification_config"

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

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"nbs_customization.tasks.all"
# 	],
# 	"daily": [
# 		"nbs_customization.tasks.daily"
# 	],
# 	"hourly": [
# 		"nbs_customization.tasks.hourly"
# 	],
# 	"weekly": [
# 		"nbs_customization.tasks.weekly"
# 	],
# 	"monthly": [
# 		"nbs_customization.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "nbs_customization.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "nbs_customization.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "nbs_customization.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "nbs_customization.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["nbs_customization.utils.before_request"]
# after_request = ["nbs_customization.utils.after_request"]

# Job Events
# ----------
# before_job = ["nbs_customization.utils.before_job"]
# after_job = ["nbs_customization.utils.after_job"]

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
# 	"nbs_customization.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

# Fixtures

fixtures = [
    
      {
        "dt": "Custom Field",
        "filters": [
            [
                "name", "in", [
                    "Item-custom_item_type",
                    "Company-custom_bank_name",
                    "Company-custom_bank_address",
                    "Company-custom_account_number", 
                    "Company-custom_swift_code",
                    "Company-custom_pdf_water_mark",
                    "Company-custom_phone_no_2",
                    "Company-custom_address_line_1",
                    "Company-custom_address_line_2",
                    "Quotation-custom_request_for_quotation_number",
                    "Delivery Note-custom_waybill_type",
                    "Delivery Note-custom_officer_details",
                    "Sales Order-custom_has_promissory_note",
                    "Sales Order-custom_has_customer_delivery_note",     
                    "Delivery Note-custom_loan_waybill_section",
                    "Delivery Note-custom_source_loan_waybill",
                    "Delivery Note-custom_loan_waybill_column_break",
                    "Delivery Note-custom_conversion_date",
                    "Delivery Note-custom_is_conversion",
                    "Delivery Note-custom_officer_details",
                    "Delivery Note-custom_delivered_by",
                    "Delivery Note-custom_officer_column_break",
                    "Delivery Note-custom_received_by",
                    "Stock Entry-custom_is_loan"
                ]
            ]
        ]
    },
    # Export custom DocTypes
    {
        "dt": "DocType",
        "filters": [
            [
                "name", "in", [
                    "Customer Delivery Note",
                    "Promissory Note", 
                    "Item Type",
                    "Customer Delivery Note Item",
                    "Promissory Note Item"
                ]
            ]
        ]
    }
]

doctype_js = {
    "Sales Order": "public/js/sales_order.js",
    "Delivery Note": "public/js/delivery_note.js"
}

doc_events = {
    "Quotation": {
        "validate": "nbs_customization.controllers.validations.sales.validate_unique_items"
    },
    "Sales Order": {
        "validate": "nbs_customization.controllers.validations.sales.validate_unique_items",
        "on_submit": "nbs_customization.controllers.sales_order.ensure_linked_documents_on_submit",
    },
    "Delivery Note": {
        "validate": [
            "nbs_customization.controllers.validations.stock.validate_unique_item_batch",
            "nbs_customization.controllers.delivery_note.validate",
        ],
        "on_submit": "nbs_customization.controllers.delivery_note.on_submit",
        "on_cancel": "nbs_customization.controllers.delivery_note.on_cancel",
    },
    "Sales Invoice": {
        "validate": "nbs_customization.controllers.validations.stock.validate_unique_item_batch"
    },
    "Stock Entry": {
        "validate": "nbs_customization.controllers.validations.stock.validate_unique_item_batch",
        "before_cancel": "nbs_customization.controllers.stock_entry.before_cancel",
    },
    "Loan Waybill": {
        "validate": "nbs_customization.controllers.validations.sales.validate_unique_items"
    }
}