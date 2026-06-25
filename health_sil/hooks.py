app_name = "health_sil"
app_title = "Health Sil"
app_publisher = "softland"
app_description = "health app"
app_email = "softland@gmail.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "health_sil",
# 		"logo": "/assets/health_sil/logo.png",
# 		"title": "Health Sil",
# 		"route": "/health_sil",
# 		"has_permission": "health_sil.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/health_sil/css/health_sil.css"
# app_include_js = "/assets/health_sil/js/health_sil.js"

# include js, css files in header of web template
# web_include_css = "/assets/health_sil/css/health_sil.css"
# web_include_js = "/assets/health_sil/js/health_sil.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "health_sil/public/scss/website"

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
# app_include_icons = "health_sil/public/icons.svg"

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

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "health_sil.utils.jinja_methods",
# 	"filters": "health_sil.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "health_sil.install.before_install"
# after_install = "health_sil.install.after_install"
after_install = "health_sil.setup.setup_permissions.setup_custom_role_permissions"
after_migrate = "health_sil.setup.setup_permissions.setup_custom_role_permissions"

on_session_creation = ["health_sil.services.api.set_login_redirect"]

# Uninstallation
# ------------

# before_uninstall = "health_sil.uninstall.before_uninstall"
# after_uninstall = "health_sil.uninstall.after_uninstall"


# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "health_sil.utils.before_app_install"
# after_app_install = "health_sil.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "health_sil.utils.before_app_uninstall"
# after_app_uninstall = "health_sil.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "health_sil.notifications.get_notification_config"

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
# 	}
# }
doc_events = {
    "Patient": {
        "after_insert": "health_sil.services.address_api.create_address_from_patient",
        # "before_insert": "health_sil.services.naming.before_insert",  # Path to the method
        "before_insert": "health_sil.services.naming.generate_custom_uid"
    },
    "Item": {
        "after_insert": [
            "health_sil.services.batch_api.create_batch_from_item",
            "health_sil.services.price_list_api.add_price_list_from_item",
        ],
        "on_update": "health_sil.services.price_list_api.update_price_list_from_item",  # This will run on save or update
    },
    "Purchase Invoice": {
        "on_submit": [
            "health_sil.services.items.update_item_valuation_rate_on_submit"
        ]
    },
    "Laboratory Bill": {
        "on_submit": "health_sil.services.laboratory_bill.create_lab_tests_for_bill"
    }
}


# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"health_sil.tasks.all"
# 	],
# 	"daily": [
# 		"health_sil.tasks.daily"
# 	],
# 	"hourly": [
# 		"health_sil.tasks.hourly"
# 	],
# 	"weekly": [
# 		"health_sil.tasks.weekly"
# 	],
# 	"monthly": [
# 		"health_sil.tasks.monthly"
# 	],
# }

# scheduler_events = {
#     "weekly": [
#         "health_sil.tasks.clear_token_history"
#     ],
# }

# scheduler_events = {
#     "daily": [
#         "health_sil.tasks.clear_token_history"
#     ]
# }


scheduler_events = {
    "cron": {
        "59 23 * * *": [
            "health_sil.tasks.clear_token_history",
            "health_sil.services.batch_api.notify_batches_due_today"
        ]
    }
}

# Testing
# -------

# before_tests = "health_sil.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "health_sil.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "health_sil.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["health_sil.utils.before_request"]
# after_request = ["health_sil.utils.after_request"]

# Job Events
# ----------
# before_job = ["health_sil.utils.before_job"]
# after_job = ["health_sil.utils.after_job"]

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
# 	"health_sil.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

fixtures = [
    "Client Script",
    "Server Script",
    # "Custom Field",
    {
        "dt": "Custom Field",
        "filters": [["module", "=", "Health Sil"]]
    },
    "Property Setter",
    "Print Format",
    # "DocType",
    "Report",
    # "Letter Head",
    # "Workflow",
    # "Workflow State",
    # "Workflow Action",
    # "Workflow Action Master",
    # Additional fields
    # {"dt": "Custom DocPerm"},
    {
        "dt": "Role",
        "filters": [["name", "in", ["Reception Staff", "Pharmacy Staff", "Laboratory Staff", "Nursing Staff"]]]
    },
    # {"dt": "Custom Role"},
    {"dt": "Module Def"},
    # {"dt": "Translation"},
    # {"dt": "Portal Menu Item"},
    # {"dt": "Web Page"},
    {"dt": "Web Form"},
    # {"dt": "Notification"},
    # {"dt": "Email Alert"},
    # {"dt": "Email Template"},
    #{"dt": "Dashboard"},
    #  {"dt": "Dashboard",
    #     "filters": [["is_standard", "=", "0"]],
    #     "ignore_version": 1},
    {
        "dt": "Dashboard Chart",
        "filters": [["document_type", "=", "Patient Encounter"]]
    },
    # {"dt": "User Permission"}
    {"dt": "Lab Test Template"},
]
