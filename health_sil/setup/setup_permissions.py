import frappe

# Minimum read-only permissions needed by custom roles for backend API operations.
# These permissions allow internal ERPNext functions (e.g. set_missing_values,
# _get_party_details) to pass permission checks when billing APIs are called
# by restricted users. These do NOT grant create/write/submit access — the
# actual document operations use ignore_permissions in the API code.
#
# The users will NOT see these doctypes in the sidebar because they don't
# have access to the corresponding modules (Accounts, Stock, Selling, etc.).

# Common billing permissions shared by pharmacy/reception roles
_BILLING_PERMISSIONS = [
    # set_missing_values → _get_party_details → frappe.has_permission("Customer", "read")
    {"doctype": "Customer", "permlevel": 0, "read": 1},
    # Invoice item lookups
    {"doctype": "Item", "permlevel": 0, "read": 1},
    # Payment account lookups
    {"doctype": "Account", "permlevel": 0, "read": 1},
    # Tax template resolution
    {"doctype": "Sales Taxes and Charges Template", "permlevel": 0, "read": 1},
    # on_submit → make_bundle_using_old_serial_batch_fields → creates Serial and Batch Bundle
    {"doctype": "Serial and Batch Bundle", "permlevel": 0, "read": 1, "write": 1, "create": 1},
    # Payment entry creation
    {"doctype": "Payment Entry", "permlevel": 0, "read": 1, "write": 1, "create": 1, "submit": 1},
    # Stock posting during update_stock=1 invoices
    {"doctype": "Stock Ledger Entry", "permlevel": 0, "read": 1, "write": 1, "create": 1},
    # Accounting ledger postings
    {"doctype": "GL Entry", "permlevel": 0, "read": 1, "write": 1, "create": 1},
    # Mode of payment validation
    {"doctype": "Mode of Payment", "permlevel": 0, "read": 1},
    # Warehouse lookup for batch items
    {"doctype": "Warehouse", "permlevel": 0, "read": 1},
    # Price list lookups
    {"doctype": "Price List", "permlevel": 0, "read": 1},
    {"doctype": "Item Price", "permlevel": 0, "read": 1},
]

ROLE_PERMISSIONS = {
    "pharmacy": _BILLING_PERMISSIONS,
    "Pharmacy Staff": _BILLING_PERMISSIONS,
    "Reception Staff": _BILLING_PERMISSIONS,
    "Laboratory Staff": [
        # Needed by lab_test.insert — Lab Test permission for creation
        {"doctype": "Lab Test", "permlevel": 0, "read": 1, "write": 1, "create": 1},
    ],
}


def setup_custom_role_permissions():
    """
    Add minimum read-only permissions for custom roles on core ERPNext doctypes.
    This is idempotent — safe to run multiple times (skips if permission already exists).
    Called from after_migrate hook to ensure permissions survive bench updates.
    """
    for role, permissions in ROLE_PERMISSIONS.items():
        # Skip if role doesn't exist
        if not frappe.db.exists("Role", role):
            continue

        for perm in permissions:
            doctype = perm["doctype"]
            permlevel = perm.get("permlevel", 0)

            # Check if this role already has ANY permission on this doctype
            existing = frappe.db.exists("DocPerm", {
                "parent": doctype,
                "role": role,
                "permlevel": permlevel
            })

            if not existing:
                # Also check Custom DocPerm
                existing = frappe.db.exists("Custom DocPerm", {
                    "parent": doctype,
                    "role": role,
                    "permlevel": permlevel
                })

            if existing:
                continue

            # Add the permission via Custom DocPerm so it doesn't modify core DocType json
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
                f"[health_sil] Added {role} read permission on {doctype}"
            )

    frappe.db.commit()
    frappe.clear_cache()
