import frappe
import traceback
from frappe import _


@frappe.whitelist()
def create_stock_entry_from_purchase_invoice(purchase_invoice):
    """
    Create Stock Entry rows for any free / bonus items on a Purchase Invoice.
    Switches to Administrator for doc operations, patches ownership back to actual user.
    """
    original_user = frappe.session.user
    try:
        pi = frappe.get_doc("Purchase Invoice", purchase_invoice)

        # Switch to Administrator for stock entry operations
        frappe.set_user("Administrator")

        for item in pi.items:
            if item.custom_is_free_qty and item.custom_free_qty > 0:
                stock_entry = frappe.new_doc("Stock Entry")
                stock_entry.custom_purchase_invoice_no = purchase_invoice
                stock_entry.purpose = "Material Receipt"
                stock_entry.stock_entry_type = "Purchase Receipt"
                stock_entry.company = pi.company

                stock_entry.append("items", {
                    "item_code": item.item_code,
                    "qty": item.custom_free_qty,
                    "rate": 0,
                    "t_warehouse": item.warehouse,
                    "item_name": item.item_name,
                    "uom": item.uom,
                    "batch_no": item.batch_no,
                    "stock_uom": item.uom,
                    "basic_rate": 0,
                })

                stock_entry.insert(ignore_permissions=True)
                stock_entry.submit()

                # Patch ownership back to the actual user
                frappe.db.set_value("Stock Entry", stock_entry.name, {
                    "owner": original_user,
                    "modified_by": original_user
                }, update_modified=False)

    except Exception as e:
        frappe.log_error(
            title="Stock Entry Creation Error",
            message=(
                f"User: {original_user}\n"
                f"Roles: {', '.join(frappe.get_roles(original_user))}\n"
                f"Purchase Invoice: {purchase_invoice}\n"
                f"Error: {str(e)}\n\n"
                f"Traceback:\n{traceback.format_exc()}"
            ),
        )
        frappe.throw(_("An error occurred while creating stock entry from purchase invoice."))
    finally:
        frappe.set_user(original_user)

