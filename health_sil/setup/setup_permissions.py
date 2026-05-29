import frappe

# Minimum permissions needed by custom roles for backend API operations.
# These permissions allow internal ERPNext functions (set_missing_values,
# _get_party_details, Serial and Batch Bundle creation) to pass permission
# checks when billing APIs are called by restricted users.
#
# What's NOT included here and why:
#   - Stock Ledger Entry / GL Entry create perms: ERPNext sets
#     flags.ignore_permissions internally in stock_ledger.make_entry and
#     general_ledger.make_entry, so user perms are not needed.
#   - Payment Entry submit perms: The API sets
#     doc.flags.ignore_permissions = True on the Payment Entry doc itself,
#     which is sufficient.
#
# What IS included and why:
#   - Serial and Batch Bundle: ERPNext's make_serial_and_batch_bundle
#     does doc.save() and doc.submit() WITHOUT setting ignore_permissions,
#     so the calling user needs perms on this doctype.
#   - Read-only on lookup tables (Customer, Item, Account, etc.): needed
#     for invoice validation and party detail lookups.

_BILLING_PERMISSIONS = [
    # Read-only lookups required during Sales Invoice / Payment Entry validation
    {"doctype": "Customer", "permlevel": 0, "read": 1},
    {"doctype": "Item", "permlevel": 0, "read": 1},
    {"doctype": "Account", "permlevel": 0, "read": 1},
    {"doctype": "Sales Taxes and Charges Template", "permlevel": 0, "read": 1},
    {"doctype": "Mode of Payment", "permlevel": 0, "read": 1},
    {"doctype": "Warehouse", "permlevel": 0, "read": 1},
    {"doctype": "Price List", "permlevel": 0, "read": 1},
    {"doctype": "Item Price", "permlevel": 0, "read": 1},

    # Required write/create/submit — ERPNext does NOT auto-bypass perms here.
    # Triggered by Sales Invoice on_submit when update_stock=1 + batch_no.
    {"doctype": "Serial and Batch Bundle", "permlevel": 0, "read": 1, "write": 1, "create": 1, "submit": 1},
]

ROLE_PERMISSIONS = {
    # All known casings of the pharmacy role are listed because different
    # deployments have used different names. setup_custom_role_permissions()
    # checks role existence and skips any that don't exist on the site, so
    # listing extras is safe.
    "pharmacy": _BILLING_PERMISSIONS,
    "Pharmacy": _BILLING_PERMISSIONS,
    "Pharmacy Staff": _BILLING_PERMISSIONS,
    "reception": _BILLING_PERMISSIONS,
    "Reception": _BILLING_PERMISSIONS,
    "Reception Staff": _BILLING_PERMISSIONS,
    "Laboratory Staff": [
        # lab_test.insert() and doc.submit() in submit_lab_test_with_results
        {"doctype": "Lab Test", "permlevel": 0, "read": 1, "write": 1, "create": 1, "submit": 1},
    ],
    "laboratory": [
        {"doctype": "Lab Test", "permlevel": 0, "read": 1, "write": 1, "create": 1, "submit": 1},
    ],
    "Laboratory": [
        {"doctype": "Lab Test", "permlevel": 0, "read": 1, "write": 1, "create": 1, "submit": 1},
    ],
}


def setup_custom_role_permissions():
    """
    Add minimum permissions for custom roles on core ERPNext doctypes.
    Idempotent — safe to run multiple times. Called from after_install and
    after_migrate hooks so permissions survive bench updates.
    """
    for role, permissions in ROLE_PERMISSIONS.items():
        if not frappe.db.exists("Role", role):
            continue

        for perm in permissions:
            doctype = perm["doctype"]
            permlevel = perm.get("permlevel", 0)

            existing = frappe.db.exists("DocPerm", {
                "parent": doctype,
                "role": role,
                "permlevel": permlevel,
            })
            if not existing:
                existing_custom = frappe.db.exists("Custom DocPerm", {
                    "parent": doctype,
                    "role": role,
                    "permlevel": permlevel,
                })
                if existing_custom:
                    # Row exists — update it in place to pick up any new flags
                    # (e.g. submit was missing previously, Bug G fix)
                    frappe.db.set_value("Custom DocPerm", existing_custom, {
                        "read":   perm.get("read",   0),
                        "write":  perm.get("write",  0),
                        "create": perm.get("create", 0),
                        "delete": perm.get("delete", 0),
                        "submit": perm.get("submit", 0),
                        "cancel": perm.get("cancel", 0),
                        "amend":  perm.get("amend",  0),
                    }, update_modified=False)
                    frappe.logger().info(
                        f"[health_sil] Updated {role} permission on {doctype}"
                    )
                    continue
            else:
                # Built-in DocPerm row exists — skip (cannot modify core perms)
                continue

            custom_perm = frappe.new_doc("Custom DocPerm")
            custom_perm.parent = doctype
            custom_perm.parenttype = "DocType"
            custom_perm.parentfield = "permissions"
            custom_perm.role = role
            custom_perm.permlevel = permlevel
            custom_perm.read = perm.get("read", 0)
            custom_perm.write = perm.get("write", 0)
            custom_perm.create = perm.get("create", 0)
            custom_perm.delete = perm.get("delete", 0)
            custom_perm.submit = perm.get("submit", 0)
            custom_perm.cancel = perm.get("cancel", 0)
            custom_perm.amend = perm.get("amend", 0)
            custom_perm.insert(ignore_permissions=True)

            frappe.logger().info(
                f"[health_sil] Added {role} permission on {doctype}"
            )

    frappe.db.commit()
    frappe.clear_cache()